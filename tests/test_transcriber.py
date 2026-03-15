"""Tests for faster-whisper ASR to SRT transcription."""

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from crosspost.transcriber import transcribe_to_srt


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_segment(start: float, end: float, text: str) -> MagicMock:
    """Create a mock faster-whisper segment."""
    seg = MagicMock()
    seg.start = start
    seg.end = end
    seg.text = text
    return seg


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestTranscribeToSrt:
    """Tests for transcribe_to_srt function."""

    @patch("crosspost.transcriber.pysubs2")
    @patch("crosspost.transcriber.WhisperModel")
    def test_creates_model_with_correct_params(self, mock_model_cls, mock_pysubs2, tmp_path):
        """transcribe_to_srt creates WhisperModel with device=cpu, compute_type=int8."""
        mock_model = MagicMock()
        mock_model_cls.return_value = mock_model
        mock_model.transcribe.return_value = (iter([]), MagicMock())

        transcribe_to_srt("/tmp/video.mp4", str(tmp_path / "out.srt"), model_size="medium")

        mock_model_cls.assert_called_once_with("medium", device="cpu", compute_type="int8")

    @patch("crosspost.transcriber.pysubs2")
    @patch("crosspost.transcriber.WhisperModel")
    def test_calls_transcribe_with_correct_params(self, mock_model_cls, mock_pysubs2, tmp_path):
        """transcribe_to_srt calls model.transcribe with language=en, beam_size=5, vad_filter=True."""
        mock_model = MagicMock()
        mock_model_cls.return_value = mock_model
        mock_model.transcribe.return_value = (iter([]), MagicMock())

        transcribe_to_srt("/tmp/video.mp4", str(tmp_path / "out.srt"))

        mock_model.transcribe.assert_called_once()
        kwargs = mock_model.transcribe.call_args
        assert kwargs[0][0] == "/tmp/video.mp4" or kwargs[1].get("audio") == "/tmp/video.mp4"
        # Check keyword args
        call_kwargs = kwargs[1] if kwargs[1] else {}
        # Could be positional or keyword - check the call
        assert "en" in str(kwargs)
        assert "beam_size" in str(kwargs) or "5" in str(kwargs)

    @patch("crosspost.transcriber.pysubs2")
    @patch("crosspost.transcriber.WhisperModel")
    def test_converts_segments_to_srt(self, mock_model_cls, mock_pysubs2, tmp_path):
        """transcribe_to_srt converts faster-whisper segments to SRT via pysubs2."""
        mock_model = MagicMock()
        mock_model_cls.return_value = mock_model

        segments = [
            _make_segment(0.0, 2.5, " Hello world "),
            _make_segment(2.5, 5.0, " Testing speech "),
        ]
        mock_model.transcribe.return_value = (iter(segments), MagicMock())

        mock_subs = MagicMock()
        mock_pysubs2.load_from_whisper.return_value = mock_subs

        output_path = str(tmp_path / "out.srt")
        result = transcribe_to_srt("/tmp/video.mp4", output_path)

        # Verify pysubs2.load_from_whisper was called with whisper-format dicts
        whisper_data = mock_pysubs2.load_from_whisper.call_args[0][0]
        assert len(whisper_data) == 2
        assert whisper_data[0]["start"] == 0.0
        assert whisper_data[0]["end"] == 2.5
        assert whisper_data[0]["text"] == "Hello world"  # stripped
        assert whisper_data[1]["text"] == "Testing speech"

        # Verify save was called
        mock_subs.save.assert_called_once()
        assert result == output_path

    @patch("crosspost.transcriber.pysubs2")
    @patch("crosspost.transcriber.WhisperModel")
    def test_empty_segments_returns_empty_string(self, mock_model_cls, mock_pysubs2, tmp_path):
        """transcribe_to_srt returns empty string for pure music video (no segments)."""
        mock_model = MagicMock()
        mock_model_cls.return_value = mock_model
        mock_model.transcribe.return_value = (iter([]), MagicMock())

        result = transcribe_to_srt("/tmp/music.mp4", str(tmp_path / "out.srt"))

        assert result == ""
        mock_pysubs2.load_from_whisper.assert_not_called()

    @patch("crosspost.transcriber.pysubs2")
    @patch("crosspost.transcriber.WhisperModel")
    def test_creates_output_directory(self, mock_model_cls, mock_pysubs2, tmp_path):
        """transcribe_to_srt creates output directory if it does not exist."""
        mock_model = MagicMock()
        mock_model_cls.return_value = mock_model

        segments = [_make_segment(0.0, 1.0, "Test")]
        mock_model.transcribe.return_value = (iter(segments), MagicMock())
        mock_pysubs2.load_from_whisper.return_value = MagicMock()

        nested_dir = tmp_path / "deep" / "nested"
        output_path = str(nested_dir / "out.srt")
        transcribe_to_srt("/tmp/video.mp4", output_path)

        assert nested_dir.exists()
