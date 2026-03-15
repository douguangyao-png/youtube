"""Tests for the translator module (DeepL subtitle + Claude metadata translation)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# --- SRT Translation Tests ---


SAMPLE_SRT = """\
1
00:00:01,000 --> 00:00:03,000
Hello world

2
00:00:04,000 --> 00:00:06,500
This is a test subtitle

3
00:00:07,000 --> 00:00:10,000
Thank you for watching
"""


class TestTranslateSrt:
    """Tests for translate_srt function."""

    def test_batch_call_sends_all_texts(self, tmp_path: Path) -> None:
        """translate_srt sends all subtitle texts in ONE batch call to DeepL."""
        input_srt = tmp_path / "input.srt"
        input_srt.write_text(SAMPLE_SRT)
        output_srt = tmp_path / "output" / "translated.srt"

        mock_result_1 = MagicMock(text="你好世界", billed_characters=5)
        mock_result_2 = MagicMock(text="这是测试字幕", billed_characters=6)
        mock_result_3 = MagicMock(text="感谢观看", billed_characters=4)

        with (
            patch("deepl.Translator") as mock_translator_cls,
            patch("opencc.OpenCC") as mock_opencc_cls,
        ):
            mock_translator = MagicMock()
            mock_translator_cls.return_value = mock_translator
            mock_translator.translate_text.return_value = [
                mock_result_1,
                mock_result_2,
                mock_result_3,
            ]

            mock_converter = MagicMock()
            mock_opencc_cls.return_value = mock_converter
            mock_converter.convert.side_effect = lambda x: x  # passthrough

            from crosspost.translator import translate_srt

            result = translate_srt(str(input_srt), str(output_srt), "fake-key")

        # Verify single batch call with all texts
        mock_translator.translate_text.assert_called_once()
        call_args = mock_translator.translate_text.call_args
        texts = call_args[0][0]
        assert len(texts) == 3
        assert texts[0] == "Hello world"
        assert texts[1] == "This is a test subtitle"
        assert texts[2] == "Thank you for watching"

    def test_deepl_params(self, tmp_path: Path) -> None:
        """translate_srt uses correct DeepL params: EN, ZH, nonewlines."""
        input_srt = tmp_path / "input.srt"
        input_srt.write_text(SAMPLE_SRT)
        output_srt = tmp_path / "output" / "translated.srt"

        mock_result = MagicMock(text="翻译", billed_characters=2)

        with (
            patch("deepl.Translator") as mock_translator_cls,
            patch("opencc.OpenCC") as mock_opencc_cls,
        ):
            mock_translator = MagicMock()
            mock_translator_cls.return_value = mock_translator
            mock_translator.translate_text.return_value = [mock_result] * 3

            mock_converter = MagicMock()
            mock_opencc_cls.return_value = mock_converter
            mock_converter.convert.side_effect = lambda x: x

            from crosspost.translator import translate_srt

            translate_srt(str(input_srt), str(output_srt), "fake-key")

        call_kwargs = mock_translator.translate_text.call_args[1]
        assert call_kwargs["source_lang"] == "EN"
        assert call_kwargs["target_lang"] == "ZH"
        assert call_kwargs["split_sentences"] == "nonewlines"

    def test_output_subtitle_count_matches_input(self, tmp_path: Path) -> None:
        """Output SRT has same number of subtitle entries as input."""
        import srt

        input_srt = tmp_path / "input.srt"
        input_srt.write_text(SAMPLE_SRT)
        output_srt = tmp_path / "output" / "translated.srt"

        mock_result = MagicMock(text="翻译文本", billed_characters=4)

        with (
            patch("deepl.Translator") as mock_translator_cls,
            patch("opencc.OpenCC") as mock_opencc_cls,
        ):
            mock_translator = MagicMock()
            mock_translator_cls.return_value = mock_translator
            mock_translator.translate_text.return_value = [mock_result] * 3

            mock_converter = MagicMock()
            mock_opencc_cls.return_value = mock_converter
            mock_converter.convert.side_effect = lambda x: x

            from crosspost.translator import translate_srt

            translate_srt(str(input_srt), str(output_srt), "fake-key")

        output_text = output_srt.read_text()
        output_subs = list(srt.parse(output_text))
        input_subs = list(srt.parse(SAMPLE_SRT))
        assert len(output_subs) == len(input_subs)

    def test_opencc_t2s_conversion_applied(self, tmp_path: Path) -> None:
        """translate_srt applies OpenCC t2s conversion on DeepL output."""
        input_srt = tmp_path / "input.srt"
        input_srt.write_text(SAMPLE_SRT)
        output_srt = tmp_path / "output" / "translated.srt"

        mock_result = MagicMock(text="傳統字", billed_characters=3)

        with (
            patch("deepl.Translator") as mock_translator_cls,
            patch("opencc.OpenCC") as mock_opencc_cls,
        ):
            mock_translator = MagicMock()
            mock_translator_cls.return_value = mock_translator
            mock_translator.translate_text.return_value = [mock_result] * 3

            mock_converter = MagicMock()
            mock_opencc_cls.return_value = mock_converter
            mock_converter.convert.return_value = "简体字"

            from crosspost.translator import translate_srt

            translate_srt(str(input_srt), str(output_srt), "fake-key")

        # OpenCC should be initialized with 't2s'
        mock_opencc_cls.assert_called_once_with("t2s")
        # convert called for each subtitle
        assert mock_converter.convert.call_count == 3

    def test_creates_output_directory(self, tmp_path: Path) -> None:
        """translate_srt creates output directory if it doesn't exist."""
        input_srt = tmp_path / "input.srt"
        input_srt.write_text(SAMPLE_SRT)
        output_srt = tmp_path / "nested" / "deep" / "translated.srt"

        mock_result = MagicMock(text="翻译", billed_characters=2)

        with (
            patch("deepl.Translator") as mock_translator_cls,
            patch("opencc.OpenCC") as mock_opencc_cls,
        ):
            mock_translator = MagicMock()
            mock_translator_cls.return_value = mock_translator
            mock_translator.translate_text.return_value = [mock_result] * 3

            mock_converter = MagicMock()
            mock_opencc_cls.return_value = mock_converter
            mock_converter.convert.side_effect = lambda x: x

            from crosspost.translator import translate_srt

            translate_srt(str(input_srt), str(output_srt), "fake-key")

        assert output_srt.parent.exists()
        assert output_srt.exists()

    def test_returns_output_path(self, tmp_path: Path) -> None:
        """translate_srt returns the output SRT path on success."""
        input_srt = tmp_path / "input.srt"
        input_srt.write_text(SAMPLE_SRT)
        output_srt = tmp_path / "output" / "translated.srt"

        mock_result = MagicMock(text="翻译", billed_characters=2)

        with (
            patch("deepl.Translator") as mock_translator_cls,
            patch("opencc.OpenCC") as mock_opencc_cls,
        ):
            mock_translator = MagicMock()
            mock_translator_cls.return_value = mock_translator
            mock_translator.translate_text.return_value = [mock_result] * 3

            mock_converter = MagicMock()
            mock_opencc_cls.return_value = mock_converter
            mock_converter.convert.side_effect = lambda x: x

            from crosspost.translator import translate_srt

            result = translate_srt(str(input_srt), str(output_srt), "fake-key")

        assert result == str(output_srt)


