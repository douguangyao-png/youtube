"""faster-whisper ASR transcription to SRT subtitle files."""

from pathlib import Path

import pysubs2
from faster_whisper import WhisperModel
from loguru import logger


def transcribe_to_srt(
    video_path: str,
    output_srt_path: str,
    model_size: str = "medium",
) -> str:
    """Transcribe English speech from video to SRT subtitle file.

    Uses faster-whisper with INT8 quantization on CPU. VAD filter
    is enabled to skip silence segments.

    Pure music / no-dialogue videos return empty string (not an error).

    Args:
        video_path: Path to source video file.
        output_srt_path: Path for output SRT file.
        model_size: Whisper model size (default: "medium").

    Returns:
        output_srt_path on success, or empty string if no speech detected.
    """
    # Ensure output directory exists
    Path(output_srt_path).parent.mkdir(parents=True, exist_ok=True)

    logger.info("Loading WhisperModel (size={}, device=cpu, int8)", model_size)
    model = WhisperModel(model_size, device="cpu", compute_type="int8")

    logger.info("Transcribing: {}", video_path)
    segments, info = model.transcribe(
        video_path,
        language="en",
        beam_size=5,
        vad_filter=True,
        vad_parameters={"threshold": 0.5},
    )

    # Consume the generator
    segment_list = list(segments)

    if not segment_list:
        logger.info("No speech segments found (pure music?) — returning empty string")
        return ""

    logger.info("Found {} speech segments", len(segment_list))

    # Convert to pysubs2 whisper format
    whisper_segments = [
        {"start": s.start, "end": s.end, "text": s.text.strip()}
        for s in segment_list
    ]

    subs = pysubs2.load_from_whisper(whisper_segments)
    subs.save(output_srt_path, format_="srt")

    logger.info("SRT saved: {}", output_srt_path)
    return output_srt_path
