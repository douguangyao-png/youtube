"""Tests for the subtitler module — bilingual ASS generation and FFmpeg burn-in."""

import pysubs2
import pytest

from crosspost.subtitler import build_bilingual_ass


@pytest.fixture()
def en_srt(tmp_path):
    """Create a minimal English SRT file."""
    srt = tmp_path / "en.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\nHello world\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\nGoodbye world\n"
    )
    return str(srt)


@pytest.fixture()
def zh_srt(tmp_path):
    """Create a minimal Chinese SRT file."""
    srt = tmp_path / "zh.srt"
    srt.write_text(
        "1\n00:00:01,000 --> 00:00:03,000\n你好世界\n\n"
        "2\n00:00:04,000 --> 00:00:06,000\n再见世界\n"
    )
    return str(srt)


class TestBuildBilingualAss:
    """Tests for build_bilingual_ass function."""

    def test_creates_ass_file(self, tmp_path, en_srt, zh_srt):
        """build_bilingual_ass creates an ASS file at the output path."""
        out = str(tmp_path / "out.ass")
        result = build_bilingual_ass(en_srt, zh_srt, out, video_height=1080, is_vertical=False)
        assert result == out
        assert (tmp_path / "out.ass").exists()

    def test_has_chinese_and_english_styles(self, tmp_path, en_srt, zh_srt):
        """ASS file has named styles 'Chinese' and 'English'."""
        out = str(tmp_path / "out.ass")
        build_bilingual_ass(en_srt, zh_srt, out, video_height=1080, is_vertical=False)
        subs = pysubs2.load(out)
        assert "Chinese" in subs.styles
        assert "English" in subs.styles

    def test_chinese_style_properties(self, tmp_path, en_srt, zh_srt):
        """Chinese style uses Noto Sans CJK SC, bold, borderstyle=3."""
        out = str(tmp_path / "out.ass")
        build_bilingual_ass(en_srt, zh_srt, out, video_height=1080, is_vertical=False)
        subs = pysubs2.load(out)
        style = subs.styles["Chinese"]
        assert style.fontname == "Noto Sans CJK SC"
        assert style.bold is True
        assert style.borderstyle == 3

    def test_english_style_properties(self, tmp_path, en_srt, zh_srt):
        """English style uses Noto Sans CJK SC, not bold, borderstyle=3."""
        out = str(tmp_path / "out.ass")
        build_bilingual_ass(en_srt, zh_srt, out, video_height=1080, is_vertical=False)
        subs = pysubs2.load(out)
        style = subs.styles["English"]
        assert style.fontname == "Noto Sans CJK SC"
        assert style.bold is False
        assert style.borderstyle == 3

    def test_backcolor_alpha_102(self, tmp_path, en_srt, zh_srt):
        """Both styles use backcolor with alpha=102 (60% opacity, pysubs2 inverted)."""
        out = str(tmp_path / "out.ass")
        build_bilingual_ass(en_srt, zh_srt, out, video_height=1080, is_vertical=False)
        subs = pysubs2.load(out)
        for name in ("Chinese", "English"):
            style = subs.styles[name]
            assert style.backcolor.a == 102, f"{name} backcolor alpha should be 102"

    def test_horizontal_fontsize(self, tmp_path, en_srt, zh_srt):
        """Horizontal video uses 24px Chinese / 18px English."""
        out = str(tmp_path / "out.ass")
        build_bilingual_ass(en_srt, zh_srt, out, video_height=1080, is_vertical=False)
        subs = pysubs2.load(out)
        assert subs.styles["Chinese"].fontsize == 24
        assert subs.styles["English"].fontsize == 18

    def test_vertical_fontsize(self, tmp_path, en_srt, zh_srt):
        """Vertical video uses 20px Chinese / 15px English."""
        out = str(tmp_path / "out.ass")
        build_bilingual_ass(en_srt, zh_srt, out, video_height=1920, is_vertical=True)
        subs = pysubs2.load(out)
        assert subs.styles["Chinese"].fontsize == 20
        assert subs.styles["English"].fontsize == 15

    def test_horizontal_marginv(self, tmp_path, en_srt, zh_srt):
        """Horizontal marginv based on 8% of video_height."""
        out = str(tmp_path / "out.ass")
        build_bilingual_ass(en_srt, zh_srt, out, video_height=1080, is_vertical=False)
        subs = pysubs2.load(out)
        base_marginv = int(1080 * 0.08)  # 86
        en_fontsize = 18
        assert subs.styles["English"].marginv == base_marginv
        assert subs.styles["Chinese"].marginv == base_marginv + en_fontsize + 6

    def test_vertical_marginv(self, tmp_path, en_srt, zh_srt):
        """Vertical marginv based on 20% of video_height."""
        out = str(tmp_path / "out.ass")
        build_bilingual_ass(en_srt, zh_srt, out, video_height=1920, is_vertical=True)
        subs = pysubs2.load(out)
        base_marginv = int(1920 * 0.20)  # 384
        en_fontsize = 15
        assert subs.styles["English"].marginv == base_marginv
        assert subs.styles["Chinese"].marginv == base_marginv + en_fontsize + 6

    def test_event_pairs(self, tmp_path, en_srt, zh_srt):
        """Each SRT segment pair creates two SSAEvent entries (Chinese + English)."""
        out = str(tmp_path / "out.ass")
        build_bilingual_ass(en_srt, zh_srt, out, video_height=1080, is_vertical=False)
        subs = pysubs2.load(out)
        # 2 SRT segments -> 4 events (2 Chinese + 2 English)
        assert len(subs.events) == 4
        chinese_events = [e for e in subs.events if e.style == "Chinese"]
        english_events = [e for e in subs.events if e.style == "English"]
        assert len(chinese_events) == 2
        assert len(english_events) == 2

    def test_wrap_style_zero(self, tmp_path, en_srt, zh_srt):
        """ASS file has wrap_style=0 for smart wrapping."""
        out = str(tmp_path / "out.ass")
        build_bilingual_ass(en_srt, zh_srt, out, video_height=1080, is_vertical=False)
        subs = pysubs2.load(out)
        assert subs.info.get("WrapStyle") == "0"

    def test_empty_srts_returns_empty_string(self, tmp_path):
        """Returns empty string when both SRT paths are empty (music video)."""
        result = build_bilingual_ass("", "", str(tmp_path / "out.ass"), 1080, False)
        assert result == ""
