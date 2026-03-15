---
phase: 02-content-processing
verified: 2026-03-15T12:00:00Z
status: passed
score: 5/5 success criteria verified
must_haves:
  truths:
    - "A downloaded video is transcoded to H.264 MP4 at platform-appropriate resolution and bitrate without manual intervention"
    - "English speech in the video is transcribed to an SRT file with accurate timestamps"
    - "The SRT file is translated to Chinese (sentence-level, timing preserved) and burned into the video with a legible CJK font"
    - "The video title and description are translated into natural Chinese text appropriate to the target platform's style"
    - "All processed artifacts (video file, SRT, translated metadata) are written to the job state before the job advances — a crash during processing does not re-trigger expensive ASR or translation calls"
  artifacts:
    - path: "src/crosspost/config.py"
      status: verified
    - path: "src/crosspost/models.py"
      status: verified
    - path: "src/crosspost/transcoder.py"
      status: verified
    - path: "src/crosspost/transcriber.py"
      status: verified
    - path: "src/crosspost/translator.py"
      status: verified
    - path: "src/crosspost/subtitler.py"
      status: verified
    - path: "src/crosspost/processor.py"
      status: verified
    - path: "src/crosspost/scheduler.py"
      status: verified
requirements:
  - id: PROC-01
    status: satisfied
  - id: PROC-02
    status: satisfied
  - id: PROC-03
    status: satisfied
  - id: PROC-04
    status: satisfied
  - id: PROC-05
    status: satisfied
---

# Phase 2: Content Processing Verification Report

**Phase Goal:** Downloaded videos are transcoded, transcribed, subtitled, and translated into Chinese assets ready for publishing
**Verified:** 2026-03-15T12:00:00Z
**Status:** passed
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A downloaded video is transcoded to H.264 MP4 at platform-appropriate resolution and bitrate without manual intervention | VERIFIED | `transcoder.py` implements `probe_video` (ffprobe) and `transcode_to_h264` with dynamic CRF (20 for >4000kbps, 23 otherwise), scale filter `-2:'min(1080,ih)'` prevents upscaling, `-movflags +faststart`, 600s timeout. `processor.py` calls these in Phase A via ThreadPoolExecutor. 147-line test file passes. |
| 2 | English speech in the video is transcribed to an SRT file with accurate timestamps | VERIFIED | `transcriber.py` implements `transcribe_to_srt` using `WhisperModel(model_size, device="cpu", compute_type="int8")` with `vad_filter=True, vad_parameters={"threshold": 0.5}`, beam_size=5. Converts segments to pysubs2 whisper format and saves as SRT. Returns empty string for music videos. 123-line test file passes. |
| 3 | The SRT file is translated to Chinese (sentence-level, timing preserved) and burned into the video with a legible CJK font | VERIFIED | `translator.py` batch-translates via DeepL with `split_sentences="nonewlines"`, applies OpenCC `t2s` conversion, preserves subtitle count. `subtitler.py` builds bilingual ASS with Chinese (Noto Sans CJK SC Bold, 24/20px) above English (18/15px), `borderstyle=3`, `backcolor=Color(0,0,0,102)` for 60% opacity, orientation-aware margins (8%/20%). `burn_subtitles` uses FFmpeg `subtitles=` filter with `fontsdir=`. 322-line translator test + 181-line subtitler test pass. |
| 4 | The video title and description are translated into natural Chinese text appropriate to the target platform's style | VERIFIED | `translator.py` implements `translate_metadata` calling `claude-haiku-4-5` with platform-specific `PLATFORM_PROMPTS`: toutiao (news/information tone) and baijiahao (formal/SEO tone). Returns `{"title": ..., "description": ...}` dict. Raises KeyError for unknown platforms. Description uses separate condensation prompt. Tests verify correct model and prompts per platform. |
| 5 | All processed artifacts (video file, SRT, translated metadata) are written to the job state before the job advances -- a crash during processing does not re-trigger expensive ASR or translation calls | VERIFIED | `processor.py` implements write-before-advance pattern: each phase writes artifact paths to Content row via `session.commit()` BEFORE advancing status. Idempotency checks (`content.processed_video_path is None`, `content.srt_path is None`, etc.) skip completed steps on restart. Each step wrapped in tenacity `@retry(stop=stop_after_attempt(max_retries))`. On final failure, marks FAILED with error_message. 516-line test file covers idempotency, crash recovery, music video path, and failure handling. |

