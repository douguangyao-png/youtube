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
