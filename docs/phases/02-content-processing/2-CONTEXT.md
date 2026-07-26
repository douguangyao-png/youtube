# Phase 2: Content Processing - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Downloaded videos are transcoded, transcribed, subtitled, and translated into Chinese assets ready for publishing. Delivers: FFmpeg transcoding, faster-whisper ASR, subtitle translation (DeepL), subtitle burn-in, LLM title/description translation per platform.

Requirements: PROC-01, PROC-02, PROC-03, PROC-04, PROC-05

</domain>

<decisions>
## Implementation Decisions

### Subtitle burn-in style
- White text on semi-transparent black bar (60% opacity)
- Font: Noto Sans CJK SC **Bold**
- Bilingual: Chinese on top, English smaller below
- Horizontal video: 24px Chinese / 18px English, positioned 8% from bottom
- Vertical video (Shorts): 20px Chinese / 15px English, positioned **20% from bottom** (avoid platform UI overlay)
- Long sentences auto-wrap, maximum 2 lines per subtitle
- Subtitles burned into all output videos — no soft subtitle option

### Platform title/description translation
- LLM (not DeepL) generates titles and descriptions per platform
- Titles are **re-created** per platform style, not direct translations
- Descriptions are **condensed/rewritten** by LLM, not direct translations
- Three distinct platform prompts:
  - Toutiao (头条): news/information tone, ~30 chars
  - Xiaohongshu (小红书): casual/sharing tone, emoji-heavy, ~20 chars, auto-generate #topic tags — DEFERRED (XHS not publishing in v1)
  - Baijiahao (百家号): formal/SEO tone, ~30 chars
- Original video tags/hashtags are NOT translated or carried over

### Output format
- Single universal output per video (not per-platform)
- 1080p H.264 MP4
- Bitrate dynamically matched to source video quality
- No aspect ratio conversion (no cropping to 3:4)
- All outputs include burned-in bilingual subtitles

### Processing pipeline order
- State flow: DOWNLOADED → (transcode + ASR in parallel) → translate → burn subtitles → PROCESSED → translate metadata → TRANSLATED
- Intermediate artifacts (SRT files, transcoded video) preserved on disk

### Failure handling
- All processing steps retry **2 times** before marking FAILED
- Pure music / no-dialogue videos: NOT a failure — skip subtitles, proceed to next step
- Partial success is preserved — resume from failure point, don't re-run completed steps
- DeepL free tier (500K chars/month) sufficient for personal use; monitor usage

### Claude's Discretion
- FFmpeg filter chain construction details
- faster-whisper model size selection (large-v3 vs medium)
- DeepL API integration details and chunking strategy
- LLM prompt engineering for platform-specific titles
- Exact retry/backoff timing (tenacity config)
- Intermediate file naming and directory structure

</decisions>

<specifics>
## Specific Ideas

- Subtitle style inspired by standard Chinese video platform conventions (white bold + dark bar)
- Vertical video subtitle position raised to avoid Douyin/XHS like/comment button overlay area
- Platform titles should feel native — a Chinese viewer should not realize it's translated content
- Pure music videos are common in short-form content; silently passing them through is important

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Content` model (models.py): already has `video_path`, `thumbnail_path`, `metadata_path` fields — needs new fields for processed artifacts (srt_path, translated_srt_path, processed_video_path)
- `ContentStatus` enum: already has PROCESSED and TRANSLATED states ready to use
- `AppSettings` / `DownloadConfig`: extend with processing config (ASR model, font path, etc.)
- `database.py`: `get_session` context manager for all DB operations
- Error pattern from downloader.py: status → FAILED with error_message — reuse for processing failures

### Established Patterns
- Synchronous pipeline (no async)
- tenacity retry decorator with logging
- yt-dlp metadata extraction pattern (extract_info with download=False) — similar pattern for FFmpeg probe
- State transitions with timestamp updates

### Integration Points
- Input: reads DOWNLOADED videos from Content table (video_path, metadata_path)
- Output: writes PROCESSED/TRANSLATED status + artifact paths for Phase 3 publishers
- Scheduler (scheduler.py): needs new job or pipeline extension to trigger processing after download

</code_context>

<deferred>
## Deferred Ideas

- Xiaohongshu (小红书) publishing removed from v1 scope — no 3:4 aspect ratio conversion needed
- Per-platform video re-encoding for anti-detection (different perceptual hash) — Phase 3 if needed
- AI smart editing of long videos — v2 (PROC-08)
- Web UI for monitoring processing status — v2

</deferred>

---

*Phase: 02-content-processing*
*Context gathered: 2026-03-14*
