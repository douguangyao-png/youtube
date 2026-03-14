"""Tests for yt-dlp metadata extraction, duration filtering, and video download."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlmodel import Session, create_engine, select as sqlselect

from crosspost.config import AppSettings, ChannelConfig, DownloadConfig
from crosspost.database import init_db
from crosspost.downloader import (
    download_video,
    get_video_metadata,
    process_discovered_videos,
    should_download,
)
from crosspost.models import Content, ContentStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def engine():
    """In-memory SQLite engine with tables."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    init_db(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def settings():
    """Default AppSettings for tests."""
    return AppSettings(
        channels=[ChannelConfig(channel_id="UCtest123", name="Test Channel")],
        download=DownloadConfig(
            output_dir="/tmp/test_downloads",
            max_duration=180,
            cookies_browser="firefox",
        ),
    )


SAMPLE_METADATA = {
    "id": "testvid001",
    "title": "Test Video Title",
    "description": "Test description",
    "duration": 120,
    "thumbnail": "https://i.ytimg.com/vi/testvid001/maxresdefault.jpg",
    "webpage_url": "https://www.youtube.com/watch?v=testvid001",
}


# ---------------------------------------------------------------------------
# get_video_metadata tests
# ---------------------------------------------------------------------------


class TestGetVideoMetadata:
    def test_get_metadata_returns_dict(self, mocker):
        """get_video_metadata returns a dict with duration, title, description, thumbnail."""
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.__enter__ = MagicMock(return_value=mock_ydl_instance)
        mock_ydl_instance.__exit__ = MagicMock(return_value=False)
        mock_ydl_instance.extract_info.return_value = SAMPLE_METADATA

        mocker.patch("yt_dlp.YoutubeDL", return_value=mock_ydl_instance)

        result = get_video_metadata("https://www.youtube.com/watch?v=testvid001")

        assert result is not None
        assert result["duration"] == 120
        assert result["title"] == "Test Video Title"
        assert result["description"] == "Test description"
        assert result["thumbnail"] == "https://i.ytimg.com/vi/testvid001/maxresdefault.jpg"

    def test_get_metadata_uses_cookies_as_tuple(self, mocker):
        """cookiesfrombrowser is passed as a tuple, NOT a string."""
        mock_ydl_class = mocker.patch("yt_dlp.YoutubeDL")
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.__enter__ = MagicMock(return_value=mock_ydl_instance)
        mock_ydl_instance.__exit__ = MagicMock(return_value=False)
        mock_ydl_instance.extract_info.return_value = SAMPLE_METADATA
        mock_ydl_class.return_value = mock_ydl_instance

        get_video_metadata("https://www.youtube.com/watch?v=testvid001", cookies_browser="firefox")

        call_kwargs = mock_ydl_class.call_args[0][0]
        cookies_value = call_kwargs["cookiesfrombrowser"]
        assert isinstance(cookies_value, tuple), f"cookiesfrombrowser must be tuple, got {type(cookies_value)}"
        assert cookies_value[0] == "firefox"

    def test_get_metadata_returns_none_on_error(self, mocker):
        """Returns None when yt-dlp raises an exception."""
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.__enter__ = MagicMock(return_value=mock_ydl_instance)
        mock_ydl_instance.__exit__ = MagicMock(return_value=False)
        mock_ydl_instance.extract_info.side_effect = Exception("Video unavailable")

        mocker.patch("yt_dlp.YoutubeDL", return_value=mock_ydl_instance)

        result = get_video_metadata("https://www.youtube.com/watch?v=testvid001")
        assert result is None

    def test_get_metadata_uses_skip_download(self, mocker):
        """yt-dlp options include skip_download=True for metadata-only extraction."""
        mock_ydl_class = mocker.patch("yt_dlp.YoutubeDL")
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.__enter__ = MagicMock(return_value=mock_ydl_instance)
        mock_ydl_instance.__exit__ = MagicMock(return_value=False)
        mock_ydl_instance.extract_info.return_value = SAMPLE_METADATA
        mock_ydl_class.return_value = mock_ydl_instance

        get_video_metadata("https://www.youtube.com/watch?v=testvid001")

        opts = mock_ydl_class.call_args[0][0]
        assert opts.get("skip_download") is True


# ---------------------------------------------------------------------------
# should_download tests
# ---------------------------------------------------------------------------


