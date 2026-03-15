---
phase: 02-content-processing
plan: "04"
subsystem: processing
tags: [pysubs2, ass, ffmpeg, subtitles, bilingual, cjk, burn-in]

requires:
  - phase: 02-content-processing
    provides: SRT files from transcriber (02-02) and translator (02-03)
provides:
  - build_bilingual_ass function for styled ASS subtitle assembly
  - burn_subtitles function for FFmpeg subtitle burn-in with fontsdir
affects: [02-05]

tech-stack:
  added: []
  patterns: [pysubs2-ssa-bilingual-styles, ffmpeg-subtitles-filter-fontsdir]

key-files:
  created:
    - src/crosspost/subtitler.py
    - src/crosspost/assets/fonts/.gitkeep
  modified:
    - tests/test_subtitler.py

key-decisions:
  - "backcolor alpha=102 for 60% opacity (pysubs2 inverted: 0=opaque, 255=transparent)"
  - "Chinese marginv = base + en_fontsize + 6 to stack above English line"
  - "subtitles filter (not ass filter) for FFmpeg — handles both SRT and ASS"
  - "CRF 20 for burn-in re-encode (matches high-quality transcode setting)"

patterns-established:
  - "Bilingual ASS pattern: two named styles (Chinese/English) with per-orientation fontsize and marginv"
  - "FFmpeg burn-in pattern: subtitles filter with fontsdir for custom CJK font rendering on headless Linux"

requirements-completed: [PROC-03]

duration: 2min
completed: 2026-03-15
---

# Phase 02 Plan 04: Subtitler Module Summary

**Bilingual ASS subtitle assembly with pysubs2 (Chinese Bold above English on semi-transparent black bar) and FFmpeg burn-in via subtitles filter with fontsdir**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-15T12:46:44Z
- **Completed:** 2026-03-15T12:49:10Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- build_bilingual_ass creates styled ASS with Chinese/English layers, orientation-specific fontsize and margins
- burn_subtitles calls FFmpeg with subtitles filter, fontsdir, libx264 CRF 20, audio copy
- Font directory placeholder created for operator to bundle NotoSansCJKsc-Bold.otf
- 17 tests (12 ASS generation + 5 burn-in with mocked subprocess), 126 total suite passes

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing tests for ASS generator** - `6530e15` (test)
2. **Task 1 GREEN: Implement build_bilingual_ass + burn_subtitles** - `a24869c` (feat)
3. **Task 2: Add burn_subtitles tests** - `4929b9a` (test)

## Files Created/Modified
- `src/crosspost/subtitler.py` - build_bilingual_ass and burn_subtitles functions
- `src/crosspost/assets/fonts/.gitkeep` - Font directory placeholder for Noto Sans CJK SC
- `tests/test_subtitler.py` - 17 tests covering styles, margins, events, FFmpeg command

## Decisions Made
- backcolor alpha=102 for 60% opacity per pysubs2 inverted alpha convention (a=0 opaque, a=255 transparent)
- Chinese subtitle line positioned above English via marginv offset (base + en_fontsize + 6px gap)
- FFmpeg subtitles filter (not ass filter) for broader format compatibility
- CRF 20 for burn-in re-encode to match high-quality transcode setting

## Deviations from Plan

**1. [Minor] burn_subtitles implemented alongside build_bilingual_ass in Task 1 GREEN**
- Both functions were written in the same file during Task 1 implementation
- Task 2 focused on adding the burn_subtitles test coverage
- No impact on correctness — all tests pass

## Issues Encountered
None

## User Setup Required
Operator must download NotoSansCJKsc-Bold.otf from Google Fonts and place it in `src/crosspost/assets/fonts/`. Font is available under SIL OFL 1.1 license.

## Next Phase Readiness
- subtitler.py ready for processor orchestration (02-05)
- Follows established subprocess/logging patterns from transcoder.py
- Both build_bilingual_ass and burn_subtitles have clean function signatures for pipeline integration

---
*Phase: 02-content-processing*
*Completed: 2026-03-15*