# --- Metadata Translation Tests ---


def _mock_anthropic_response(text: str) -> MagicMock:
    """Create a mock Anthropic API response."""
    mock_content = MagicMock()
    mock_content.text = text
    mock_response = MagicMock()
    mock_response.content = [mock_content]
    return mock_response


class TestTranslateMetadata:
    """Tests for translate_metadata function."""

    def test_toutiao_uses_correct_system_prompt(self) -> None:
        """translate_metadata calls Claude Haiku 4.5 with toutiao system prompt."""
        with patch("anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = _mock_anthropic_response("中文标题")

            from crosspost.translator import translate_metadata

            translate_metadata(
                title="Test Video Title",
                description="A description of the video",
                platform="toutiao",
                api_key="fake-key",
            )

        # Verify model used
        calls = mock_client.messages.create.call_args_list
        for call in calls:
            assert call[1]["model"] == "claude-haiku-4-5"

        # Verify toutiao system prompt contains news/information tone guidance
        title_call = calls[0]
        system_prompt = title_call[1]["system"]
        assert "头条" in system_prompt or "toutiao" in system_prompt.lower() or "新闻" in system_prompt or "资讯" in system_prompt

    def test_baijiahao_uses_correct_system_prompt(self) -> None:
        """translate_metadata calls Claude Haiku 4.5 with baijiahao system prompt."""
        with patch("anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = _mock_anthropic_response("中文标题")

            from crosspost.translator import translate_metadata

            translate_metadata(
                title="Test Video Title",
                description="A description",
                platform="baijiahao",
                api_key="fake-key",
            )

        calls = mock_client.messages.create.call_args_list
        title_call = calls[0]
        system_prompt = title_call[1]["system"]
        assert "百家号" in system_prompt or "baijiahao" in system_prompt.lower() or "SEO" in system_prompt

    def test_returns_dict_with_title_and_description(self) -> None:
        """translate_metadata returns dict with 'title' and 'description' keys."""
        with patch("anthropic.Anthropic") as mock_anthropic_cls:
            mock_client = MagicMock()
            mock_anthropic_cls.return_value = mock_client
            mock_client.messages.create.return_value = _mock_anthropic_response("翻译结果")

            from crosspost.translator import translate_metadata

            result = translate_metadata(
                title="Test Title",
                description="Test description",
                platform="toutiao",
                api_key="fake-key",
            )

        assert isinstance(result, dict)
        assert "title" in result
        assert "description" in result

    def test_raises_keyerror_for_unknown_platform(self) -> None:
        """translate_metadata raises KeyError for unknown platform."""
        from crosspost.translator import translate_metadata

        with pytest.raises(KeyError):
            translate_metadata(
                title="Test",
                description="Test",
                platform="xiaohongshu",
                api_key="fake-key",
            )

    def test_platform_prompts_tone_guidance(self) -> None:
        """System prompts contain correct tone guidance per platform."""
        from crosspost.translator import PLATFORM_PROMPTS

        # Toutiao: news/information tone
        toutiao_prompt = PLATFORM_PROMPTS["toutiao"]
        assert any(
            keyword in toutiao_prompt
            for keyword in ["新闻", "资讯", "news", "information", "头条"]
        )

        # Baijiahao: formal/SEO tone
        baijiahao_prompt = PLATFORM_PROMPTS["baijiahao"]
        assert any(
            keyword in baijiahao_prompt
            for keyword in ["SEO", "百家号", "formal", "正式", "搜索"]
        )
