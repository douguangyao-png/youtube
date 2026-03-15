"""FFmpeg probe and transcode functions for video processing."""

import json
import subprocess

from loguru import logger


def probe_video(video_path: str) -> dict:
    """Extract video stream info from a video file using ffprobe.

    Args:
        video_path: Path to the video file.

    Returns:
        Dict with keys: width, height, bit_rate, codec_name, r_frame_rate
        from the first video stream.

    Raises:
        subprocess.CalledProcessError: If ffprobe fails.
    """
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-select_streams", "v:0",
        video_path,
    ]
    logger.info("Probing video: {}", video_path)
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    logger.info(
        "Probe result: {}x{} {} @ {} bps",
        stream.get("width"),
        stream.get("height"),
        stream.get("codec_name"),
        stream.get("bit_rate"),
    )
    return stream


def transcode_to_h264(input_path: str, output_path: str, source_bitrate_kbps: int) -> str:
    """Transcode video to H.264 MP4 at up to 1080p.

    Uses dynamic CRF based on source bitrate:
    - CRF 20 for high quality sources (> 4000 kbps)
    - CRF 23 for lower bitrate sources (<= 4000 kbps)

    Never upscales below-1080p sources.

    Args:
        input_path: Path to source video file.
        output_path: Path for output H.264 MP4.
        source_bitrate_kbps: Source video bitrate in kbps for CRF selection.

    Returns:
        output_path on success.

    Raises:
        subprocess.CalledProcessError: If ffmpeg fails.
        subprocess.TimeoutExpired: If transcoding exceeds 600 seconds.
    """
    crf = "20" if source_bitrate_kbps > 4000 else "23"

    # Scale filter: downscale to 1080p max, never upscale.
    # -2 ensures width is divisible by 2.
    scale_filter = "scale=-2:'min(1080,ih)'"

    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-vf", scale_filter,
        "-c:v", "libx264",
        "-crf", crf,
        "-preset", "medium",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        output_path,
    ]

    logger.info(
        "Transcoding {} -> {} (CRF {}, scale {})",
        input_path, output_path, crf, scale_filter,
    )
    subprocess.run(cmd, capture_output=True, check=True, timeout=600)
    logger.info("Transcode complete: {}", output_path)
    return output_path
