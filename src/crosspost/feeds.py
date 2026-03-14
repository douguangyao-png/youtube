"""YouTube RSS feed polling and video discovery."""

from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urlparse

import feedparser
from loguru import logger
from sqlalchemy.engine import Engine
from sqlmodel import Session, select
from tenacity import retry, stop_after_attempt, wait_exponential

from crosspost.config import ChannelConfig
from crosspost.models import Content, ContentStatus

YOUTUBE_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def _extract_video_id(entry) -> str | None:
    """Extract YouTube video ID from a feedparser entry using 3-level fallback.

    1. entry.yt_videoid (standard YouTube Atom extension)
    2. entry.id in 'yt:video:XXX' format
    3. ?v= query param from entry.link
    """
    # Level 1: yt_videoid attribute
    try:
        vid = getattr(entry, "yt_videoid", None)
        if vid:
            return vid
    except Exception:
        pass

    # Level 2: parse yt:video:XXX from entry.id
    try:
        entry_id = getattr(entry, "id", "")
        if entry_id and entry_id.startswith("yt:video:"):
            return entry_id.split("yt:video:", 1)[1]
    except Exception:
        pass

    # Level 3: ?v= from link
    try:
        link = getattr(entry, "link", "")
        if link:
            parsed = urlparse(link)
            qs = parse_qs(parsed.query)
            v = qs.get("v")
            if v:
                return v[0]
    except Exception:
        pass

    return None


def _extract_thumbnail(entry) -> str:
    """Extract thumbnail URL from feedparser entry media_thumbnail list."""
    try:
        thumbnails = getattr(entry, "media_thumbnail", [])
        if thumbnails:
            return thumbnails[0].get("url", "")
    except Exception:
        pass
    return ""


def _parse_entry(entry) -> dict | None:
    """Parse a feedparser entry into a standardized video dict."""
    video_id = _extract_video_id(entry)
    if not video_id:
        logger.warning("Could not extract video_id from feed entry -- skipping")
        return None

    return {
        "video_id": video_id,
        "title": getattr(entry, "title", ""),
        "published": getattr(entry, "published", ""),
        "link": getattr(entry, "link", ""),
        "description": getattr(entry, "media_description", ""),
        "thumbnail": _extract_thumbnail(entry),
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
def _fetch_feed(feed_url: str):
    """Fetch and parse an RSS feed with tenacity retry on network errors."""
    return feedparser.parse(feed_url)


def poll_channel(channel_id: str) -> list[dict]:
    """Poll a YouTube channel's RSS feed and return video entries.

    Args:
        channel_id: YouTube channel ID (e.g. UCxxxxxx).

    Returns:
        List of dicts each containing: video_id, title, published, link,
        description, thumbnail. Returns empty list on error.
    """
    feed_url = YOUTUBE_RSS_URL.format(channel_id=channel_id)
    logger.debug("Polling RSS feed for channel {}", channel_id)

    try:
        feed = _fetch_feed(feed_url)
    except Exception as exc:
        logger.error("Failed to fetch RSS feed for channel {}: {}", channel_id, exc)
        return []

    entries = []
    for entry in feed.entries:
        parsed = _parse_entry(entry)
        if parsed:
            entries.append(parsed)

    logger.info("Polled channel {}: {} entries found", channel_id, len(entries))
    return entries


def _parse_published(published_str: str) -> datetime | None:
    """Attempt to parse a published date string into a datetime."""
    if not published_str:
        return None
    try:
        return parsedate_to_datetime(published_str)
    except Exception:
        pass
    try:
        return datetime.fromisoformat(published_str.replace("Z", "+00:00"))
    except Exception:
        pass
    return None


def discover_new_videos(engine: Engine, channel: ChannelConfig) -> list[Content]:
    """Discover new videos from a channel's RSS feed and insert them into the DB.

    Checks for deduplication by video_id -- existing videos are skipped.

    Args:
        engine: SQLAlchemy engine connected to the database.
        channel: Channel configuration with channel_id.

    Returns:
        List of newly created Content objects with DISCOVERED status.
    """
    entries = poll_channel(channel.channel_id)
    if not entries:
        logger.info("No RSS entries for channel {}", channel.channel_id)
        return []

    new_videos: list[Content] = []
    skipped = 0

    with Session(engine) as session:
        # Collect existing video_ids to avoid per-entry queries
        existing_ids_result = session.exec(
            select(Content.video_id).where(
                Content.video_id.in_([e["video_id"] for e in entries])  # type: ignore[attr-defined]
            )
        )
        existing_ids = set(existing_ids_result.all())

        for entry in entries:
            video_id = entry["video_id"]
            if video_id in existing_ids:
                skipped += 1
                logger.debug("Skipping existing video_id={}", video_id)
                continue

            video_url = entry.get("link") or f"https://www.youtube.com/watch?v={video_id}"

            content = Content(
                video_id=video_id,
                channel_id=channel.channel_id,
                title=entry.get("title", ""),
                description=entry.get("description", ""),
                thumbnail_url=entry.get("thumbnail", ""),
                video_url=video_url,
                status=ContentStatus.DISCOVERED,
                published_at=_parse_published(entry.get("published", "")),
            )

            session.add(content)
            new_videos.append(content)

        session.commit()

        # Refresh objects to get DB-assigned ids
        for content in new_videos:
            session.refresh(content)

    logger.info(
        "Channel {}: {} new videos discovered, {} skipped (already in DB)",
        channel.channel_id,
        len(new_videos),
        skipped,
    )
    return new_videos
