---
phase: 01-pipeline-foundation
plan: "02"
subsystem: acquisition
tags: [feedparser, yt-dlp, rss, youtube, tenacity, sqlmodel, state-machine]

# Dependency graph
requires:
  - phase: 01-pipeline-foundation/01-01
    provides: AppSettings, ChannelConfig, DownloadConfig, Content, ContentStatus, get_engine, get_session, init_db
provides:
  - YouTube RSS feed polling with 3-level video_id fallback extraction
  - Batch deduplication for new video discovery via Content.video_id
  - yt-dlp metadata extraction with cookiesfrombrowser as tuple
  - Duration filtering gate (unknown durations pass through)
  - Video download with thumbnail and info JSON artifacts
  - DISCOVERED -> DOWNLOADING -> DOWNLOADED/FAILED state transitions
affects: [01-03, 02-pipeline-enhancement, scheduler, cli-runner]

# Tech tracking
tech-stack:
  added: [feedparser>=6.0.0, yt-dlp>=2024.1.0, tenacity>=8.0.0, loguru>=0.7.0]
  patterns: [tdd-red-green, state-machine-transitions, batch-dedup-query, tuple-cookie-format]

key-files:
  created:
    - src/crosspost/feeds.py
    - src/crosspost/downloader.py
    - tests/test_feeds.py
    - tests/test_downloader.py
  modified: []

key-decisions:
  - "cookiesfrombrowser must be tuple (browser, None, None, None) not string -- yt-dlp internal requirement"
  - "Unknown/zero duration passes through filter -- don't block videos with unavailable duration data"
  - "Batch dedup query for all video_ids in one SELECT WHERE IN -- avoid N+1 queries per RSS entry"
  - "Metadata failure transitions to FAILED (not skip) -- operator needs visibility into broken videos"
  - "poll_channel returns empty list on error (never raises) -- resilient pipeline design"

patterns-established:
  - "State machine: Always transition to intermediate state (DOWNLOADING) before operation to track in-flight work"
  - "Duration gate: Always resolve per-channel override via settings.get_max_duration before global fallback"
  - "yt-dlp cookie format: (browser, None, None, None) tuple for all yt-dlp calls"

requirements-completed: [ACQ-01, ACQ-02, ACQ-04]

# Metrics
duration: 5min
completed: 2026-03-14
---

# Phase 1 Plan 02: RSS Feed Poller and yt-dlp Downloader Summary

**YouTube RSS feed polling with feedparser and yt-dlp video download pipeline: deduplication, duration filtering, and DISCOVERED->DOWNLOADED state transitions**

## Performance

- **Duration:** 5 min
- **Started:** 2026-03-14T15:26:32Z
- **Completed:** 2026-03-14T15:31:00Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- `poll_channel` parses YouTube Atom feeds with feedparser, extracting video_id via 3-level fallback (yt_videoid -> yt:video: id format -> ?v= link param) and returns structured dicts
- `discover_new_videos` batch-checks all video_ids against DB in one query, inserts only new Content rows with DISCOVERED status
- `get_video_metadata` extracts video info without downloading; cookiesfrombrowser passed as tuple `(browser, None, None, None)` per yt-dlp API requirement
- `should_download` duration gate passes unknown/zero durations (don't block), rejects > max_duration
- `process_discovered_videos` orchestrates full DISCOVERED->DOWNLOADING->DOWNLOADED/FAILED state machine with per-channel duration overrides
- 33 tests green across both modules (TDD red-green workflow)

## Task Commits

Each task was committed atomically:

1. **Task 1: YouTube RSS feed poller (RED)** - `d1e776b` (test)
2. **Task 1: YouTube RSS feed poller (GREEN)** - `dadd5bc` (feat)
3. **Task 2: yt-dlp downloader (RED)** - `9f9a427` (test)
4. **Task 2: yt-dlp downloader (GREEN)** - `bf927a5` (feat)

_TDD tasks have separate test and implementation commits (red -> green)_

## Files Created/Modified

- `src/crosspost/feeds.py` - YouTube RSS polling (`poll_channel`, `discover_new_videos`) with tenacity retry
- `src/crosspost/downloader.py` - yt-dlp wrapper (`get_video_metadata`, `should_download`, `download_video`, `process_discovered_videos`)
- `tests/test_feeds.py` - 13 tests covering poll_channel, video_id extraction fallbacks, discover dedup
- `tests/test_downloader.py` - 20 tests covering metadata, duration filtering, download, state transitions

## Decisions Made

- **cookiesfrombrowser as tuple:** yt-dlp requires `(browser, profile, keyring, container)` tuple format internally. Passing a string causes runtime errors. Hardcoded to `(cookies_browser, None, None, None)` pattern.
- **Unknown duration passes:** `should_download` returns True for duration=0 or None. Blocking unknowns would cause false negatives on videos where yt-dlp can't determine duration pre-download.
- **Batch dedup query:** `discover_new_videos` collects all video_ids from feed then does one `SELECT WHERE IN` instead of per-video queries, preventing N+1 database load on large feeds.
- **Metadata failure -> FAILED:** If `get_video_metadata` returns None, video is marked FAILED rather than silently skipped. This gives operators visibility into problematic videos.
- **poll_channel never raises:** Wrapped in try/except to return `[]` on error -- upstream callers don't need error handling, pipeline continues on partial failures.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None. All tests passed on first run after implementing each module.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- RSS feed polling and video download pipeline complete
- Ready for Plan 03 (scheduler/orchestrator or CLI runner) to wire `discover_new_videos` and `process_discovered_videos` into automated polling loop
- cookiesfrombrowser requires Firefox with active YouTube session on the host machine for real downloads

---
*Phase: 01-pipeline-foundation*
*Completed: 2026-03-14*
