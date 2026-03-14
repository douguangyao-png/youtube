"""Tests for YouTube RSS feed polling and video discovery."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import create_engine

from crosspost.config import ChannelConfig
from crosspost.database import init_db
from crosspost.feeds import discover_new_videos, poll_channel
from crosspost.models import Content, ContentStatus


# ---------------------------------------------------------------------------
# Sample YouTube Atom feed data (mimics real feedparser output)
# ---------------------------------------------------------------------------

SAMPLE_ENTRY_1 = MagicMock()
SAMPLE_ENTRY_1.yt_videoid = "dQw4w9WgXcQ"
SAMPLE_ENTRY_1.title = "Never Gonna Give You Up"
SAMPLE_ENTRY_1.published = "2024-01-15T12:00:00+00:00"
SAMPLE_ENTRY_1.link = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
SAMPLE_ENTRY_1.id = "yt:video:dQw4w9WgXcQ"
SAMPLE_ENTRY_1.media_description = "The classic Rickroll video"
SAMPLE_ENTRY_1.media_thumbnail = [{"url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg"}]

SAMPLE_ENTRY_2 = MagicMock()
SAMPLE_ENTRY_2.yt_videoid = "oHg5SJYRHA0"
SAMPLE_ENTRY_2.title = "RickRoll'D"
SAMPLE_ENTRY_2.published = "2024-01-20T10:00:00+00:00"
SAMPLE_ENTRY_2.link = "https://www.youtube.com/watch?v=oHg5SJYRHA0"
SAMPLE_ENTRY_2.id = "yt:video:oHg5SJYRHA0"
SAMPLE_ENTRY_2.media_description = "Another classic"
SAMPLE_ENTRY_2.media_thumbnail = [{"url": "https://i.ytimg.com/vi/oHg5SJYRHA0/maxresdefault.jpg"}]


def make_feed(entries=None, bozo=False):
    """Helper to create a mock feedparser result."""
    feed = MagicMock()
    feed.entries = entries if entries is not None else []
    feed.bozo = bozo
    feed.bozo_exception = Exception("parse error") if bozo else None
    return feed


# ---------------------------------------------------------------------------
# poll_channel tests
# ---------------------------------------------------------------------------


class TestPollChannel:
    def test_poll_channel_returns_video_entries(self, mocker):
        """poll_channel returns list of dicts with expected keys."""
        mock_parse = mocker.patch("feedparser.parse", return_value=make_feed([SAMPLE_ENTRY_1]))

        results = poll_channel("UCtest123")

        assert len(results) == 1
        video = results[0]
        assert video["video_id"] == "dQw4w9WgXcQ"
        assert video["title"] == "Never Gonna Give You Up"
        assert video["link"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert "published" in video
        assert "description" in video
        assert "thumbnail" in video

    def test_poll_channel_extracts_video_id_from_yt_videoid(self, mocker):
        """video_id is extracted from yt_videoid field first."""
        entry = MagicMock()
        entry.yt_videoid = "abc123"
        entry.id = "yt:video:other"
        entry.link = "https://www.youtube.com/watch?v=different"
        entry.title = "Test"
        entry.published = "2024-01-15T12:00:00+00:00"
        entry.media_description = ""
        entry.media_thumbnail = []

        mocker.patch("feedparser.parse", return_value=make_feed([entry]))
        results = poll_channel("UCtest123")

        assert results[0]["video_id"] == "abc123"

    def test_poll_channel_video_id_fallback_to_id_field(self, mocker):
        """Falls back to parsing entry.id (yt:video:XXX) when yt_videoid absent."""
        entry = MagicMock()
        # Make yt_videoid missing by not setting it (raise AttributeError)
        del entry.yt_videoid
        entry.id = "yt:video:fallback456"
        entry.link = "https://www.youtube.com/watch?v=fallback456"
        entry.title = "Test"
        entry.published = "2024-01-15T12:00:00+00:00"
        entry.media_description = ""
        entry.media_thumbnail = []

        mocker.patch("feedparser.parse", return_value=make_feed([entry]))
        results = poll_channel("UCtest123")

        assert results[0]["video_id"] == "fallback456"

    def test_poll_channel_video_id_fallback_to_link(self, mocker):
        """Falls back to ?v= query param from link when both yt_videoid and id parse fail."""
        entry = MagicMock()
        del entry.yt_videoid
        entry.id = "not-a-yt-video-id"
        entry.link = "https://www.youtube.com/watch?v=linkfallback789"
        entry.title = "Test"
        entry.published = "2024-01-15T12:00:00+00:00"
        entry.media_description = ""
        entry.media_thumbnail = []

        mocker.patch("feedparser.parse", return_value=make_feed([entry]))
        results = poll_channel("UCtest123")

        assert results[0]["video_id"] == "linkfallback789"

    def test_poll_channel_empty_feed(self, mocker):
        """Empty feed returns empty list without error."""
        mocker.patch("feedparser.parse", return_value=make_feed([]))

        results = poll_channel("UCtest123")

        assert results == []

    def test_poll_channel_network_error(self, mocker):
        """Network failure returns empty list and logs the error."""
        mocker.patch("feedparser.parse", side_effect=Exception("Connection refused"))

        results = poll_channel("UCtest123")

        assert results == []

    def test_poll_channel_builds_correct_url(self, mocker):
        """RSS URL is correctly built from channel_id."""
        mock_parse = mocker.patch("feedparser.parse", return_value=make_feed([]))

        poll_channel("UCspecific123")

        call_args = mock_parse.call_args[0][0]
        assert "UCspecific123" in call_args
        assert "feeds/videos.xml" in call_args

    def test_poll_channel_multiple_entries(self, mocker):
        """Multiple entries are all returned."""
        mocker.patch("feedparser.parse", return_value=make_feed([SAMPLE_ENTRY_1, SAMPLE_ENTRY_2]))

        results = poll_channel("UCtest123")

        assert len(results) == 2
        video_ids = [r["video_id"] for r in results]
        assert "dQw4w9WgXcQ" in video_ids
        assert "oHg5SJYRHA0" in video_ids


# ---------------------------------------------------------------------------
# discover_new_videos tests
# ---------------------------------------------------------------------------


class TestDiscoverNewVideos:
    @pytest.fixture
    def engine(self):
        """In-memory SQLite engine with tables created."""
        engine = create_engine("sqlite:///:memory:", echo=False)
        init_db(engine)
        yield engine
        engine.dispose()

    @pytest.fixture
    def channel(self):
        return ChannelConfig(channel_id="UCtest123", name="Test Channel")

    def test_discover_new_videos_inserts_discovered(self, mocker, engine, channel):
        """New videos from RSS are inserted with DISCOVERED status."""
        mocker.patch(
            "crosspost.feeds.poll_channel",
            return_value=[
                {
                    "video_id": "newvid001",
                    "title": "New Video",
                    "published": "2024-01-15T12:00:00+00:00",
                    "link": "https://www.youtube.com/watch?v=newvid001",
                    "description": "A new video",
                    "thumbnail": "https://i.ytimg.com/vi/newvid001/maxresdefault.jpg",
                }
            ],
        )

        new_videos = discover_new_videos(engine, channel)

        assert len(new_videos) == 1
        assert new_videos[0].video_id == "newvid001"
        assert new_videos[0].status == ContentStatus.DISCOVERED
        assert new_videos[0].title == "New Video"

    def test_discover_new_videos_dedup(self, mocker, engine, channel):
        """Video already in DB is not re-inserted."""
        from sqlmodel import Session

        # Pre-insert a video
        with Session(engine) as session:
            existing = Content(
                video_id="existingvid",
                channel_id="UCtest123",
                title="Existing Video",
                video_url="https://www.youtube.com/watch?v=existingvid",
            )
            session.add(existing)
            session.commit()

        mocker.patch(
            "crosspost.feeds.poll_channel",
            return_value=[
                {
                    "video_id": "existingvid",
                    "title": "Existing Video",
                    "published": "2024-01-15T12:00:00+00:00",
                    "link": "https://www.youtube.com/watch?v=existingvid",
                    "description": "",
                    "thumbnail": "",
                }
            ],
        )

        new_videos = discover_new_videos(engine, channel)

        assert new_videos == []

    def test_discover_new_videos_mixed(self, mocker, engine, channel):
        """Only new videos in a mixed feed are inserted."""
        from sqlmodel import Session

        with Session(engine) as session:
            existing = Content(
                video_id="existingvid",
                channel_id="UCtest123",
                title="Existing Video",
                video_url="https://www.youtube.com/watch?v=existingvid",
            )
            session.add(existing)
            session.commit()

        mocker.patch(
            "crosspost.feeds.poll_channel",
            return_value=[
                {
                    "video_id": "existingvid",
                    "title": "Existing Video",
                    "published": "2024-01-14T12:00:00+00:00",
                    "link": "https://www.youtube.com/watch?v=existingvid",
                    "description": "",
                    "thumbnail": "",
                },
                {
                    "video_id": "newvid002",
                    "title": "Brand New",
                    "published": "2024-01-15T12:00:00+00:00",
                    "link": "https://www.youtube.com/watch?v=newvid002",
                    "description": "Fresh content",
                    "thumbnail": "",
                },
            ],
        )

        new_videos = discover_new_videos(engine, channel)

        assert len(new_videos) == 1
        assert new_videos[0].video_id == "newvid002"

    def test_discover_new_videos_returns_content_objects(self, mocker, engine, channel):
        """Returned list contains Content model instances."""
        mocker.patch(
            "crosspost.feeds.poll_channel",
            return_value=[
                {
                    "video_id": "vid123",
                    "title": "Test",
                    "published": "2024-01-15T12:00:00+00:00",
                    "link": "https://www.youtube.com/watch?v=vid123",
                    "description": "",
                    "thumbnail": "",
                }
            ],
        )

        new_videos = discover_new_videos(engine, channel)

        assert all(isinstance(v, Content) for v in new_videos)

    def test_discover_new_videos_sets_video_url(self, mocker, engine, channel):
        """Inserted Content rows have video_url built from video_id."""
        mocker.patch(
            "crosspost.feeds.poll_channel",
            return_value=[
                {
                    "video_id": "urltest123",
                    "title": "URL Test",
                    "published": "2024-01-15T12:00:00+00:00",
                    "link": "https://www.youtube.com/watch?v=urltest123",
                    "description": "",
                    "thumbnail": "",
                }
            ],
        )

        new_videos = discover_new_videos(engine, channel)

        assert "urltest123" in new_videos[0].video_url
