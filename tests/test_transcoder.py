"""Tests for FFmpeg probe and transcode functions."""

import json
import subprocess
from unittest.mock import MagicMock, patch, call

import pytest

from crosspost.transcoder import probe_video, transcode_to_h264


# ---------------------------------------------------------------------------
# probe_video tests
# ---------------------------------------------------------------------------


class TestProbeVideo:
    """Tests for probe_video function."""

    def test_probe_returns_stream_info(self):
        """probe_video returns dict with width, height, bit_rate, codec_name."""
        fake_output = json.dumps(
            {
                "streams": [
                    {
                        "width": 1920,
                        "height": 1080,
                        "bit_rate": "5000000",
                        "codec_name": "h264",
                        "r_frame_rate": "30/1",
                    }
                ]
            }
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_output)
            result = probe_video("/tmp/video.mp4")

        assert result["width"] == 1920
        assert result["height"] == 1080
        assert result["bit_rate"] == "5000000"
        assert result["codec_name"] == "h264"

    def test_probe_raises_on_ffprobe_failure(self):
        """probe_video raises CalledProcessError on ffprobe failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, "ffprobe")
            with pytest.raises(subprocess.CalledProcessError):
                probe_video("/tmp/nonexistent.mp4")

    def test_probe_calls_ffprobe_with_correct_args(self):
        """probe_video calls ffprobe with JSON output and video stream selection."""
        fake_output = json.dumps(
            {"streams": [{"width": 1280, "height": 720, "bit_rate": "2000000", "codec_name": "h264"}]}
        )
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=fake_output)
            probe_video("/tmp/video.mp4")

        cmd = mock_run.call_args[0][0]
        assert "ffprobe" in cmd
        assert "-print_format" in cmd or "-of" in cmd
        assert "json" in cmd
        assert "-select_streams" in cmd
        assert "v:0" in cmd


# ---------------------------------------------------------------------------
# transcode_to_h264 tests
# ---------------------------------------------------------------------------


class TestTranscodeToH264:
    """Tests for transcode_to_h264 function."""

    def test_high_bitrate_uses_crf_20(self):
        """transcode_to_h264 uses CRF 20 when source bitrate > 4000 kbps."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            transcode_to_h264("/tmp/in.mp4", "/tmp/out.mp4", 5000)

        cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(cmd)
        assert "-crf" in cmd
        crf_idx = cmd.index("-crf")
        assert cmd[crf_idx + 1] == "20"

    def test_low_bitrate_uses_crf_23(self):
        """transcode_to_h264 uses CRF 23 when source bitrate <= 4000 kbps."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            transcode_to_h264("/tmp/in.mp4", "/tmp/out.mp4", 3000)

        cmd = mock_run.call_args[0][0]
        crf_idx = cmd.index("-crf")
        assert cmd[crf_idx + 1] == "23"

    def test_no_upscale_scale_filter(self):
        """transcode_to_h264 uses scale filter that does NOT upscale below-1080p sources."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            transcode_to_h264("/tmp/in.mp4", "/tmp/out.mp4", 3000)

        cmd = mock_run.call_args[0][0]
        cmd_str = " ".join(cmd)
        # Scale filter must reference min(1080,ih) or equivalent to avoid upscaling
        assert "-vf" in cmd
        vf_idx = cmd.index("-vf")
        scale_val = cmd[vf_idx + 1]
        assert "min" in scale_val and "1080" in scale_val

    def test_movflags_faststart(self):
        """transcode_to_h264 includes -movflags +faststart for web-compatible MP4."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            transcode_to_h264("/tmp/in.mp4", "/tmp/out.mp4", 5000)

        cmd = mock_run.call_args[0][0]
        assert "-movflags" in cmd
        movflags_idx = cmd.index("-movflags")
        assert cmd[movflags_idx + 1] == "+faststart"

    def test_timeout_600(self):
        """transcode_to_h264 sets timeout=600 on subprocess.run."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            transcode_to_h264("/tmp/in.mp4", "/tmp/out.mp4", 5000)

        kwargs = mock_run.call_args[1]
        assert kwargs.get("timeout") == 600

    def test_returns_output_path(self):
        """transcode_to_h264 returns the output_path on success."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = transcode_to_h264("/tmp/in.mp4", "/tmp/out.mp4", 5000)

        assert result == "/tmp/out.mp4"

    def test_overwrite_flag(self):
        """transcode_to_h264 includes -y flag to overwrite output."""
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            transcode_to_h264("/tmp/in.mp4", "/tmp/out.mp4", 5000)

        cmd = mock_run.call_args[0][0]
        assert "-y" in cmd
