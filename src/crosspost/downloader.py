"""yt-dlp metadata extraction, duration filtering, and video download."""

from datetime import datetime
from pathlib import Path

import yt_dlp
from loguru import logger
from sqlalchemy.engine import Engine
from sqlmodel import Session, select
from tenacity import retry, stop_after_attempt, wait_exponential

from crosspost.config import AppSettings, ChannelConfig
from crosspost.models import Content, ContentStatus


def get_video_metadata(video_url: str, cookies_browser: str = "firefox") -> dict | None:
    """Extract video metadata without downloading.

    Args:
        video_url: Full YouTube video URL.
        cookies_browser: Browser to extract cookies from (default: firefox).
                         CRITICAL: passed to yt-dlp as a tuple, not a string.

    Returns:
        Info dict from yt-dlp with duration, title, description, thumbnail, etc.
        Returns None on any error.
    """
    opts = {
        "skip_download": True,
        "quiet": True,
        "no_warnings": True,
        # CRITICAL: cookiesfrombrowser MUST be a tuple, not a string.
        # Format: (browser, profile, keyring, container)
        "cookiesfrombrowser": (cookies_browser, None, None, None),
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            return info
    except Exception as exc:
        logger.error("Failed to get metadata for {}: {}", video_url, exc)
        return None


def should_download(metadata: dict, max_duration: int = 180) -> bool:
    """Determine whether a video should be downloaded based on duration.

    Videos with unknown duration (0 or None) are allowed through -- we
    don't block on unknowns.

    Args:
        metadata: Info dict from yt-dlp (or any dict with an optional 'duration' key).
        max_duration: Maximum allowed duration in seconds.

    Returns:
        True if the video should be downloaded, False if it exceeds max_duration.
    """
    duration = metadata.get("duration", 0)
    if not duration:  # None or 0
        return True
    return duration <= max_duration


@retry(stop=stop_after_attempt(2), wait=wait_exponential(multiplier=1, min=1, max=5))
def download_video(
    video_url: str,
    output_dir: str,
    cookies_browser: str = "firefox",
    format_str: str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
) -> dict:
    """Download a video with thumbnail and info JSON using yt-dlp.

    Args:
        video_url: Full YouTube video URL.
        output_dir: Directory to save downloaded files.
        cookies_browser: Browser for cookie extraction (passed as tuple to yt-dlp).
        format_str: yt-dlp format selector string.

    Returns:
        Info dict from yt-dlp after download.
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    opts = {
        "format": format_str,
        "outtmpl": f"{output_dir}/%(id)s.%(ext)s",
        "writethumbnail": True,
        "writeinfojson": True,
        "cookiesfrombrowser": (cookies_browser, None, None, None),
        "quiet": True,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        return ydl.extract_info(video_url, download=True)


def _get_channel_max_duration(settings: AppSettings, channel_id: str) -> int:
    """Resolve effective max_duration for a given channel_id."""
    for channel in settings.channels:
        if channel.channel_id == channel_id:
            if channel.max_duration is not None:
                return channel.max_duration
    return settings.download.max_duration


def process_discovered_videos(engine: Engine, settings: AppSettings) -> int:
    """Process all DISCOVERED content: check duration, download, update state.

    State transitions:
      DISCOVERED -> DOWNLOADING -> DOWNLOADED  (success)
      DISCOVERED -> DOWNLOADING -> FAILED      (download error)
      DISCOVERED -> FAILED                     (metadata fetch error)
      DISCOVERED -> DISCOVERED                 (duration exceeds limit -- skipped)

    Args:
        engine: SQLAlchemy engine.
        settings: Application settings with download config.

    Returns:
        Number of videos successfully downloaded.
    """
    with Session(engine) as session:
        discovered = session.exec(
            select(Content).where(Content.status == ContentStatus.DISCOVERED)
        ).all()

    if not discovered:
        logger.info("No DISCOVERED videos to process")
        return 0

    logger.info("Processing {} DISCOVERED videos", len(discovered))
    downloaded_count = 0

    for content in discovered:
        video_url = content.video_url or f"https://www.youtube.com/watch?v={content.video_id}"

        # Step 1: Fetch metadata
        logger.debug("Fetching metadata for video_id={}", content.video_id)
        metadata = get_video_metadata(video_url, cookies_browser=settings.download.cookies_browser)

        if metadata is None:
            logger.error("Failed to get metadata for video_id={}, marking FAILED", content.video_id)
            with Session(engine) as session:
                item = session.get(Content, content.id)
                if item:
                    item.status = ContentStatus.FAILED
                    item.error_message = "Failed to retrieve video metadata"
                    item.failed_at = datetime.utcnow()
                    session.commit()
            continue

        # Step 2: Update duration from metadata
        duration = metadata.get("duration", 0) or 0

        # Step 3: Duration check
        max_duration = _get_channel_max_duration(settings, content.channel_id)
        if not should_download(metadata, max_duration=max_duration):
            logger.info(
                "Skipping video_id={} (duration={}s exceeds max={}s)",
                content.video_id,
                duration,
                max_duration,
            )
            # Update duration in DB but leave status as DISCOVERED
            with Session(engine) as session:
                item = session.get(Content, content.id)
                if item:
                    item.duration = duration
                    session.commit()
            continue

        # Step 4: Transition to DOWNLOADING
        with Session(engine) as session:
            item = session.get(Content, content.id)
            if item:
                item.status = ContentStatus.DOWNLOADING
                item.duration = duration
                session.commit()

        # Step 5: Download
        try:
            logger.info("Downloading video_id={}", content.video_id)
            info = download_video(
                video_url,
                settings.download.output_dir,
                cookies_browser=settings.download.cookies_browser,
                format_str=settings.download.format,
            )

            # Step 6: Transition to DOWNLOADED
            video_path = None
            requested = info.get("requested_downloads", [])
            if requested:
                video_path = requested[0].get("filepath")

            with Session(engine) as session:
                item = session.get(Content, content.id)
                if item:
                    item.status = ContentStatus.DOWNLOADED
                    item.downloaded_at = datetime.utcnow()
                    item.video_path = video_path
                    session.commit()

            downloaded_count += 1
            logger.info("Successfully downloaded video_id={}", content.video_id)

        except Exception as exc:
            logger.error("Download failed for video_id={}: {}", content.video_id, exc)
            with Session(engine) as session:
                item = session.get(Content, content.id)
                if item:
                    item.status = ContentStatus.FAILED
                    item.error_message = str(exc)
                    item.failed_at = datetime.utcnow()
                    session.commit()

    logger.info("Processed DISCOVERED videos: {}/{} downloaded", downloaded_count, len(discovered))
    return downloaded_count
