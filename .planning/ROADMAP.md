# Roadmap: CrossPost

## Overview

CrossPost is built as a staged pipeline: foundation first (state machine, config, scheduling), then content acquisition from YouTube, then video processing and translation, and finally publishing to all target Chinese platforms with automation safeguards. Each phase delivers a coherent, independently verifiable capability. The pipeline becomes end-to-end functional at Phase 3 with the first successful publish.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Pipeline Foundation** - State machine, config, scheduling, and YouTube acquisition
- [ ] **Phase 2: Content Processing** - Transcoding, ASR, subtitle burn-in, and translation
- [ ] **Phase 3: Publishing & Automation** - All platform publishers, anti-detection, and automation hardening

## Phase Details

### Phase 1: Pipeline Foundation
**Goal**: The system can discover, download, and track YouTube videos unattended
**Depends on**: Nothing (first phase)
**Requirements**: ACQ-01, ACQ-02, ACQ-03, ACQ-04, AUTO-01, AUTO-02, AUTO-03
**Success Criteria** (what must be TRUE):
  1. Operator edits a YAML config file with a channel list and credentials; the system reads it on startup without code changes
  2. The system polls configured YouTube channels on a schedule and downloads new videos (with metadata and thumbnails) without manual invocation
  3. A video already downloaded is not downloaded again across restarts (deduplication is persistent)
  4. After a crash or restart, the system resumes from the last known job state rather than restarting from scratch
  5. A SQLite database contains a content row per discovered video with a clear status (DISCOVERED, DOWNLOADED, FAILED, etc.)
**Plans:** 3/3 plans executed

Plans:
- [x] 01-01-PLAN.md -- Project scaffolding, config system, and SQLModel state machine
- [x] 01-02-PLAN.md -- YouTube RSS feed poller and yt-dlp downloader with duration filtering
- [x] 01-03-PLAN.md -- APScheduler wiring, crash recovery, and application entry point

### Phase 2: Content Processing
**Goal**: Downloaded videos are transcoded, transcribed, subtitled, and translated into Chinese assets ready for publishing
**Depends on**: Phase 1
**Requirements**: PROC-01, PROC-02, PROC-03, PROC-04, PROC-05
**Success Criteria** (what must be TRUE):
  1. A downloaded video is transcoded to H.264 MP4 at platform-appropriate resolution and bitrate without manual intervention
  2. English speech in the video is transcribed to an SRT file with accurate timestamps
  3. The SRT file is translated to Chinese (sentence-level, timing preserved) and burned into the video with a legible CJK font
  4. The video title and description are translated into natural Chinese text appropriate to the target platform's style
  5. All processed artifacts (video file, SRT, translated metadata) are written to the job state before the job advances — a crash during processing does not re-trigger expensive ASR or translation calls
**Plans:** 5 plans

Plans:
- [ ] 02-01-PLAN.md -- Config extension and Phase 2 dependency install
- [ ] 02-02-PLAN.md -- Transcoder (ffprobe + H.264 transcode) and transcriber (faster-whisper ASR to SRT)
- [ ] 02-03-PLAN.md -- Translator (DeepL subtitle translation + Claude metadata translation)
- [ ] 02-04-PLAN.md -- Subtitler (bilingual ASS generation + FFmpeg burn-in)
- [ ] 02-05-PLAN.md -- Processor orchestrator wiring and scheduler integration

### Phase 3: Publishing & Automation
**Goal**: Processed and translated videos are automatically published to all target platforms with anti-detection safeguards and rate controls
**Depends on**: Phase 2
**Requirements**: PUB-01, PUB-02, PUB-03, AUTO-04
**Success Criteria** (what must be TRUE):
  1. A processed video is published to Toutiao (via API) and Baidu Baijiahao (via API) without manual action
  2. A processed video is published to Xiaohongshu via browser automation without triggering account flags
  3. Each platform enforces a configurable minimum publish interval — no two posts to the same platform are sent closer together than the configured gap
  4. A failed publish is retried with exponential backoff; after exceeding the retry limit the job is marked FAILED and does not block other jobs
  5. The end-to-end pipeline runs unattended: a new YouTube video on a monitored channel is discovered, processed, translated, and published to all platforms without operator interaction
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Pipeline Foundation | 3/3 | Complete | 2026-03-14 |
| 2. Content Processing | 0/5 | Not started | - |
| 3. Publishing & Automation | 0/TBD | Not started | - |
