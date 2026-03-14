"""Application entry point for CrossPost.

Starts the APScheduler-based polling pipeline:
  1. Load configuration from config.yaml in the current directory.
  2. Configure logging via loguru.
  3. Create the SQLite database engine and ensure tables exist.
  4. Recover any DOWNLOADING rows left over from a prior crash.
  5. Create the scheduler.
  6. Run an immediate poll before handing off to the scheduler loop.
  7. Register signal handlers for graceful shutdown.
  8. Block in scheduler.start() until shutdown is requested.

Usage:
    uv run python -m crosspost
"""

import atexit
import signal
import sys

from loguru import logger

from crosspost.config import AppSettings
from crosspost.database import get_engine, init_db
from crosspost.scheduler import create_scheduler, poll_and_download_job, recover_incomplete_downloads


def main() -> None:
    """Main application entry point."""
    # ------------------------------------------------------------------
    # 1. Load settings from config.yaml in the current directory
    # ------------------------------------------------------------------
    settings = AppSettings(_yaml_file="config.yaml")

    # ------------------------------------------------------------------
    # 2. Configure loguru
    # ------------------------------------------------------------------
    logger.remove()  # Remove default stderr handler
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | {message}",
    )

    # ------------------------------------------------------------------
    # 3. Create DB engine and ensure tables exist
    # ------------------------------------------------------------------
    engine = get_engine(settings.database_url)
    init_db(engine)

    # ------------------------------------------------------------------
    # 4. Crash recovery for interrupted downloads
    # ------------------------------------------------------------------
    recovered = recover_incomplete_downloads(engine)

    # ------------------------------------------------------------------
    # 5. Log startup info
    # ------------------------------------------------------------------
    logger.info(
        "CrossPost starting: {} channel(s) configured, poll_interval={}min, db={}",
        len(settings.channels),
        settings.schedule.poll_interval_minutes,
        settings.database_url,
    )
    if recovered:
        logger.info("Recovered {} interrupted download(s) from previous session", recovered)

    # ------------------------------------------------------------------
    # 6. Create scheduler
    # ------------------------------------------------------------------
    scheduler = create_scheduler(settings, engine)

    # ------------------------------------------------------------------
    # 7. Register signal handlers for graceful shutdown
    # ------------------------------------------------------------------
    def _shutdown(signum, frame):  # noqa: ANN001
        logger.info("Received signal {} — shutting down scheduler", signum)
        try:
            scheduler.shutdown(wait=False)
        except Exception:
            pass  # Scheduler may already be stopped

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    # ------------------------------------------------------------------
    # 8. Register atexit cleanup
    # ------------------------------------------------------------------
    def _cleanup():
        engine.dispose()
        logger.info("Database connections closed")

    atexit.register(_cleanup)

    # ------------------------------------------------------------------
    # 9. Run an immediate poll before starting the timed loop
    # ------------------------------------------------------------------
    logger.info("Running initial poll before scheduler loop starts")
    poll_and_download_job(settings)

    # ------------------------------------------------------------------
    # 10. Start scheduler (blocks until shutdown)
    # ------------------------------------------------------------------
    logger.info("Starting scheduler loop (Ctrl+C to stop)")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped")


if __name__ == "__main__":
    main()
