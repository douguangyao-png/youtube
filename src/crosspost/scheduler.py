"""APScheduler setup, job definitions, and crash recovery for CrossPost."""

from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from crosspost.config import AppSettings
from crosspost.downloader import process_discovered_videos
from crosspost.feeds import discover_new_videos
from crosspost.models import Content, ContentStatus


def recover_incomplete_downloads(engine: Engine) -> int:
    """Reset DOWNLOADING rows to DISCOVERED so they are retried on next poll.

    Called once on application startup to recover from a crash that left
    content stuck in the DOWNLOADING state.

    Args:
        engine: SQLAlchemy engine connected to the content database.

    Returns:
        Number of Content rows transitioned from DOWNLOADING to DISCOVERED.
    """
    with Session(engine) as session:
        downloading = session.exec(
            select(Content).where(Content.status == ContentStatus.DOWNLOADING)
        ).all()

        if not downloading:
            logger.info("Crash recovery: no DOWNLOADING rows found")
            return 0

        for content in downloading:
            content.status = ContentStatus.DISCOVERED

        session.commit()

    count = len(downloading)
    logger.info("Crash recovery: reset {} DOWNLOADING row(s) to DISCOVERED", count)
    return count


def poll_and_download_job(settings: AppSettings, engine: Engine) -> None:
    """APScheduler job: poll all channels for new videos and download them.

    Iterates over every channel in settings, calls discover_new_videos to
    insert newly found videos into the database, then calls
    process_discovered_videos to fetch metadata, filter by duration, and
    download eligible videos.

    The entire function is wrapped in a broad try/except so that any
    unexpected exception is logged but does not crash the scheduler.

    Args:
        settings: Application configuration containing channel list and
                  download/schedule parameters.
        engine: SQLAlchemy engine connected to the content database.
    """
    try:
        total_discovered = 0
        for channel in settings.channels:
            new_videos = discover_new_videos(engine, channel)
            total_discovered += len(new_videos)

        downloaded = process_discovered_videos(engine, settings)

        logger.info(
            "Poll complete: {} channel(s) polled, {} new video(s) discovered, {} downloaded",
            len(settings.channels),
            total_discovered,
            downloaded,
        )
    except Exception as exc:
        logger.error("poll_and_download_job raised an unexpected error: {}", exc)


def create_scheduler(settings: AppSettings, engine: Engine) -> BlockingScheduler:
    """Create and configure a BlockingScheduler with SQLite-backed job store.

    Uses a separate SQLite database for APScheduler's job store (derived
    from settings.database_url by appending '_jobs') to prevent lock
    contention with the content database.

    Job defaults:
      - coalesce=True (merge missed executions into one)
      - max_instances=1 (no concurrent runs)
      - misfire_grace_time from settings

    The 'youtube_poll' job is added with replace_existing=True so that
    restarting the application does not create duplicate job records.

    Args:
        settings: Application configuration.
        engine: SQLAlchemy engine for the content database (not the job store).

    Returns:
        A configured BlockingScheduler (not yet started).
    """
    # Derive a separate SQLite URL for the job store to avoid lock contention
    base_url = settings.database_url
    if base_url.startswith("sqlite:///"):
        db_path = base_url[len("sqlite:///"):]
        # Strip any existing extension and append _jobs.db
        if db_path.endswith(".db"):
            jobs_db_path = db_path[:-3] + "_jobs.db"
        else:
            jobs_db_path = db_path + "_jobs"
        jobs_url = f"sqlite:///{jobs_db_path}"
    else:
        # For non-SQLite URLs, append _jobs suffix before any query string
        jobs_url = base_url + "_jobs"

    job_store = SQLAlchemyJobStore(url=jobs_url)

    job_defaults = {
        "coalesce": True,
        "max_instances": 1,
        "misfire_grace_time": settings.schedule.misfire_grace_time,
    }

    scheduler = BlockingScheduler(
        jobstores={"default": job_store},
        job_defaults=job_defaults,
    )

    scheduler.add_job(
        poll_and_download_job,
        IntervalTrigger(minutes=settings.schedule.poll_interval_minutes),
        id="youtube_poll",
        replace_existing=True,
        coalesce=True,
        max_instances=1,
        misfire_grace_time=settings.schedule.misfire_grace_time,
        args=[settings, engine],
    )

    return scheduler
