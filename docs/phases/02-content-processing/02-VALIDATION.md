---
phase: 02
slug: content-processing
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-14
---

# Phase 02 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x + pytest-mock 3.14.x |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/test_processor.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_processor.py tests/test_transcriber.py tests/test_transcoder.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | PROC-01 | unit | `uv run pytest tests/test_transcriber.py -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | PROC-01 | unit | `uv run pytest tests/test_transcriber.py::test_transcribe_music_video -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 1 | PROC-02 | unit | `uv run pytest tests/test_translator.py::test_translate_srt -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 1 | PROC-02 | unit | `uv run pytest tests/test_translator.py::test_translate_srt_batches -x` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 2 | PROC-03 | unit | `uv run pytest tests/test_subtitler.py::test_build_bilingual_ass -x` | ❌ W0 | ⬜ pending |
| 02-03-02 | 03 | 2 | PROC-03 | unit | `uv run pytest tests/test_subtitler.py::test_margin_by_orientation -x` | ❌ W0 | ⬜ pending |
| 02-04-01 | 04 | 2 | PROC-04 | unit | `uv run pytest tests/test_translator.py::test_translate_metadata_toutiao -x` | ❌ W0 | ⬜ pending |
| 02-05-01 | 05 | 1 | PROC-05 | unit | `uv run pytest tests/test_transcoder.py::test_probe_video -x` | ❌ W0 | ⬜ pending |
| 02-05-02 | 05 | 1 | PROC-05 | unit | `uv run pytest tests/test_transcoder.py::test_transcode_command -x` | ❌ W0 | ⬜ pending |
| 02-05-03 | 05 | 1 | PROC-05 | unit | `uv run pytest tests/test_processor.py::test_transcode_skips_if_done -x` | ❌ W0 | ⬜ pending |
| 02-ALL-01 | ALL | 3 | All | unit | `uv run pytest tests/test_processor.py::test_full_processing_pipeline -x` | ❌ W0 | ⬜ pending |
| 02-ALL-02 | ALL | 3 | All | unit | `uv run pytest tests/test_processor.py::test_resume_from_partial -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_processor.py` — processing orchestration and state machine transitions
- [ ] `tests/test_transcriber.py` — faster-whisper ASR, music-video pass-through
- [ ] `tests/test_transcoder.py` — ffprobe, transcode command construction
- [ ] `tests/test_translator.py` — DeepL subtitle translation, Claude metadata translation
- [ ] `tests/test_subtitler.py` — pysubs2 ASS generation, horizontal/vertical margin logic
- [ ] `src/crosspost/assets/fonts/NotoSansCJKsc-Bold.otf` — bundled CJK font for CI and production

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Subtitle visual appearance (font, position, opacity) | PROC-03 | Requires visual inspection of rendered video | Generate test video, open in player, verify bilingual subtitles readable |
| ASR transcription accuracy | PROC-01 | Requires human judgment of transcript quality | Compare whisper output to known reference transcript |
| Chinese title naturalness | PROC-04 | Requires native speaker judgment | Review 3-5 generated titles for each platform style |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
