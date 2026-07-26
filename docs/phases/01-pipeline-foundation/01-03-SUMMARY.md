---
phase: 01-pipeline-foundation
plan: "03"
subsystem: scheduler
tags: [apscheduler, sqlite, python, yt-dlp, feedparser, sqlmodel, loguru]

requires:
  - phase: 01-01
    provides: AppSettings with ScheduleConfig, get_engine, init_db, Content model, ContentStatus enum
  - phase: 01-02
    provides: discover_new_videos, process_discovered_videos, poll_channel

provides:
  - APScheduler BlockingScheduler with SQLAlchemyJobStore (separate _jobs.db)
  - recover_incomplete_downloads: startup crash recovery for DOWNLOADING rows
  - poll_and_download_job: scheduled job that polls RSS feeds and downloads videos
  - python -m crosspost entry point with signal handlers and graceful shutdown

affects:
  - phase-02-processing (scheduler runs the full pipeline continuously)

tech-stack:
  added: [apscheduler>=3.10.0 (already in deps), SQLAlchemyJobStore]
  patterns:
    - Scheduled job receives only picklable AppSettings -- creates engine internally per-run
    - Separate _jobs.db SQLite file prevents lock contention with content database
    - Crash recovery runs once at startup before scheduler loop begins
    - Job registered with replace_existing=True and explicit coalesce/max_instances on add_job

key-files:
  created:
    - src/crosspost/scheduler.py
    - src/crosspost/__main__.py
    - tests/test_scheduler.py
    - tests/test_integration.py
  modified: []

key-decisions:
  - "poll_and_download_job takes only AppSettings (not Engine) -- APScheduler pickles job args for persistent store; Engine not picklable"
  - "Job store uses separate SQLite file (_jobs.db) to avoid lock contention with content database"
  - "coalesce=True and max_instances=1 passed explicitly to add_job (not just job_defaults) to be accessible on pending jobs before scheduler starts"
  - "Signal handler catches SchedulerNotRunningError to handle double-SIGTERM gracefully"

patterns-established:
  - "Scheduler pattern: settings-only job args for picklability with SQLite job store"
  - "Crash recovery pattern: recover_incomplete_downloads called before scheduler.start()"
  - "Initial poll pattern: run poll_and_download_job once before scheduler.start() for immediate execution"

requirements-completed: [AUTO-01, AUTO-02, AUTO-03]

duration: 6min
completed: 2026-03-14
---

# Phase 1 Plan 3: Scheduler and Entry Point Summary

**APScheduler-based unattended pipeline wiring feeds.py + downloader.py with SQLite job store, crash recovery, and graceful signal handling via `python -m crosspost`**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-14T16:33:33Z
- **Completed:** 2026-03-14T16:39:48Z
- **Tasks:** 2 (Task 1 TDD: 3 commits; Task 2: 1 commit)
- **Files modified:** 4 created

## Accomplishments
- Full unattended pipeline wired: RSS poll -> discover -> filter by duration -> download -> state tracking runs continuously
- APScheduler with SQLAlchemyJobStore using separate `_jobs.db` SQLite file prevents lock contention
- Crash recovery resets any DOWNLOADING rows to DISCOVERED on startup
- `python -m crosspost` entry point with SIGINT/SIGTERM graceful shutdown and initial poll before loop
- 74 tests across all modules, all green

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: Failing scheduler tests** - `0f8312a` (test)
2. **Task 1 GREEN: Scheduler implementation** - `674862d` (feat)
3. **Task 2: Entry point + integration tests + deviation fixes** - `d5eaf28` (feat)

_Note: TDD task had RED + GREEN commits. Deviation fixes folded into Task 2 commit._

## Files Created/Modified
- `src/crosspost/scheduler.py` - APScheduler setup, recover_incomplete_downloads, poll_and_download_job, create_scheduler
- `src/crosspost/__main__.py` - Entry point: config load, DB init, crash recovery, signal handlers, scheduler.start()
- `tests/test_scheduler.py` - 12 tests covering scheduler creation, job store, coalesce, crash recovery, job execution
- `tests/test_integration.py` - 3 end-to-end tests: full pipeline, dedup across polls, crash recovery