**Score:** 5/5 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/crosspost/config.py` | ProcessingConfig nested in AppSettings | VERIFIED | ProcessingConfig with asr_model, output_dir, font_path, deepl_auth_key, anthropic_api_key, max_retries. Wired into AppSettings as `processing` field. |
| `src/crosspost/models.py` | Content model with processing artifact fields | VERIFIED | 7 new fields: srt_path, translated_srt_path, ass_path, processed_video_path, processed_at, translated_at, platform_metadata. All Optional with None defaults. |
| `pyproject.toml` | Phase 2 dependencies | VERIFIED | All 6 packages present: faster-whisper>=1.2.1, pysubs2>=1.8.0, deepl>=1.28.0, anthropic>=0.84.0, opencc-python-reimplemented>=0.1.7, srt>=3.5.3. |
| `src/crosspost/transcoder.py` | FFmpeg probe and transcode functions | VERIFIED | 92 lines. Exports probe_video and transcode_to_h264. Uses subprocess.run with check=True. |
| `src/crosspost/transcriber.py` | faster-whisper ASR to SRT | VERIFIED | 64 lines. Exports transcribe_to_srt. Uses WhisperModel, pysubs2.load_from_whisper. Music video graceful handling. |
| `src/crosspost/translator.py` | DeepL subtitle + Claude metadata translation | VERIFIED | 142 lines. Exports translate_srt (DeepL batch + OpenCC t2s) and translate_metadata (Claude Haiku 4.5 with platform prompts). |
| `src/crosspost/subtitler.py` | ASS subtitle assembly and FFmpeg burn-in | VERIFIED | 152 lines. Exports build_bilingual_ass (styled ASS with orientation-aware sizing) and burn_subtitles (FFmpeg subtitles filter). |
| `src/crosspost/processor.py` | Processing pipeline orchestrator | VERIFIED | 289 lines. Exports process_downloaded_videos. Implements parallel transcode+ASR, sequential translate/burn, idempotent steps, retry, DOWNLOADED->PROCESSED->TRANSLATED transitions. |
| `src/crosspost/scheduler.py` | Extended scheduler with processing trigger | VERIFIED | Imports and calls process_videos after process_discovered_videos in poll_and_download_job. Recovery log line present. |
| `src/crosspost/assets/fonts/.gitkeep` | Font directory placeholder | VERIFIED | Exists. Docstring in subtitler.py instructs operator to place NotoSansCJKsc-Bold.otf. |
| `tests/test_transcoder.py` | Unit tests for probe and transcode | VERIFIED | 147 lines (min_lines: 40 required). |
| `tests/test_transcriber.py` | Unit tests for ASR | VERIFIED | 123 lines (min_lines: 40 required). |
| `tests/test_translator.py` | Unit tests for DeepL and Anthropic | VERIFIED | 322 lines (min_lines: 60 required). |
| `tests/test_subtitler.py` | Unit tests for ASS and burn-in | VERIFIED | 181 lines (min_lines: 50 required). |
| `tests/test_processor.py` | Unit tests for pipeline orchestration | VERIFIED | 516 lines (min_lines: 80 required). |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| config.py | config.yaml | processing section | WIRED | `processing: ProcessingConfig = Field(default_factory=ProcessingConfig)` in AppSettings |
| transcoder.py | ffmpeg/ffprobe | subprocess.run | WIRED | Both `subprocess.run` calls with ffprobe and ffmpeg commands present |
| transcriber.py | faster_whisper | WhisperModel.transcribe | WIRED | `WhisperModel(model_size, device="cpu", compute_type="int8")` and `model.transcribe(...)` |
| translator.py | deepl | translator.translate_text batch | WIRED | `translator.translate_text(texts, ..., split_sentences="nonewlines")` |
| translator.py | anthropic | client.messages.create | WIRED | `client.messages.create(model="claude-haiku-4-5", ...)` with platform prompts |
| subtitler.py | pysubs2 | SSAStyle borderstyle=3 | WIRED | `SSAStyle(..., borderstyle=3, ...)` for both Chinese and English styles |
| subtitler.py | ffmpeg | subtitles filter with fontsdir | WIRED | `f"subtitles={ass_path}:fontsdir={fonts_dir}"` in FFmpeg command |
| processor.py | transcoder.py | transcode_to_h264 in ThreadPoolExecutor | WIRED | `pool.submit(_transcode_with_retry)` calling `transcode_to_h264` |
| processor.py | transcriber.py | transcribe_to_srt in ThreadPoolExecutor | WIRED | `pool.submit(_asr_with_retry)` calling `transcribe_to_srt` |
| processor.py | translator.py | translate_srt and translate_metadata | WIRED | Both imported and called in Phases B and E |
| processor.py | subtitler.py | build_bilingual_ass and burn_subtitles | WIRED | Both imported and called in Phase C |
| processor.py | models.py | ContentStatus transitions | WIRED | `ContentStatus.PROCESSED` and `ContentStatus.TRANSLATED` set on Content rows |
| scheduler.py | processor.py | process_downloaded_videos call | WIRED | `from crosspost.processor import process_downloaded_videos as process_videos` and `processed = process_videos(engine, settings)` |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| PROC-01 | 02-02, 02-05 | faster-whisper local ASR extracts English subtitles (SRT) | SATISFIED | `transcriber.py` implements faster-whisper ASR with VAD filter, saves to SRT. Wired into processor pipeline. |
| PROC-02 | 02-03, 02-05 | English subtitles translated to Chinese (timing preserved, sentence-level) | SATISFIED | `translator.py` batch-translates via DeepL with `split_sentences="nonewlines"`, OpenCC t2s. Preserves subtitle count and timing. |
| PROC-03 | 02-04, 02-05 | Chinese subtitles burned into video (CJK font, vertical/horizontal support) | SATISFIED | `subtitler.py` builds bilingual ASS with Noto Sans CJK SC, orientation-aware sizing (24/20px ZH, 18/15px EN), burns via FFmpeg subtitles filter. |
| PROC-04 | 02-03, 02-05 | Title and description translated to natural Chinese per platform style | SATISFIED | `translator.py` translate_metadata uses Claude Haiku 4.5 with toutiao (news) and baijiahao (SEO) platform prompts. Stored as JSON in platform_metadata field. |
| PROC-05 | 02-02, 02-05 | Video transcoded per platform specs (H.264 MP4, resolution/bitrate) | SATISFIED | `transcoder.py` transcodes to H.264 with dynamic CRF, 1080p max without upscaling, faststart, AAC 128k audio. |

No orphaned requirements found -- all 5 PROC requirements are mapped to Phase 2 in REQUIREMENTS.md and all are claimed by plans.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (none) | - | - | - | No anti-patterns detected |

No TODO/FIXME/PLACEHOLDER/stub patterns found in any Phase 2 source files.

### Human Verification Required

### 1. End-to-End Processing with Real Video

**Test:** Download a short YouTube video and run the full pipeline through scheduler
**Expected:** Video is transcoded, transcribed to SRT, SRT translated to Chinese, bilingual subtitles burned into video, metadata translated for toutiao and baijiahao, Content status advances to TRANSLATED
**Why human:** Requires real FFmpeg, faster-whisper model download, DeepL API key, and Anthropic API key -- cannot verify in unit tests

### 2. Subtitle Visual Quality

**Test:** Play a processed video with burned-in bilingual subtitles
**Expected:** Chinese text appears above English, both readable on semi-transparent black bar, correct font size for horizontal vs vertical video, no text overflow
**Why human:** Visual rendering quality cannot be verified programmatically

### 3. Translation Quality

**Test:** Review translated SRT and platform metadata for a real video
**Expected:** Chinese subtitles preserve meaning and timing, toutiao title reads like news headline, baijiahao title is SEO-friendly, descriptions are condensed appropriately
**Why human:** Translation quality is subjective and requires Chinese language fluency

---

_Verified: 2026-03-15T12:00:00Z_
_Verifier: Claude (gsd-verifier)_
_Test suite: 141 tests passed (91 Phase 2 specific), 0 failures, 0 regressions_
