"""Tests for processing pipeline orchestrator."""

import json
from datetime import datetime
from unittest.mock import MagicMock, call, patch

import pytest
from sqlmodel import Session, create_engine, select

from crosspost.config import AppSettings, DownloadConfig, ProcessingConfig, ScheduleConfig
from crosspost.database import init_db
from crosspost.models import Content, ContentStatus


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def in_memory_engine():
    """In-memory SQLite engine with tables created."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_db(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def settings():
    """AppSettings with processing config for tests."""
    return AppSettings(
        channels=[],
        download=DownloadConfig(output_dir="/tmp/test_downloads"),
        processing=ProcessingConfig(
            output_dir="/tmp/test_processed",
            deepl_auth_key="fake-deepl-key",
            anthropic_api_key="fake-anthropic-key",
            max_retries=2,
        ),
        schedule=ScheduleConfig(poll_interval_minutes=5),
        database_url="sqlite:///:memory:",
    )


def _make_downloaded_content(video_id="abc123", **overrides):
    """Create a Content row in DOWNLOADED state."""
    defaults = dict(
        video_id=video_id,
        channel_id="UC_test",
        title="Test Video",
        description="A test video description",
        video_url="https://youtube.com/watch?v=" + video_id,
        status=ContentStatus.DOWNLOADED,
        video_path="/tmp/downloads/" + video_id + ".mp4",
    )
    defaults.update(overrides)
    return Content(**defaults)


# ---------------------------------------------------------------------------
# Task 1: process_content -- parallel transcode + ASR
# ---------------------------------------------------------------------------


@patch("crosspost.processor.transcribe_to_srt")
@patch("crosspost.processor.transcode_to_h264")
@patch("crosspost.processor.probe_video")
@patch("crosspost.processor.translate_metadata")
@patch("crosspost.processor.translate_srt")
@patch("crosspost.processor.burn_subtitles")
@patch("crosspost.processor.build_bilingual_ass")
def test_process_content_runs_transcode_and_asr_in_parallel(
    mock_ass, mock_burn, mock_translate_srt, mock_translate_meta,
    mock_probe, mock_transcode, mock_transcribe,
    in_memory_engine, settings,
):
    """process_content runs transcode and ASR via ThreadPoolExecutor."""
    mock_transcode.return_value = "/tmp/test_processed/abc123_transcoded.mp4"
    mock_transcribe.return_value = "/tmp/test_processed/abc123_en.srt"
    mock_translate_srt.return_value = "/tmp/test_processed/abc123_zh.srt"
    mock_probe.return_value = {"width": 1920, "height": 1080, "bit_rate": "5000000"}
    mock_ass.return_value = "/tmp/test_processed/abc123_bilingual.ass"
    mock_burn.return_value = "/tmp/test_processed/abc123_final.mp4"
    mock_translate_meta.return_value = {"title": "zh title", "description": "zh desc"}

    with Session(in_memory_engine) as session:
        content = _make_downloaded_content()
        session.add(content)
        session.commit()

    from crosspost.processor import _process_single
    _process_single(in_memory_engine, settings, "abc123")

    mock_transcode.assert_called_once()
    mock_transcribe.assert_called_once()


@patch("crosspost.processor.transcribe_to_srt")
@patch("crosspost.processor.transcode_to_h264")
@patch("crosspost.processor.probe_video")
@patch("crosspost.processor.translate_metadata")
@patch("crosspost.processor.translate_srt")
@patch("crosspost.processor.burn_subtitles")
@patch("crosspost.processor.build_bilingual_ass")
def test_process_content_skips_transcode_if_already_done(
    mock_ass, mock_burn, mock_translate_srt, mock_translate_meta,
    mock_probe, mock_transcode, mock_transcribe,
    in_memory_engine, settings,
):
    """Idempotency: skip transcode if processed_video_path already set."""
    mock_transcribe.return_value = "/tmp/test_processed/abc123_en.srt"
    mock_translate_srt.return_value = "/tmp/test_processed/abc123_zh.srt"
    mock_probe.return_value = {"width": 1920, "height": 1080, "bit_rate": "5000000"}
    mock_ass.return_value = "/tmp/test_processed/abc123_bilingual.ass"
    mock_burn.return_value = "/tmp/test_processed/abc123_final.mp4"
    mock_translate_meta.return_value = {"title": "zh title", "description": "zh desc"}

    with Session(in_memory_engine) as session:
        content = _make_downloaded_content(
            processed_video_path="/tmp/test_processed/abc123_transcoded.mp4"
        )
        session.add(content)
        session.commit()

    from crosspost.processor import _process_single
    _process_single(in_memory_engine, settings, "abc123")

    mock_transcode.assert_not_called()


@patch("crosspost.processor.transcribe_to_srt")
@patch("crosspost.processor.transcode_to_h264")
@patch("crosspost.processor.probe_video")
@patch("crosspost.processor.translate_metadata")
@patch("crosspost.processor.translate_srt")
@patch("crosspost.processor.burn_subtitles")
@patch("crosspost.processor.build_bilingual_ass")
def test_process_content_skips_asr_if_already_done(
    mock_ass, mock_burn, mock_translate_srt, mock_translate_meta,
    mock_probe, mock_transcode, mock_transcribe,
    in_memory_engine, settings,
):
    """Idempotency: skip ASR if srt_path already set."""
    mock_transcode.return_value = "/tmp/test_processed/abc123_transcoded.mp4"
    mock_translate_srt.return_value = "/tmp/test_processed/abc123_zh.srt"
    mock_probe.return_value = {"width": 1920, "height": 1080, "bit_rate": "5000000"}
    mock_ass.return_value = "/tmp/test_processed/abc123_bilingual.ass"
    mock_burn.return_value = "/tmp/test_processed/abc123_final.mp4"
    mock_translate_meta.return_value = {"title": "zh title", "description": "zh desc"}

    with Session(in_memory_engine) as session:
        content = _make_downloaded_content(
            srt_path="/tmp/test_processed/abc123_en.srt"
        )
        session.add(content)
        session.commit()

    from crosspost.processor import _process_single
    _process_single(in_memory_engine, settings, "abc123")

    mock_transcribe.assert_not_called()


@patch("crosspost.processor.transcribe_to_srt")
@patch("crosspost.processor.transcode_to_h264")
@patch("crosspost.processor.probe_video")
@patch("crosspost.processor.translate_metadata")
@patch("crosspost.processor.translate_srt")
@patch("crosspost.processor.burn_subtitles")
@patch("crosspost.processor.build_bilingual_ass")
def test_process_content_skips_subtitle_translation_if_already_done(
    mock_ass, mock_burn, mock_translate_srt, mock_translate_meta,
    mock_probe, mock_transcode, mock_transcribe,
    in_memory_engine, settings,
):
    """Idempotency: skip subtitle translation if translated_srt_path already set."""
    mock_transcode.return_value = "/tmp/test_processed/abc123_transcoded.mp4"
    mock_transcribe.return_value = "/tmp/test_processed/abc123_en.srt"
    mock_probe.return_value = {"width": 1920, "height": 1080, "bit_rate": "5000000"}
    mock_ass.return_value = "/tmp/test_processed/abc123_bilingual.ass"
    mock_burn.return_value = "/tmp/test_processed/abc123_final.mp4"
    mock_translate_meta.return_value = {"title": "zh title", "description": "zh desc"}

    with Session(in_memory_engine) as session:
        content = _make_downloaded_content(
            translated_srt_path="/tmp/test_processed/abc123_zh.srt"
        )
        session.add(content)
        session.commit()

    from crosspost.processor import _process_single
    _process_single(in_memory_engine, settings, "abc123")

    mock_translate_srt.assert_not_called()


@patch("crosspost.processor.transcribe_to_srt")
@patch("crosspost.processor.transcode_to_h264")
@patch("crosspost.processor.probe_video")
@patch("crosspost.processor.translate_metadata")
@patch("crosspost.processor.translate_srt")
@patch("crosspost.processor.burn_subtitles")
@patch("crosspost.processor.build_bilingual_ass")
def test_process_content_skips_burnin_if_ass_already_done(
    mock_ass, mock_burn, mock_translate_srt, mock_translate_meta,
    mock_probe, mock_transcode, mock_transcribe,
    in_memory_engine, settings,
):
    """Idempotency: skip burn-in if ass_path already set."""
    mock_transcode.return_value = "/tmp/test_processed/abc123_transcoded.mp4"
    mock_transcribe.return_value = "/tmp/test_processed/abc123_en.srt"
    mock_translate_srt.return_value = "/tmp/test_processed/abc123_zh.srt"
    mock_translate_meta.return_value = {"title": "zh title", "description": "zh desc"}

    with Session(in_memory_engine) as session:
        content = _make_downloaded_content(
            ass_path="/tmp/test_processed/abc123_bilingual.ass",
            processed_video_path="/tmp/test_processed/abc123_final.mp4",
        )
        session.add(content)
        session.commit()

    from crosspost.processor import _process_single
    _process_single(in_memory_engine, settings, "abc123")

    mock_ass.assert_not_called()
    mock_burn.assert_not_called()


@patch("crosspost.processor.transcribe_to_srt")
@patch("crosspost.processor.transcode_to_h264")
@patch("crosspost.processor.probe_video")
@patch("crosspost.processor.translate_metadata")
@patch("crosspost.processor.translate_srt")
@patch("crosspost.processor.burn_subtitles")
@patch("crosspost.processor.build_bilingual_ass")
def test_process_content_music_video_skips_subtitles(
    mock_ass, mock_burn, mock_translate_srt, mock_translate_meta,
    mock_probe, mock_transcode, mock_transcribe,
    in_memory_engine, settings,
):
    """Music video (empty srt) skips translation and burn-in, still transcodes."""
    mock_transcode.return_value = "/tmp/test_processed/abc123_transcoded.mp4"
    mock_transcribe.return_value = ""  # music video
    mock_translate_meta.return_value = {"title": "zh title", "description": "zh desc"}

    with Session(in_memory_engine) as session:
        content = _make_downloaded_content()
        session.add(content)
        session.commit()

    from crosspost.processor import _process_single
    _process_single(in_memory_engine, settings, "abc123")

    mock_transcode.assert_called_once()
    mock_translate_srt.assert_not_called()
    mock_ass.assert_not_called()
    mock_burn.assert_not_called()
    mock_translate_meta.assert_called()  # metadata still translated


@patch("crosspost.processor.transcribe_to_srt")
@patch("crosspost.processor.transcode_to_h264")
@patch("crosspost.processor.probe_video")
@patch("crosspost.processor.translate_metadata")
@patch("crosspost.processor.translate_srt")
@patch("crosspost.processor.burn_subtitles")
@patch("crosspost.processor.build_bilingual_ass")
def test_process_content_writes_paths_before_status_advance(
    mock_ass, mock_burn, mock_translate_srt, mock_translate_meta,
    mock_probe, mock_transcode, mock_transcribe,
    in_memory_engine, settings,
):
    """Artifact paths written to Content BEFORE status transitions."""
    mock_transcode.return_value = "/tmp/test_processed/abc123_transcoded.mp4"
    mock_transcribe.return_value = "/tmp/test_processed/abc123_en.srt"
    mock_translate_srt.return_value = "/tmp/test_processed/abc123_zh.srt"
    mock_probe.return_value = {"width": 1920, "height": 1080, "bit_rate": "5000000"}
    mock_ass.return_value = "/tmp/test_processed/abc123_bilingual.ass"
    mock_burn.return_value = "/tmp/test_processed/abc123_final.mp4"
    mock_translate_meta.return_value = {"title": "zh title", "description": "zh desc"}

    with Session(in_memory_engine) as session:
        content = _make_downloaded_content()
        session.add(content)
        session.commit()

    from crosspost.processor import _process_single
    _process_single(in_memory_engine, settings, "abc123")

    with Session(in_memory_engine) as session:
        content = session.exec(
            select(Content).where(Content.video_id == "abc123")
        ).one()
        assert content.processed_video_path is not None
        assert content.srt_path is not None
        assert content.translated_srt_path is not None
        assert content.ass_path is not None
        assert content.status == ContentStatus.TRANSLATED


@patch("crosspost.processor.transcribe_to_srt")
@patch("crosspost.processor.transcode_to_h264")
@patch("crosspost.processor.probe_video")
@patch("crosspost.processor.translate_metadata")
@patch("crosspost.processor.translate_srt")
@patch("crosspost.processor.burn_subtitles")
@patch("crosspost.processor.build_bilingual_ass")
def test_process_content_transitions_to_processed(
    mock_ass, mock_burn, mock_translate_srt, mock_translate_meta,
    mock_probe, mock_transcode, mock_transcribe,
    in_memory_engine, settings,
):
    """Status transitions: DOWNLOADED -> PROCESSED with processed_at set."""
    mock_transcode.return_value = "/tmp/test_processed/abc123_transcoded.mp4"
    mock_transcribe.return_value = "/tmp/test_processed/abc123_en.srt"
    mock_translate_srt.return_value = "/tmp/test_processed/abc123_zh.srt"
    mock_probe.return_value = {"width": 1920, "height": 1080, "bit_rate": "5000000"}
    mock_ass.return_value = "/tmp/test_processed/abc123_bilingual.ass"
    mock_burn.return_value = "/tmp/test_processed/abc123_final.mp4"
    mock_translate_meta.return_value = {"title": "zh title", "description": "zh desc"}

    with Session(in_memory_engine) as session:
        content = _make_downloaded_content()
        session.add(content)
        session.commit()

    from crosspost.processor import _process_single
    _process_single(in_memory_engine, settings, "abc123")

    with Session(in_memory_engine) as session:
        content = session.exec(
            select(Content).where(Content.video_id == "abc123")
        ).one()
        assert content.processed_at is not None


@patch("crosspost.processor.transcribe_to_srt")
@patch("crosspost.processor.transcode_to_h264")
@patch("crosspost.processor.probe_video")
@patch("crosspost.processor.translate_metadata")
@patch("crosspost.processor.translate_srt")
@patch("crosspost.processor.burn_subtitles")
@patch("crosspost.processor.build_bilingual_ass")
def test_process_content_transitions_to_translated(
    mock_ass, mock_burn, mock_translate_srt, mock_translate_meta,
    mock_probe, mock_transcode, mock_transcribe,
    in_memory_engine, settings,
):
    """Status transitions: PROCESSED -> TRANSLATED with translated_at set."""
    mock_transcode.return_value = "/tmp/test_processed/abc123_transcoded.mp4"
    mock_transcribe.return_value = "/tmp/test_processed/abc123_en.srt"
    mock_translate_srt.return_value = "/tmp/test_processed/abc123_zh.srt"
    mock_probe.return_value = {"width": 1920, "height": 1080, "bit_rate": "5000000"}
    mock_ass.return_value = "/tmp/test_processed/abc123_bilingual.ass"
    mock_burn.return_value = "/tmp/test_processed/abc123_final.mp4"
    mock_translate_meta.return_value = {"title": "zh title", "description": "zh desc"}

    with Session(in_memory_engine) as session:
        content = _make_downloaded_content()
        session.add(content)
        session.commit()

    from crosspost.processor import _process_single
    _process_single(in_memory_engine, settings, "abc123")

    with Session(in_memory_engine) as session:
        content = session.exec(
            select(Content).where(Content.video_id == "abc123")
        ).one()
        assert content.status == ContentStatus.TRANSLATED
        assert content.translated_at is not None


@patch("crosspost.processor.transcribe_to_srt")
@patch("crosspost.processor.transcode_to_h264")
@patch("crosspost.processor.probe_video")
@patch("crosspost.processor.translate_metadata")
@patch("crosspost.processor.translate_srt")
@patch("crosspost.processor.burn_subtitles")
@patch("crosspost.processor.build_bilingual_ass")
def test_process_content_stores_platform_metadata_json(
    mock_ass, mock_burn, mock_translate_srt, mock_translate_meta,
    mock_probe, mock_transcode, mock_transcribe,
    in_memory_engine, settings,
):
    """platform_metadata stored as JSON with toutiao and baijiahao entries."""
    mock_transcode.return_value = "/tmp/test_processed/abc123_transcoded.mp4"
    mock_transcribe.return_value = "/tmp/test_processed/abc123_en.srt"
    mock_translate_srt.return_value = "/tmp/test_processed/abc123_zh.srt"
    mock_probe.return_value = {"width": 1920, "height": 1080, "bit_rate": "5000000"}
    mock_ass.return_value = "/tmp/test_processed/abc123_bilingual.ass"
    mock_burn.return_value = "/tmp/test_processed/abc123_final.mp4"
    mock_translate_meta.return_value = {"title": "zh title", "description": "zh desc"}

    with Session(in_memory_engine) as session:
        content = _make_downloaded_content()
        session.add(content)
        session.commit()

    from crosspost.processor import _process_single
    _process_single(in_memory_engine, settings, "abc123")

    with Session(in_memory_engine) as session:
        content = session.exec(
            select(Content).where(Content.video_id == "abc123")
        ).one()
        meta = json.loads(content.platform_metadata)
        assert "toutiao" in meta
        assert "baijiahao" in meta
        assert meta["toutiao"]["title"] == "zh title"


@patch("crosspost.processor.transcribe_to_srt")
@patch("crosspost.processor.transcode_to_h264")
@patch("crosspost.processor.probe_video")
@patch("crosspost.processor.translate_metadata")
@patch("crosspost.processor.translate_srt")
@patch("crosspost.processor.burn_subtitles")
@patch("crosspost.processor.build_bilingual_ass")
def test_process_content_marks_failed_after_retries_exhausted(
    mock_ass, mock_burn, mock_translate_srt, mock_translate_meta,
    mock_probe, mock_transcode, mock_transcribe,
    in_memory_engine, settings,
):
    """Content marked FAILED with error_message after max_retries exhausted."""
    mock_transcode.side_effect = RuntimeError("FFmpeg crashed")

    with Session(in_memory_engine) as session:
        content = _make_downloaded_content()
        session.add(content)
        session.commit()

    from crosspost.processor import _process_single
    _process_single(in_memory_engine, settings, "abc123")

    with Session(in_memory_engine) as session:
        content = session.exec(
            select(Content).where(Content.video_id == "abc123")
        ).one()
        assert content.status == ContentStatus.FAILED
        assert "FFmpeg crashed" in content.error_message


@patch("crosspost.processor.transcribe_to_srt")
@patch("crosspost.processor.transcode_to_h264")
@patch("crosspost.processor.probe_video")
@patch("crosspost.processor.translate_metadata")
@patch("crosspost.processor.translate_srt")
@patch("crosspost.processor.burn_subtitles")
@patch("crosspost.processor.build_bilingual_ass")
def test_process_downloaded_videos_queries_downloaded_content(
    mock_ass, mock_burn, mock_translate_srt, mock_translate_meta,
    mock_probe, mock_transcode, mock_transcribe,
    in_memory_engine, settings,
):
    """process_downloaded_videos queries DOWNLOADED content and processes each."""
    mock_transcode.return_value = "/tmp/test_processed/vid1_transcoded.mp4"
    mock_transcribe.return_value = "/tmp/test_processed/vid1_en.srt"
    mock_translate_srt.return_value = "/tmp/test_processed/vid1_zh.srt"
    mock_probe.return_value = {"width": 1920, "height": 1080, "bit_rate": "5000000"}
    mock_ass.return_value = "/tmp/test_processed/vid1_bilingual.ass"
    mock_burn.return_value = "/tmp/test_processed/vid1_final.mp4"
    mock_translate_meta.return_value = {"title": "zh", "description": "zh"}

    with Session(in_memory_engine) as session:
        session.add(_make_downloaded_content(video_id="vid1"))
        session.add(Content(
            video_id="vid2", channel_id="UC_test",
            video_url="https://youtube.com/watch?v=vid2",
            status=ContentStatus.DISCOVERED,
        ))
        session.commit()

    from crosspost.processor import process_downloaded_videos
    count = process_downloaded_videos(in_memory_engine, settings)

    assert count == 1
    with Session(in_memory_engine) as session:
        vid2 = session.exec(
            select(Content).where(Content.video_id == "vid2")
        ).one()
        assert vid2.status == ContentStatus.DISCOVERED


@patch("crosspost.processor.transcribe_to_srt")
@patch("crosspost.processor.transcode_to_h264")
@patch("crosspost.processor.probe_video")
@patch("crosspost.processor.translate_metadata")
@patch("crosspost.processor.translate_srt")
@patch("crosspost.processor.burn_subtitles")
@patch("crosspost.processor.build_bilingual_ass")
def test_future_result_propagates_exceptions(
    mock_ass, mock_burn, mock_translate_srt, mock_translate_meta,
    mock_probe, mock_transcode, mock_transcribe,
    in_memory_engine, settings,
):
    """ThreadPoolExecutor future.result() propagates exceptions (Pitfall 8)."""
    mock_transcode.side_effect = RuntimeError("transcode boom")
    mock_transcribe.return_value = "/tmp/test_processed/abc123_en.srt"

    with Session(in_memory_engine) as session:
        content = _make_downloaded_content()
        session.add(content)
        session.commit()

    from crosspost.processor import _process_single
    _process_single(in_memory_engine, settings, "abc123")

    with Session(in_memory_engine) as session:
        content = session.exec(
            select(Content).where(Content.video_id == "abc123")
        ).one()
        assert content.status == ContentStatus.FAILED
        assert "transcode boom" in content.error_message