## Decisions Made
- **Engine not passed to scheduled job:** APScheduler serializes job args via pickle for the SQLite job store. `Engine` objects are not picklable. The job creates a fresh engine from `settings.database_url` on each invocation. `AppSettings` (Pydantic BaseSettings) is picklable.
- **Explicit job params over job_defaults:** APScheduler only applies `job_defaults` to jobs when the scheduler starts. Tests inspect `job.coalesce` before `scheduler.start()`. Passing `coalesce=True, max_instances=1` explicitly to `add_job` ensures attributes are set on pending jobs too.
- **Signal handler guards:** Added try/except around `scheduler.shutdown(wait=False)` to handle `SchedulerNotRunningError` when SIGTERM is received twice (e.g., from `timeout` command).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Engine is not picklable; poll_and_download_job signature changed**
- **Found during:** Task 2 (smoke test of python -m crosspost)
- **Issue:** Plan specified passing `engine` as job arg to APScheduler. SQLAlchemy Engine has un-picklable lambda closures; APScheduler's SQLAlchemyJobStore uses pickle to persist job state, causing `AttributeError: Can't get local object 'create_engine.<locals>.connect'` on scheduler.start().
- **Fix:** Changed `poll_and_download_job(settings, engine)` to `poll_and_download_job(settings)`. Job creates its own engine from `settings.database_url` per-invocation. `create_scheduler` still accepts `engine` parameter for consistency but does not pass it to the job.
- **Files modified:** `src/crosspost/scheduler.py`, `src/crosspost/__main__.py`, `tests/test_scheduler.py`
- **Verification:** Smoke test completes without error; all 74 tests pass
- **Committed in:** `d5eaf28`

**2. [Rule 1 - Bug] APScheduler attribute is `_jobstores` not `_job_stores`**
- **Found during:** Task 1 GREEN (test_create_scheduler_has_sqlalchemy_job_store)
- **Issue:** Test used `scheduler._job_stores` but APScheduler 3.x uses `scheduler._jobstores`
- **Fix:** Updated test attribute reference
- **Files modified:** `tests/test_scheduler.py`
- **Verification:** Test passes
- **Committed in:** `674862d`

**3. [Rule 1 - Bug] coalesce/max_instances not accessible on pending jobs via job_defaults**
- **Found during:** Task 1 GREEN (test_job_coalesce)
- **Issue:** `job_defaults` is only applied when scheduler starts; `job.coalesce` raises AttributeError on pending jobs
- **Fix:** Pass `coalesce=True, max_instances=1, misfire_grace_time=...` explicitly to `add_job()`
- **Files modified:** `src/crosspost/scheduler.py`
- **Verification:** `job.coalesce` returns True before scheduler.start()
- **Committed in:** `674862d`

---

**Total deviations:** 3 auto-fixed (Rule 1 x3 - APScheduler behavioral bugs)
**Impact on plan:** All auto-fixes required for correct operation. No scope creep.

## Issues Encountered
- APScheduler `replace_existing=True` does not deduplicate jobs when the scheduler is not running (pending state); this only works when the scheduler reconnects to a persistent store on restart. Test was rewritten to verify the correct invariant: one youtube_poll job exists after create_scheduler.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Complete Phase 1: config system, database models, RSS feed polling, yt-dlp downloading, APScheduler pipeline, entry point
- All requirements AUTO-01 through AUTO-03 satisfied
- Ready for Phase 2: video processing (transcoding, metadata enrichment)
- Concern: yt-dlp PO Token support for geo-restricted or bot-challenged channels is unverified; may require investigation before Phase 2

---
*Phase: 01-pipeline-foundation*
*Completed: 2026-03-14*

## Self-Check: PASSED
All files and commits verified.
