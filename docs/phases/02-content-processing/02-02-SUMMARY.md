---
phase: 02-content-processing
plan: "02"
subsystem: processing
tags: [ffmpeg, ffprobe, faster-whisper, pysubs2, subprocess, transcoding, asr]

requires:
  - phase: 02-content-processing
    provides: ProcessingConfig with ASR settings, Content model with processing fields, Phase 2 dependencies
provides:
  - probe_video function for FFmpeg stream info extraction
  - transcode_to_h264 function with dynamic CRF and no-upscale scaling
  - transcribe_to_srt function with faster-whisper ASR and music-video graceful handling
affects: [02-03, 02-04, 02-05]

tech-stack:
  added: []
  patterns: [subprocess-ffmpeg, whisper-to-pysubs2-srt, dynamic-crf]

key-files:
  created:
    - src/crosspost/transcoder.py
    - src/crosspost/transcriber.py
    - tests/test_transcoder.py
    - tests/test_transcriber.py
  modified: []

key-decisions:
  - "Dynamic CRF: 20 for >4000kbps sources, 23 for lower bitrate (quality-preserving without bloat)"
  - "Scale filter scale=-2:'min(1080,ih)' prevents upscaling below-1080p sources"
  - "WhisperModel loaded once per call with cpu/int8 — retry at orchestrator level avoids redundant model loading"
  - "Empty segment list returns empty string (music video) — not a failure, per user decision"

patterns-established:
  - "FFmpeg subprocess pattern: subprocess.run with capture_output=True, check=True, timeout=600"
  - "Music-video handling: empty segments -> empty string return, caller decides next step"
  - "No retry decorators on CPU-heavy functions — retry at orchestrator level"

requirements-completed: [PROC-05, PROC-01]

duration: 3min
completed: 2026-03-15
---

# Phase 02 Plan 02: Transcoder and Transcriber Summary

**FFmpeg probe/transcode with dynamic CRF and no-upscale scaling, faster-whisper ASR to SRT with VAD filtering and music-video graceful handling**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-15T12:41:29Z
- **Completed:** 2026-03-15T12:44:15Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- probe_video extracts width/height/bitrate/codec from ffprobe JSON output
- transcode_to_h264 produces H.264 MP4 with dynamic CRF (20/23), no-upscale scale filter, movflags +faststart
- transcribe_to_srt converts faster-whisper segments to SRT via pysubs2, returns empty string for music videos
- 15 new tests (10 transcoder + 5 transcriber) all passing, no regressions in existing suite

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for transcoder** - `ae0ab3f` (test)
2. **Task 1 GREEN: Implement transcoder** - `6921e2a` (feat)
3. **Task 2 RED: Failing tests for transcriber** - `e9748be` (test)
4. **Task 2 GREEN: Implement transcriber** - `67c4ce3` (feat)

## Files Created/Modified
- `src/crosspost/transcoder.py` - FFmpeg probe and transcode functions via subprocess
- `src/crosspost/transcriber.py` - faster-whisper ASR to SRT via pysubs2
- `tests/test_transcoder.py` - 10 tests: probe stream info, probe failure, CRF selection, scale filter, movflags, timeout, overwrite
- `tests/test_transcriber.py` - 5 tests: model params, transcribe params, segment conversion, empty segments, directory creation

## Decisions Made
- Dynamic CRF (20 for high bitrate, 23 for low) balances quality preservation with file size
- scale=-2:'min(1080,ih)' prevents upscaling — divisible-by-2 width guaranteed by -2
- WhisperModel uses cpu/int8 for server deployment without GPU
- No retry decorators on transcoder/transcriber — retry at orchestrator level to avoid re-loading WhisperModel

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required. FFmpeg and faster-whisper models are runtime dependencies.

## Next Phase Readiness
- transcoder.py ready for processor orchestration (02-05)
- transcriber.py ready for subtitle translation pipeline (02-03)
- Both modules follow established subprocess/logging patterns

---
*Phase: 02-content-processing*
*Completed: 2026-03-15*