class TestShouldDownload:
    def test_duration_filter_pass(self):
        """Video with duration <= max_duration should be downloaded."""
        assert should_download({"duration": 120}, max_duration=180) is True

    def test_duration_filter_exact_boundary(self):
        """Video with duration == max_duration should be downloaded."""
        assert should_download({"duration": 180}, max_duration=180) is True

    def test_duration_filter_fail(self):
        """Video with duration > max_duration should not be downloaded."""
        assert should_download({"duration": 300}, max_duration=180) is False

    def test_duration_filter_zero(self):
        """Video with duration=0 passes filter (unknown duration)."""
        assert should_download({"duration": 0}, max_duration=180) is True

    def test_duration_filter_none(self):
        """Video with duration=None passes filter (unknown duration)."""
        assert should_download({"duration": None}, max_duration=180) is True

    def test_duration_filter_missing_key(self):
        """Video with no duration key passes filter (unknown)."""
        assert should_download({}, max_duration=180) is True


# ---------------------------------------------------------------------------
# download_video tests
# ---------------------------------------------------------------------------


class TestDownloadVideo:
    def test_download_video_calls_yt_dlp(self, mocker, tmp_path):
        """download_video calls yt-dlp with writethumbnail and writeinfojson."""
        mock_ydl_class = mocker.patch("yt_dlp.YoutubeDL")
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.__enter__ = MagicMock(return_value=mock_ydl_instance)
        mock_ydl_instance.__exit__ = MagicMock(return_value=False)
        mock_ydl_instance.extract_info.return_value = SAMPLE_METADATA
        mock_ydl_class.return_value = mock_ydl_instance

        output_dir = str(tmp_path)
        download_video("https://www.youtube.com/watch?v=testvid001", output_dir)

        opts = mock_ydl_class.call_args[0][0]
        assert opts.get("writethumbnail") is True
        assert opts.get("writeinfojson") is True
        assert output_dir in opts.get("outtmpl", "")

    def test_download_video_uses_cookies_as_tuple(self, mocker, tmp_path):
        """download_video also uses cookiesfrombrowser as tuple."""
        mock_ydl_class = mocker.patch("yt_dlp.YoutubeDL")
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.__enter__ = MagicMock(return_value=mock_ydl_instance)
        mock_ydl_instance.__exit__ = MagicMock(return_value=False)
        mock_ydl_instance.extract_info.return_value = SAMPLE_METADATA
        mock_ydl_class.return_value = mock_ydl_instance

        download_video(
            "https://www.youtube.com/watch?v=testvid001",
            str(tmp_path),
            cookies_browser="firefox",
        )

        opts = mock_ydl_class.call_args[0][0]
        cookies_value = opts["cookiesfrombrowser"]
        assert isinstance(cookies_value, tuple)
        assert cookies_value[0] == "firefox"

    def test_download_video_creates_output_dir(self, mocker, tmp_path):
        """download_video creates the output directory if it does not exist."""
        new_dir = tmp_path / "new_subdir" / "deep"
        assert not new_dir.exists()

        mock_ydl_instance = MagicMock()
        mock_ydl_instance.__enter__ = MagicMock(return_value=mock_ydl_instance)
        mock_ydl_instance.__exit__ = MagicMock(return_value=False)
        mock_ydl_instance.extract_info.return_value = SAMPLE_METADATA
        mocker.patch("yt_dlp.YoutubeDL", return_value=mock_ydl_instance)

        download_video("https://www.youtube.com/watch?v=testvid001", str(new_dir))

        assert new_dir.exists()


# ---------------------------------------------------------------------------
# process_discovered_videos tests
# ---------------------------------------------------------------------------


