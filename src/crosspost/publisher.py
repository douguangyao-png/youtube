"""Publishing stage for processed CrossPost content."""

from __future__ import annotations

import json
import mimetypes
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from loguru import logger
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from crosspost.config import PublisherConfig
from crosspost.models import Content, ContentStatus, PublishRecord, PublishStatus


class PublishError(RuntimeError):
    """Raised when a platform publish attempt fails."""


class Publisher(ABC):
    """Base class for platform publishers."""

    def __init__(self, platform: str, config: PublisherConfig):
        self.platform = platform
        self.config = config

    @abstractmethod
    def publish(self, content: Content, metadata: dict[str, Any]) -> dict[str, str]:
        """Publish content and return platform identifiers."""


class DryRunPublisher(Publisher):
    """Publisher that records a successful publish without external side effects."""

    def publish(self, content: Content, metadata: dict[str, Any]) -> dict[str, str]:
        return {
            "platform_post_id": f"dry-run-{content.video_id}-{self.platform}",
            "platform_url": content.video_url or "",
        }


class ApiPublisher(Publisher):
    """Configurable JSON-over-HTTP API publisher."""

    def publish(self, content: Content, metadata: dict[str, Any]) -> dict[str, str]:
        api = self.config.api
        if not api.endpoint:
            raise PublishError(f"{self.platform}: api.endpoint is required")
        if not content.processed_video_path:
            raise PublishError(f"{self.platform}: processed_video_path is required")

        payload = dict(api.extra_payload)
        payload[api.title_field] = metadata.get("title") or content.title
        payload[api.description_field] = metadata.get("description") or content.description
        payload[api.video_field] = content.processed_video_path

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            api.endpoint,
            data=body,
            headers=_build_headers(api.token_header, api.token_prefix, api.token),
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise PublishError(f"{self.platform}: HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise PublishError(f"{self.platform}: {exc.reason}") from exc

        return _parse_publish_response(response_body)


class BrowserPublisher(Publisher):
    """Playwright based publisher with configurable selectors."""

    def publish(self, content: Content, metadata: dict[str, Any]) -> dict[str, str]:
        cfg = self.config.browser
        if not cfg.upload_url:
            raise PublishError(f"{self.platform}: browser.upload_url is required")
        if not cfg.file_selector or not cfg.submit_selector:
            raise PublishError(f"{self.platform}: file_selector and submit_selector are required")
        if not content.processed_video_path:
            raise PublishError(f"{self.platform}: processed_video_path is required")

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise PublishError("Playwright is not installed; install crosspost with browser deps") from exc

        video_path = str(Path(content.processed_video_path).expanduser().resolve())
        if not Path(video_path).exists():
            raise PublishError(f"{self.platform}: video file not found: {video_path}")

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=cfg.headless)
            context_kwargs: dict[str, Any] = {}
            if cfg.storage_state_path:
                context_kwargs["storage_state"] = cfg.storage_state_path
            context = browser.new_context(**context_kwargs)
            page = context.new_page()
            page.goto(cfg.upload_url, wait_until="domcontentloaded")
            page.set_input_files(cfg.file_selector, video_path)
            if cfg.title_selector:
                page.fill(cfg.title_selector, metadata.get("title") or content.title)
            if cfg.description_selector:
                page.fill(cfg.description_selector, metadata.get("description") or content.description)
            page.click(cfg.submit_selector)
            if cfg.success_selector:
                page.wait_for_selector(cfg.success_selector, timeout=120_000)
            else:
                page.wait_for_timeout(cfg.wait_after_submit_seconds * 1000)
            current_url = page.url
            context.close()
            browser.close()

        return {"platform_post_id": "", "platform_url": current_url}


def publish_translated_videos(engine: Engine, settings) -> int:  # noqa: ANN001
    """Publish TRANSLATED content to all enabled platforms."""
    publishing = settings.publishing
    if not publishing.enabled:
        logger.info("Publishing disabled")
        return 0

    platforms = {
        platform: cfg
        for platform, cfg in publishing.platforms.items()
        if cfg.enabled
    }
    if not platforms:
        logger.info("Publishing enabled but no platforms are enabled")
        return 0

    with Session(engine) as session:
        contents = session.exec(
            select(Content).where(Content.status == ContentStatus.TRANSLATED)
        ).all()

    published_count = 0
    for content in contents:
        metadata_by_platform = _load_platform_metadata(content)
        for platform, cfg in platforms.items():
            if _publish_one(engine, content, platform, cfg, metadata_by_platform.get(platform, {})):
                published_count += 1

        _mark_content_published_if_complete(engine, content.id, platforms.keys())

    logger.info("Publishing complete: {} platform publish(es) succeeded", published_count)
    return published_count


