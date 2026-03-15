"""Bilingual ASS subtitle assembly and FFmpeg burn-in.

Operator must place NotoSansCJKsc-Bold.otf in src/crosspost/assets/fonts/ —
download from Google Fonts (SIL OFL 1.1 license).
"""

import subprocess

import pysubs2
from pysubs2 import Color, SSAEvent, SSAFile, SSAStyle

from loguru import logger


def build_bilingual_ass(
    en_srt_path: str,
    zh_srt_path: str,
    output_ass_path: str,
    video_height: int,
    is_vertical: bool,
) -> str:
    """Build a bilingual ASS subtitle file from English and Chinese SRT files.

    Creates a styled ASS file with Chinese subtitles above English,
    using Noto Sans CJK SC font on a semi-transparent black background bar.

    Args:
        en_srt_path: Path to English SRT file. Empty string to skip.
        zh_srt_path: Path to Chinese SRT file. Empty string to skip.
        output_ass_path: Path for output ASS file.
        video_height: Video height in pixels (for margin calculation).
        is_vertical: True for vertical/Shorts videos (20% margin), False for horizontal (8%).

    Returns:
        output_ass_path on success, or empty string if both inputs are empty (music video).
    """
    if not en_srt_path and not zh_srt_path:
        logger.info("Both SRT paths empty (music video) — skipping subtitle generation")
        return ""

    # Font sizes per orientation
    zh_fontsize = 20 if is_vertical else 24
    en_fontsize = 15 if is_vertical else 18

    # Margin calculation
    margin_pct = 0.20 if is_vertical else 0.08
    base_marginv = int(video_height * margin_pct)
    zh_marginv = base_marginv + en_fontsize + 6  # Chinese above English
    en_marginv = base_marginv

    # Semi-transparent black background: alpha=102 for 60% opacity
    # pysubs2 alpha: 0=opaque, 255=transparent
    back_color = Color(0, 0, 0, 102)
    primary_color = Color(255, 255, 255, 0)  # Opaque white

    subs = SSAFile()
    subs.info["WrapStyle"] = "0"

    # Chinese style
    subs.styles["Chinese"] = SSAStyle(
        fontname="Noto Sans CJK SC",
        fontsize=zh_fontsize,
        bold=True,
        primarycolor=primary_color,
        backcolor=back_color,
        borderstyle=3,
        outline=0,
        shadow=0,
        alignment=2,
        marginv=zh_marginv,
    )

    # English style
    subs.styles["English"] = SSAStyle(
        fontname="Noto Sans CJK SC",
        fontsize=en_fontsize,
        bold=False,
        primarycolor=primary_color,
        backcolor=back_color,
        borderstyle=3,
        outline=0,
        shadow=0,
        alignment=2,
        marginv=en_marginv,
    )

    # Load SRT files
    en_events = pysubs2.load(en_srt_path).events if en_srt_path else []
    zh_events = pysubs2.load(zh_srt_path).events if zh_srt_path else []

    # Create paired events
    for i in range(max(len(en_events), len(zh_events))):
        if i < len(zh_events):
            zh_ev = zh_events[i]
            subs.events.append(SSAEvent(
                start=zh_ev.start,
                end=zh_ev.end,
                text=zh_ev.text,
                style="Chinese",
            ))
        if i < len(en_events):
            en_ev = en_events[i]
            subs.events.append(SSAEvent(
                start=en_ev.start,
                end=en_ev.end,
                text=en_ev.text,
                style="English",
            ))

    subs.save(output_ass_path)
    logger.info("Built bilingual ASS: {} ({} events)", output_ass_path, len(subs.events))
    return output_ass_path


def burn_subtitles(
    video_path: str,
    ass_path: str,
    output_path: str,
    fonts_dir: str,
) -> str:
    """Burn ASS subtitles into video using FFmpeg subtitles filter.

    Args:
        video_path: Path to input video.
        ass_path: Path to ASS subtitle file.
        output_path: Path for output video with burned-in subtitles.
        fonts_dir: Path to directory containing font files (e.g., NotoSansCJKsc-Bold.otf).

    Returns:
        output_path on success.

    Raises:
        subprocess.CalledProcessError: If FFmpeg fails.
        subprocess.TimeoutExpired: If burn-in exceeds 900 seconds.
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vf", f"subtitles={ass_path}:fontsdir={fonts_dir}",
        "-c:v", "libx264",
        "-crf", "20",
        "-preset", "medium",
        "-c:a", "copy",
        output_path,
    ]

    logger.info("Burning subtitles: {} + {} -> {}", video_path, ass_path, output_path)
    subprocess.run(cmd, capture_output=True, check=True, timeout=900)
    logger.info("Subtitle burn-in complete: {}", output_path)
    return output_path