class TestProcessDiscoveredVideos:
    def test_process_discovered_success(self, mocker, engine, settings):
        """DISCOVERED -> DOWNLOADING -> DOWNLOADED on success."""
        with Session(engine) as session:
            content = Content(
                video_id="success001",
                channel_id="UCtest123",
                title="Success Video",
                video_url="https://www.youtube.com/watch?v=success001",
                status=ContentStatus.DISCOVERED,
            )
            session.add(content)
            session.commit()

        meta = dict(SAMPLE_METADATA, id="success001", duration=120)
        mocker.patch("crosspost.downloader.get_video_metadata", return_value=meta)
        mocker.patch(
            "crosspost.downloader.download_video",
            return_value={"id": "success001", "requested_downloads": [{"filepath": "/tmp/success001.mp4"}]},
        )

        count = process_discovered_videos(engine, settings)
        assert count == 1

        with Session(engine) as session:
            content = session.exec(sqlselect(Content).where(Content.video_id == "success001")).one()
            assert content.status == ContentStatus.DOWNLOADED
            assert content.downloaded_at is not None

    def test_process_discovered_too_long(self, mocker, engine, settings):
        """Video exceeding max_duration stays DISCOVERED and is not downloaded."""
        with Session(engine) as session:
            content = Content(
                video_id="toolong001",
                channel_id="UCtest123",
                title="Too Long Video",
                video_url="https://www.youtube.com/watch?v=toolong001",
                status=ContentStatus.DISCOVERED,
            )
            session.add(content)
            session.commit()

        meta = dict(SAMPLE_METADATA, id="toolong001", duration=600)
        mocker.patch("crosspost.downloader.get_video_metadata", return_value=meta)
        mock_download = mocker.patch("crosspost.downloader.download_video")

        count = process_discovered_videos(engine, settings)
        assert count == 0
        mock_download.assert_not_called()

        with Session(engine) as session:
            content = session.exec(sqlselect(Content).where(Content.video_id == "toolong001")).one()
            assert content.status == ContentStatus.DISCOVERED

    def test_process_discovered_error(self, mocker, engine, settings):
        """Download failure transitions Content to FAILED with error_message."""
        with Session(engine) as session:
            content = Content(
                video_id="errfail001",
                channel_id="UCtest123",
                title="Failing Video",
                video_url="https://www.youtube.com/watch?v=errfail001",
                status=ContentStatus.DISCOVERED,
            )
            session.add(content)
            session.commit()

        meta = dict(SAMPLE_METADATA, id="errfail001", duration=120)
        mocker.patch("crosspost.downloader.get_video_metadata", return_value=meta)
        mocker.patch("crosspost.downloader.download_video", side_effect=Exception("Network failure"))

        count = process_discovered_videos(engine, settings)
        assert count == 0

        with Session(engine) as session:
            content = session.exec(sqlselect(Content).where(Content.video_id == "errfail001")).one()
            assert content.status == ContentStatus.FAILED
            assert content.error_message is not None
            assert content.failed_at is not None

    def test_process_discovered_metadata_failure(self, mocker, engine, settings):
        """Metadata retrieval failure transitions video to FAILED."""
        with Session(engine) as session:
            content = Content(
                video_id="nometa001",
                channel_id="UCtest123",
                title="No Metadata Video",
                video_url="https://www.youtube.com/watch?v=nometa001",
                status=ContentStatus.DISCOVERED,
            )
            session.add(content)
            session.commit()

        mocker.patch("crosspost.downloader.get_video_metadata", return_value=None)

        count = process_discovered_videos(engine, settings)
        assert count == 0

        with Session(engine) as session:
            content = session.exec(sqlselect(Content).where(Content.video_id == "nometa001")).one()
            assert content.status == ContentStatus.FAILED

    def test_process_discovered_updates_duration(self, mocker, engine, settings):
        """Duration field is updated from metadata."""
        with Session(engine) as session:
            content = Content(
                video_id="durtest001",
                channel_id="UCtest123",
                title="Duration Test",
                video_url="https://www.youtube.com/watch?v=durtest001",
                status=ContentStatus.DISCOVERED,
                duration=0,
            )
            session.add(content)
            session.commit()

        meta = dict(SAMPLE_METADATA, id="durtest001", duration=95)
        mocker.patch("crosspost.downloader.get_video_metadata", return_value=meta)
        mocker.patch(
            "crosspost.downloader.download_video",
            return_value={"id": "durtest001", "requested_downloads": []},
        )

        process_discovered_videos(engine, settings)

        with Session(engine) as session:
            content = session.exec(sqlselect(Content).where(Content.video_id == "durtest001")).one()
            assert content.duration == 95

    def test_process_discovered_returns_count(self, mocker, engine, settings):
        """Returns the number of successfully downloaded videos."""
        with Session(engine) as session:
            for i in range(3):
                content = Content(
                    video_id=f"batch{i:03d}",
                    channel_id="UCtest123",
                    title=f"Batch Video {i}",
                    video_url=f"https://www.youtube.com/watch?v=batch{i:03d}",
                    status=ContentStatus.DISCOVERED,
                )
                session.add(content)
            session.commit()

        meta = dict(SAMPLE_METADATA, duration=60)
        mocker.patch("crosspost.downloader.get_video_metadata", return_value=meta)
        mocker.patch(
            "crosspost.downloader.download_video",
            return_value={"id": "batchX", "requested_downloads": []},
        )

        count = process_discovered_videos(engine, settings)
        assert count == 3

    def test_process_discovered_no_items(self, engine, settings):
        """Returns 0 when no DISCOVERED items exist."""
        count = process_discovered_videos(engine, settings)
        assert count == 0
