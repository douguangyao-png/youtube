"""Translation module for subtitle and metadata translation.

Handles two translation workflows:
1. Subtitle translation: DeepL batch API for SRT files (EN -> ZH) with OpenCC t2s
2. Metadata translation: Claude Haiku 4.5 for platform-specific titles and descriptions
"""

import logging
from pathlib import Path

import deepl
import opencc
import srt

logger = logging.getLogger(__name__)


def translate_srt(input_srt_path: str, output_srt_path: str, auth_key: str) -> str:
    """Translate an English SRT file to Simplified Chinese.

    Uses DeepL for translation with OpenCC Traditional-to-Simplified conversion.
    All subtitle texts are sent in a single batch API call.

    Args:
        input_srt_path: Path to the English SRT file.
        output_srt_path: Path where the translated SRT will be written.
        auth_key: DeepL API authentication key.

    Returns:
        The output_srt_path on success.
    """
    # Parse input SRT
    input_text = Path(input_srt_path).read_text(encoding="utf-8")
    subtitles = list(srt.parse(input_text))

    # Extract all subtitle texts for batch translation
    texts = [sub.content for sub in subtitles]

    # Single batch DeepL API call (not per-line)
    translator = deepl.Translator(auth_key)
    results = translator.translate_text(
        texts,
        source_lang="EN",
        target_lang="ZH",
        split_sentences="nonewlines",
    )

    # Convert Traditional Chinese to Simplified Chinese via OpenCC
    converter = opencc.OpenCC("t2s")

    # Log billed characters for usage monitoring
    total_billed = sum(r.billed_characters for r in results)
    logger.info("DeepL translation: %d subtitles, %d billed characters", len(texts), total_billed)

    # Replace subtitle content with translated text
    for sub, result in zip(subtitles, results):
        sub.content = converter.convert(result.text)

    # Ensure output directory exists
    Path(output_srt_path).parent.mkdir(parents=True, exist_ok=True)

    # Write output SRT
    output_text = srt.compose(subtitles)
    Path(output_srt_path).write_text(output_text, encoding="utf-8")

    return output_srt_path
