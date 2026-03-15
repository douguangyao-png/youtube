"""Translation module for subtitle and metadata translation.

Handles two translation workflows:
1. Subtitle translation: DeepL batch API for SRT files (EN -> ZH) with OpenCC t2s
2. Metadata translation: Claude Haiku 4.5 for platform-specific titles and descriptions
"""

import logging
from pathlib import Path

import anthropic
import deepl
import opencc
import srt

logger = logging.getLogger(__name__)


# Platform-specific system prompts for title translation via Claude Haiku 4.5
# Each prompt guides the LLM to re-create (not directly translate) the title
# in a style appropriate for the target platform.
PLATFORM_PROMPTS: dict[str, str] = {
    "toutiao": (
        "你是今日头条的内容编辑。将以下英文视频标题改写为中文，"
        "采用新闻资讯风格，简洁有力，约30个汉字以内。"
        "不要直译，要根据头条平台的阅读习惯重新创作标题。"
        "只输出中文标题，不要加引号或其他说明。"
    ),
    "baijiahao": (
        "你是百家号的内容编辑。将以下英文视频标题改写为中文，"
        "采用正式、SEO友好的风格，适合搜索引擎收录，约30个汉字以内。"
        "不要直译，要根据百家号平台的SEO规范重新创作标题。"
        "只输出中文标题，不要加引号或其他说明。"
    ),
}

# System prompt for description condensation/rewriting
_DESCRIPTION_PROMPT = (
    "将以下英文视频描述浓缩改写为中文，保留核心信息，"
    "适合中国视频平台的描述风格，简洁明了。"
    "只输出中文描述，不要加引号或其他说明。"
)


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


def translate_metadata(
    title: str, description: str, platform: str, api_key: str
) -> dict:
    """Translate video title and description for a specific Chinese platform.

    Uses Claude Haiku 4.5 to re-create (not directly translate) the title and
    description in a style appropriate for the target platform.

    Args:
        title: Original English video title.
        description: Original English video description.
        platform: Target platform key ("toutiao" or "baijiahao").
        api_key: Anthropic API key.

    Returns:
        Dict with "title" and "description" keys containing Chinese text.

    Raises:
        KeyError: If platform is not in PLATFORM_PROMPTS.
    """
    # Raise KeyError for unknown platforms (before creating client)
    system_prompt = PLATFORM_PROMPTS[platform]

    client = anthropic.Anthropic(api_key=api_key)

    # Translate title with platform-specific prompt
    title_response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=100,
        system=system_prompt,
        messages=[{"role": "user", "content": title}],
    )
    translated_title = title_response.content[0].text

    # Translate/condense description
    desc_response = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        system=_DESCRIPTION_PROMPT,
        messages=[{"role": "user", "content": description}],
    )
    translated_desc = desc_response.content[0].text

    logger.info("Metadata translated for platform=%s", platform)

    return {"title": translated_title, "description": translated_desc}
