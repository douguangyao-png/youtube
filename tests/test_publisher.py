"""Tests for the configurable publishing stage."""

import json
from datetime import datetime, timedelta
from unittest.mock import patch

from sqlmodel import Session, select

from crosspost.config import AppSettings, PublisherConfig, PublishingConfig
from crosspost.models import Content, ContentStatus, PublishRecord, PublishStatus
from crosspost.publisher import publish_translated_videos


def _translated_content(video_id: str = "pub1") -> Content:
    return Content(
        video_id=video_id,
        channel_id="UC_test",
        title="English title",
        description="English description",
        video_url=f"https://youtube.com/watch?v={video_id}",
        status=ContentStatus.TRANSLATED,
        processed_video_path=f"/processed/{video_id}.mp4",
        platform_metadata=json.dumps(
            {
                "toutiao": {"title": "头条标题", "description": "头条描述"},
                "baijiahao": {"title": "百家号标题", "description": "百家号描述"},
            },
            ensure_ascii=False,
        ),
    )


def _settings(platforms: dict[str, PublisherConfig]) -> AppSettings:
    return AppSettings(publishing=PublishingConfig(enabled=True, platforms=platforms))


def test_publish_disabled_returns_zero(in_memory_engine):
    """Publishing stage is a no-op unless explicitly enabled."""
    with Session(in_memory_engine) as session:
        session.add(_translated_content())
        session.commit()

    assert publish_translated_videos(in_memory_engine, AppSettings()) == 0


def test_dry_run_publishes_all_enabled_platforms(in_memory_engine):
    """Dry-run publisher records successful platform publishes."""
    with Session(in_memory_engine) as session:
        session.add(_translated_content())
        session.commit()

    count = publish_translated_videos(
        in_memory_engine,
        _settings(
            {
                "toutiao": PublisherConfig(enabled=True, backend="dry_run", min_interval_minutes=0),
                "baijiahao": PublisherConfig(enabled=True, backend="dry_run", min_interval_minutes=0),
            }
        ),
    )

    assert count == 2
    with Session(in_memory_engine) as session:
        records = session.exec(select(PublishRecord)).all()
        content = session.exec(select(Content)).one()

    assert {r.platform for r in records} == {"toutiao", "baijiahao"}
    assert all(r.status == PublishStatus.PUBLISHED for r in records)
    assert content.status == ContentStatus.PUBLISHED


def test_rate_limit_defers_second_publish(in_memory_engine):
    """Per-platform min_interval_minutes prevents back-to-back posts."""
    with Session(in_memory_engine) as session:
        first = _translated_content("first")
        second = _translated_content("second")
        session.add(first)
        session.add(second)
        session.commit()
        session.refresh(first)
        session.add(
            PublishRecord(
                content_id=first.id,
                video_id=first.video_id,
                platform="toutiao",
                status=PublishStatus.PUBLISHED,
                published_at=datetime.utcnow(),
            )
        )
        session.commit()

    count = publish_translated_videos(
        in_memory_engine,
        _settings({"toutiao": PublisherConfig(enabled=True, backend="dry_run", min_interval_minutes=120)}),
    )

    assert count == 0
    with Session(in_memory_engine) as session:
        deferred = session.exec(
            select(PublishRecord).where(PublishRecord.video_id == "second")
        ).one()

    assert deferred.status == PublishStatus.SKIPPED
    assert deferred.next_attempt_at is not None


def test_existing_published_records_are_not_republished(in_memory_engine):
    """Already published platform records are skipped idempotently."""
    with Session(in_memory_engine) as session:
        content = _translated_content()
        session.add(content)
        session.commit()
        session.refresh(content)
        session.add(
            PublishRecord(
                content_id=content.id,
                video_id=content.video_id,
                platform="toutiao",
                status=PublishStatus.PUBLISHED,
                published_at=datetime.utcnow() - timedelta(days=1),
            )
        )
        session.commit()

    count = publish_translated_videos(
        in_memory_engine,
        _settings({"toutiao": PublisherConfig(enabled=True, backend="dry_run", min_interval_minutes=0)}),
    )

    assert count == 0


def test_publish_failure_marks_failed_after_max_retries(in_memory_engine):
    """Publisher failures are persisted without blocking other jobs."""
    with Session(in_memory_engine) as session:
        session.add(_translated_content())
        session.commit()

    with patch("crosspost.publisher.DryRunPublisher.publish", side_effect=RuntimeError("boom")):
        count = publish_translated_videos(
            in_memory_engine,
            _settings(
                {
                    "toutiao": PublisherConfig(
                        enabled=True,
                        backend="dry_run",
                        min_interval_minutes=0,
                        max_retries=1,
                    )
                }
            ),
        )

    assert count == 0
    with Session(in_memory_engine) as session:
        record = session.exec(select(PublishRecord)).one()

    assert record.status == PublishStatus.FAILED
    assert record.error_message == "boom"
