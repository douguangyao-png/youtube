"""End-to-end integration tests for the CrossPost acquisition pipeline."""

import os
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, create_engine, select

from crosspost.config import AppSettings, ChannelConfig, DownloadConfig, ScheduleConfig
from crosspost.database import init_db
from crosspost.downloader import process_discovered_videos
from crosspost.feeds import discover_new_videos
from crosspost.models import Content, ContentStatus
from crosspost.scheduler import recover_incomplete_downloads


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_feed_entry(video_id: str, title: str = "") -> MagicMock:
    """Build a mock feedparser entry for the given video_id."""
    entry = MagicMock()
    entry.yt_videoid = video_id
    entry.title = title or f"Video {video_id}"
    entry.published = "Mon, 01 Jan 2024 00:00:00 +0000"
    entry.link = f"https://www.youtube.com/watch?v={video_id}"
    entry.media_description = "Test description"
    entry.media_thumbnail = [{"url": f"https://img.youtube.com/{video_id}.jpg"}]
    return entry


def _make_feed(entries):
    """Build a mock feedparser result containing the given entries."""
    feed = MagicMock()
    feed.entries = entries
    return feed


def _make_ydl_metadata(video_id: str, duration: int) -> dict:
    """Build a minimal yt-dlp metadata dict."""
    return {
        "id": video_id,
        "title": f"Video {video_id}",
        "duration": duration,
        "thumbnail": f"https://img.youtube.com/{video_id}.jpg",
        "description": "Test",
        "requested_downloads": [{"filepath": f"/tmp/downloads/{video_id}.mp4"}],
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def in_memory_engine():
    """In-memory SQLite engine with all tables created."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_db(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def settings_with_channel():
    """AppSettings configured with one channel and 180s max_duration."""
    return AppSettings(
        channels=[ChannelConfig(channel_id="UC_test_channel", name="Test Channel")],
        download=DownloadConfig(output_dir="/tmp/crosspost_test", max_duration=180),
        schedule=ScheduleConfig(poll_interval_minutes=30),
        database_url="sqlite:///:memory:",
    )


# ---------------------------------------------------------------------------
# Test: Full pipeline
# ---------------------------------------------------------------------------


def test_full_pipeline(settings_with_channel, in_memory_engine, tmp_path):
    """End-to-end: RSS poll -> discover -> filter by duration -> download -> state tracking.

    Videos:
      v1: 60s  -> should be DOWNLOADED (under 180s threshold)
      v2: 300s -> should stay DISCOVERED (over threshold, skipped)
      v3: 120s -> should be DOWNLOADED (under threshold)
    """
    entries = [
        _make_feed_entry("v1", "Short Video"),
        _make_feed_entry("v2", "Long Video"),
        _make_feed_entry("v3", "Medium Video"),
    ]
    mock_feed = _make_feed(entries)

    metadata_map = {
        "v1": _make_ydl_metadata("v1", 60),
        "v2": _make_ydl_metadata("v2", 300),
        "v3": _make_ydl_metadata("v3", 120),
    }

    def fake_extract_info(url, download=False):
        vid = url.split("v=")[-1]
        return metadata_map[vid]

    mock_ydl_instance = MagicMock()
    mock_ydl_instance.__enter__ = lambda s: mock_ydl_instance
    mock_ydl_instance.__exit__ = MagicMock(return_value=False)
    mock_ydl_instance.extract_info = fake_extract_info

    with (
        patch("feedparser.parse", return_value=mock_feed),
        patch("yt_dlp.YoutubeDL", return_value=mock_ydl_instance),
    ):
        # Step 1: Discover new videos
        channel = settings_with_channel.channels[0]
        new_videos = discover_new_videos(in_memory_engine, channel)

    # All 3 should be discovered
    assert len(new_videos) == 3

    # Verify DISCOVERED rows in DB
    with Session(in_memory_engine) as session:
        all_content = session.exec(select(Content)).all()
    assert len(all_content) == 3
    assert all(c.status == ContentStatus.DISCOVERED for c in all_content)

    # Step 2: Process (filter + download)
    with patch("yt_dlp.YoutubeDL", return_value=mock_ydl_instance):
        downloaded = process_discovered_videos(in_memory_engine, settings_with_channel)

    assert downloaded == 2  # v1 and v3

    # Verify final states
    with Session(in_memory_engine) as session:
        items = session.exec(select(Content)).all()
        statuses = {c.video_id: c for c in items}

    assert statuses["v1"].status == ContentStatus.DOWNLOADED
    assert statuses["v1"].video_path == "/tmp/downloads/v1.mp4"

    assert statuses["v2"].status == ContentStatus.DISCOVERED  # still skipped

    assert statuses["v3"].status == ContentStatus.DOWNLOADED
    assert statuses["v3"].video_path == "/tmp/downloads/v3.mp4"


# ---------------------------------------------------------------------------
# Test: Deduplication across polls
# ---------------------------------------------------------------------------


def test_dedup_across_polls(settings_with_channel, in_memory_engine):
    """Running discover_new_videos twice with the same feed data produces no duplicates."""
    entries = [
        _make_feed_entry("dup_v1", "Video 1"),
        _make_feed_entry("dup_v2", "Video 2"),
    ]
    mock_feed = _make_feed(entries)

    with patch("feedparser.parse", return_value=mock_feed):
        channel = settings_with_channel.channels[0]
        first_poll = discover_new_videos(in_memory_engine, channel)
        second_poll = discover_new_videos(in_memory_engine, channel)

    # First poll inserts 2 rows; second poll inserts 0 (all already exist)
    assert len(first_poll) == 2
    assert len(second_poll) == 0

    # Database should still have exactly 2 rows
    with Session(in_memory_engine) as session:
        count = len(session.exec(select(Content)).all())
    assert count == 2


# ---------------------------------------------------------------------------
# Test: Crash recovery
# ---------------------------------------------------------------------------


def test_crash_recovery(in_memory_engine):
    """recover_incomplete_downloads transitions DOWNLOADING rows back to DISCOVERED."""
    with Session(in_memory_engine) as session:
        c1 = Content(
            video_id="crash_v1",
            channel_id="UC_test",
            video_url="https://youtube.com/watch?v=crash_v1",
            status=ContentStatus.DOWNLOADING,
        )
        c2 = Content(
            video_id="crash_v2",
            channel_id="UC_test",
            video_url="https://youtube.com/watch?v=crash_v2",
            status=ContentStatus.DOWNLOADING,
        )
        c3 = Content(
            video_id="ok_v1",
            channel_id="UC_test",
            video_url="https://youtube.com/watch?v=ok_v1",
            status=ContentStatus.DOWNLOADED,  # should not be touched
        )
        session.add_all([c1, c2, c3])
        session.commit()

    recovered = recover_incomplete_downloads(in_memory_engine)
    assert recovered == 2

    with Session(in_memory_engine) as session:
        items = session.exec(select(Content)).all()
        statuses = {c.video_id: c.status for c in items}

    assert statuses["crash_v1"] == ContentStatus.DISCOVERED
    assert statuses["crash_v2"] == ContentStatus.DISCOVERED
    assert statuses["ok_v1"] == ContentStatus.DOWNLOADED