def _publish_one(
    engine: Engine,
    content: Content,
    platform: str,
    cfg: PublisherConfig,
    metadata: dict[str, Any],
) -> bool:
    now = datetime.utcnow()
    with Session(engine) as session:
        record = _get_or_create_record(session, content, platform)
        if record.status == PublishStatus.PUBLISHED:
            return False
        if record.next_attempt_at and record.next_attempt_at > now:
            logger.info("Skipping {} for {} until {}", platform, content.video_id, record.next_attempt_at)
            return False
        if not _rate_limit_allows(session, platform, cfg.min_interval_minutes, now):
            record.status = PublishStatus.SKIPPED
            record.next_attempt_at = now + timedelta(minutes=cfg.min_interval_minutes)
            record.updated_at = now
            session.add(record)
            session.commit()
            return False

        record.status = PublishStatus.PUBLISHING
        record.attempts += 1
        record.updated_at = now
        session.add(record)
        session.commit()

    publisher = create_publisher(platform, cfg)
    try:
        result = publisher.publish(content, metadata)
    except Exception as exc:
        _record_failure(engine, content, platform, cfg, str(exc))
        return False

    with Session(engine) as session:
        record = _get_or_create_record(session, content, platform)
        record.status = PublishStatus.PUBLISHED
        record.platform_post_id = result.get("platform_post_id") or None
        record.platform_url = result.get("platform_url") or None
        record.error_message = None
        record.next_attempt_at = None
        record.published_at = datetime.utcnow()
        record.updated_at = record.published_at
        session.add(record)
        session.commit()
    return True


def create_publisher(platform: str, cfg: PublisherConfig) -> Publisher:
    """Create a platform publisher from configuration."""
    if cfg.backend == "dry_run":
        return DryRunPublisher(platform, cfg)
    if cfg.backend == "api":
        return ApiPublisher(platform, cfg)
    if cfg.backend == "browser":
        return BrowserPublisher(platform, cfg)
    raise PublishError(f"{platform}: unsupported publisher backend {cfg.backend!r}")


def _get_or_create_record(session: Session, content: Content, platform: str) -> PublishRecord:
    record = session.exec(
        select(PublishRecord).where(
            PublishRecord.content_id == content.id,
            PublishRecord.platform == platform,
        )
    ).first()
    if record:
        return record

    record = PublishRecord(
        content_id=content.id,
        video_id=content.video_id,
        platform=platform,
        status=PublishStatus.PENDING,
    )
    session.add(record)
    session.commit()
    session.refresh(record)
    return record


def _rate_limit_allows(
    session: Session,
    platform: str,
    min_interval_minutes: int,
    now: datetime,
) -> bool:
    if min_interval_minutes <= 0:
        return True
    latest = session.exec(
        select(PublishRecord)
        .where(
            PublishRecord.platform == platform,
            PublishRecord.status == PublishStatus.PUBLISHED,
        )
        .order_by(PublishRecord.published_at.desc())
    ).first()
    if not latest or not latest.published_at:
        return True
    return latest.published_at + timedelta(minutes=min_interval_minutes) <= now


def _record_failure(
    engine: Engine,
    content: Content,
    platform: str,
    cfg: PublisherConfig,
    error_message: str,
) -> None:
    with Session(engine) as session:
        record = _get_or_create_record(session, content, platform)
        now = datetime.utcnow()
        record.error_message = error_message
        record.updated_at = now
        if record.attempts >= cfg.max_retries:
            record.status = PublishStatus.FAILED
            record.next_attempt_at = None
        else:
            delay_minutes = min(60, 2 ** max(0, record.attempts - 1))
            record.status = PublishStatus.PENDING
            record.next_attempt_at = now + timedelta(minutes=delay_minutes)
        session.add(record)
        session.commit()


def _mark_content_published_if_complete(
    engine: Engine,
    content_id: int | None,
    platforms: Any,
) -> None:
    if content_id is None:
        return
    platform_set = set(platforms)
    with Session(engine) as session:
        records = session.exec(
            select(PublishRecord).where(PublishRecord.content_id == content_id)
        ).all()
        published = {
            record.platform
            for record in records
            if record.status == PublishStatus.PUBLISHED
        }
        if platform_set and platform_set.issubset(published):
            content = session.get(Content, content_id)
            if content:
                content.status = ContentStatus.PUBLISHED
                session.add(content)
                session.commit()


def _load_platform_metadata(content: Content) -> dict[str, dict[str, Any]]:
    if not content.platform_metadata:
        return {}
    try:
        data = json.loads(content.platform_metadata)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _build_headers(token_header: str, token_prefix: str, token: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers[token_header] = f"{token_prefix} {token}".strip()
    return headers


def _parse_publish_response(response_body: str) -> dict[str, str]:
    try:
        data = json.loads(response_body) if response_body else {}
    except json.JSONDecodeError:
        data = {}
    return {
        "platform_post_id": str(
            data.get("platform_post_id") or data.get("id") or data.get("post_id") or ""
        ),
        "platform_url": str(data.get("platform_url") or data.get("url") or ""),
    }


def guess_mime_type(path: str) -> str:
    """Return a MIME type for future multipart publisher extensions."""
    return mimetypes.guess_type(path)[0] or "application/octet-stream"
