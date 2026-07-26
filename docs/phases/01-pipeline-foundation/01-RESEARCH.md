# Phase 1: Pipeline Foundation - Research

**Researched:** 2026-03-14
**Domain:** YouTube acquisition pipeline -- RSS polling, yt-dlp download, SQLite state machine, APScheduler scheduling, YAML config
**Confidence:** HIGH

## Summary

Phase 1 builds the unattended YouTube video discovery and download pipeline from scratch. The core components are well-established Python libraries with stable APIs: feedparser for RSS Atom feed parsing, yt-dlp as a Python library (not subprocess) for metadata extraction and video download, SQLModel/SQLite for state persistence and deduplication, APScheduler 3.x with SQLite-backed job persistence for scheduling, and Pydantic Settings with YAML source for configuration.

The most consequential implementation decision is yt-dlp's PO Token support. YouTube now binds PO Tokens to individual video IDs, making manual token extraction impractical. The recommended approach is installing the `bgutil-ytdlp-pot-provider` plugin, which runs a companion HTTP server (Node.js or Docker) that automatically generates tokens per-request. This must be operational from day one -- server datacenter IPs get flagged within hours without proper authentication.

**Primary recommendation:** Build the pipeline as independent modules (config, models, feed poller, downloader, scheduler) that communicate exclusively through SQLite state transitions. Use yt-dlp's `extract_info(url, download=False)` for metadata-only extraction (including duration) before committing to download.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Only download videos <= 3 minutes (configurable via YAML, default 180 seconds)
- Duration obtained from yt-dlp metadata before download -- skip videos exceeding threshold
- Applies to both regular videos and Shorts
- SQLite with content table tracking status: DISCOVERED -> DOWNLOADED -> PROCESSED -> TRANSLATED -> PUBLISHED / FAILED
- Deduplication by video ID -- persistent across restarts
- All state defined upfront even though Phase 1 only uses DISCOVERED -> DOWNLOADED
- YAML config file for channel list, credentials, schedule intervals, filter rules
- No web UI -- config file + CLI is sufficient for v1
- Pydantic Settings for validation and type safety
- RSS feed polling (no API key needed): `https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID`
- RSS returns last 15 videos -- polling interval must be frequent enough for high-output channels
- yt-dlp with Firefox cookies + PO Token support from day one
- APScheduler with configurable polling interval
- SQLite-backed job persistence for APScheduler (survives restarts)

### Claude's Discretion
- SQLite schema details and column design
- Project directory structure and module organization
- Logging configuration (Loguru)
- Error handling patterns and retry logic
- Exact APScheduler job configuration

### Deferred Ideas (OUT OF SCOPE)
- Web management UI for viewing conversion status, upload history, and managing subscriptions
- AI smart editing -- auto-extract key points from long videos and compress to short clips
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| ACQ-01 | YouTube RSS channel monitoring (videos + Shorts) | feedparser Atom parsing with yt:videoId namespace extraction; RSS returns last 15 entries per channel |
| ACQ-02 | yt-dlp video download with metadata (title, description, thumbnail) | yt-dlp Python API with extract_info() + download(); writethumbnail and writeinfojson options |
| ACQ-03 | YAML config for channel list | Pydantic Settings v2 with YamlConfigSettingsSource; nested model validation |
| ACQ-04 | Duration filter (default <= 3 minutes) | yt-dlp extract_info(download=False) returns duration in seconds; filter before download call |
| AUTO-01 | APScheduler periodic YouTube polling | BackgroundScheduler with IntervalTrigger; SQLAlchemyJobStore for persistence |
| AUTO-02 | SQLite dedup (no re-download across restarts) | SQLModel content table with unique video_id column; check-before-insert pattern |
| AUTO-03 | State machine with crash recovery | SQLModel enum field for status; all transitions write to DB before proceeding; APScheduler coalesce + misfire_grace_time for recovery |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| yt-dlp | 2025.x+ (latest) | Video metadata extraction and download | De facto standard, 2000+ sites, active maintenance, Python library API |
| feedparser | 6.0.x | YouTube RSS/Atom feed parsing | Universal feed parser, handles all Atom/RSS variants, mature |
| SQLModel | 0.0.22+ | ORM for SQLite state persistence | Unifies Pydantic validation with SQLAlchemy ORM, type-safe |
| APScheduler | 3.10.x | Periodic job scheduling | In-process scheduler with SQLite job persistence, no external broker |
| pydantic-settings | 2.x | Configuration management | Type-safe settings with YAML source support |
| Loguru | 0.7.x | Structured logging | Zero-config, built-in rotation, exception formatting |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tenacity | 9.x | Retry with exponential backoff | All external calls (RSS fetch, yt-dlp download) |
| PyYAML | 6.x | YAML parsing (dependency of pydantic-settings[yaml]) | Transitive dependency, not used directly |
| bgutil-ytdlp-pot-provider | latest | PO Token generation for YouTube | Required for reliable downloads on server IPs |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| feedparser | aiohttp + xml.etree | feedparser handles malformed feeds, encoding issues, date normalization |
| APScheduler 3.x | APScheduler 4.x (async) | 4.x is still alpha; 3.x is stable and well-documented |
| SQLModel | raw SQLAlchemy | SQLModel gives free Pydantic validation on models |
| pydantic-settings | plain PyYAML + dataclasses | Lose type validation, env var override, nested model support |

**Installation:**
```bash
uv init crosspost
cd crosspost
uv add yt-dlp feedparser sqlmodel apscheduler pydantic-settings[yaml] loguru tenacity
uv add bgutil-ytdlp-pot-provider
```

## Architecture Patterns

### Recommended Project Structure
```
crosspost/
├── src/
│   └── crosspost/
│       ├── __init__.py
│       ├── __main__.py         # Entry point: scheduler start, signal handling
│       ├── config.py           # Pydantic Settings with YAML source
│       ├── models.py           # SQLModel tables: Content, enums
│       ├── database.py         # Engine creation, session management
│       ├── feeds.py            # YouTube RSS polling with feedparser
│       ├── downloader.py       # yt-dlp wrapper: metadata extraction + download
│       └── scheduler.py        # APScheduler setup, job definitions
├── config.yaml                 # User configuration (channel list, settings)
├── pyproject.toml
└── tests/
    ├── test_config.py
    ├── test_models.py
    ├── test_feeds.py
    ├── test_downloader.py
    └── test_scheduler.py
```

### Pattern 1: yt-dlp as Python Library (Metadata + Download)

**What:** Use yt-dlp's `YoutubeDL` class directly instead of subprocess calls.
**When to use:** All video metadata extraction and download operations.

```python
import yt_dlp

# Step 1: Extract metadata without downloading
def get_video_metadata(video_url: str) -> dict | None:
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'cookiesfrombrowser': ('firefox', None, None, None),  # MUST be tuple
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        return info  # contains 'duration', 'title', 'description', 'thumbnail', etc.

# Step 2: Download with full options
def download_video(video_url: str, output_dir: str) -> dict:
    opts = {
        'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
        'outtmpl': f'{output_dir}/%(id)s.%(ext)s',
        'writethumbnail': True,
        'writeinfojson': True,
        'cookiesfrombrowser': ('firefox', None, None, None),
        'quiet': True,
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(video_url, download=True)
        return info
```

**Critical:** The `cookiesfrombrowser` parameter MUST be a tuple `('firefox', None, None, None)`, NOT a string. Passing a string causes it to be unpacked character-by-character, triggering a TypeError.

### Pattern 2: YouTube RSS Feed Parsing

**What:** Parse YouTube Atom feeds to discover new videos.
**When to use:** Periodic channel polling for new content.

```python
import feedparser

YOUTUBE_RSS_URL = "https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

def poll_channel(channel_id: str) -> list[dict]:
    feed_url = YOUTUBE_RSS_URL.format(channel_id=channel_id)
    feed = feedparser.parse(feed_url)

    videos = []
    for entry in feed.entries:
        # YouTube Atom feeds use yt: namespace
        # feedparser normalizes the yt:videoId tag
        video_id = entry.get('yt_videoid', '')
        if not video_id:
            # Fallback: extract from entry.id (format: yt:video:VIDEO_ID)
            raw_id = entry.get('id', '')
            if raw_id.startswith('yt:video:'):
                video_id = raw_id.split('yt:video:')[1]
            else:
                # Last resort: extract from link
                video_id = entry.link.split('v=')[-1].split('&')[0]

        videos.append({
            'video_id': video_id,
            'title': entry.title,
            'published': entry.published,
            'link': entry.link,
            # media:group fields available via feedparser
            'description': getattr(entry, 'media_description', ''),
            'thumbnail': getattr(entry, 'media_thumbnail', [{}])[0].get('url', ''),
        })
    return videos
```

**YouTube Atom feed structure** (per entry):
```xml
<entry>
  <id>yt:video:VIDEO_ID</id>
  <yt:videoId>VIDEO_ID</yt:videoId>
  <yt:channelId>CHANNEL_ID</yt:channelId>
  <title>Video Title</title>
  <link rel="alternate" href="https://www.youtube.com/watch?v=VIDEO_ID"/>
  <published>2026-03-14T12:00:00+00:00</published>
  <updated>2026-03-14T12:00:00+00:00</updated>
  <media:group>
    <media:title>Video Title</media:title>
    <media:content url="..." type="application/x-shockwave-flash" width="640" height="390"/>
    <media:thumbnail url="https://i1.ytimg.com/vi/VIDEO_ID/hqdefault.jpg" width="480" height="360"/>
    <media:description>Video description text</media:description>
  </media:group>
</entry>
```

**Key facts:**
- RSS returns the last 15 videos only -- no pagination
- Shorts and regular videos appear identically in the feed -- distinguish via yt-dlp metadata (duration)
- feedparser normalizes namespace-prefixed tags: `yt:videoId` becomes `yt_videoid` in the entry dict

### Pattern 3: SQLModel State Machine

**What:** Define all pipeline states upfront as an enum; content table tracks each video through its lifecycle.
**When to use:** Every state transition in the pipeline.

```python
import enum
from datetime import datetime
from sqlmodel import SQLModel, Field, Column
from sqlalchemy import Enum as SAEnum, String

class ContentStatus(str, enum.Enum):
    DISCOVERED = "discovered"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    PROCESSED = "processed"
    TRANSLATED = "translated"
    PUBLISHED = "published"
    FAILED = "failed"

class Content(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    video_id: str = Field(sa_column=Column(String, unique=True, index=True))
    channel_id: str
    title: str
    description: str = ""
    duration: int = 0  # seconds
    thumbnail_url: str = ""
    video_url: str = ""
    published_at: datetime | None = None

    status: ContentStatus = Field(
        default=ContentStatus.DISCOVERED,
        sa_column=Column(SAEnum(ContentStatus))
    )

    # File paths (populated after download)
    video_path: str | None = None
    thumbnail_path: str | None = None
    metadata_path: str | None = None

    # Timestamps
    discovered_at: datetime = Field(default_factory=datetime.utcnow)
    downloaded_at: datetime | None = None
    failed_at: datetime | None = None
    error_message: str | None = None
```

**For SQLite:** The `SAEnum` type stores values as VARCHAR strings, which is correct for SQLite (no native enum type). The `(str, enum.Enum)` base class ensures JSON serialization works with Pydantic.

### Pattern 4: Pydantic Settings with YAML

**What:** Type-safe configuration loaded from YAML with env var override support.
**When to use:** Application startup configuration.

```python
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings import YamlConfigSettingsSource, PydanticBaseSettingsSource

class ChannelConfig(BaseModel):
    channel_id: str
    name: str = ""
    max_duration: int = 180  # seconds, per-channel override

class DownloadConfig(BaseModel):
    output_dir: str = "./downloads"
    max_duration: int = 180  # default 3 minutes
    format: str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    cookies_browser: str = "firefox"

class ScheduleConfig(BaseModel):
    poll_interval_minutes: int = 30
    misfire_grace_time: int = 300  # seconds

class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        yaml_file="config.yaml",
        yaml_file_encoding="utf-8",
    )

    channels: list[ChannelConfig] = []
    download: DownloadConfig = DownloadConfig()
    schedule: ScheduleConfig = ScheduleConfig()
    database_url: str = "sqlite:///crosspost.db"
    log_level: str = "INFO"

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(settings_cls),
        )
```

Corresponding `config.yaml`:
```yaml
channels:
  - channel_id: "UCxxxxxxxxxxxxxxxxxxxxxx"
    name: "Example Channel"
    max_duration: 300

download:
  output_dir: "./downloads"
  max_duration: 180
  cookies_browser: "firefox"

schedule:
  poll_interval_minutes: 30

database_url: "sqlite:///crosspost.db"
log_level: "DEBUG"
```

### Pattern 5: APScheduler with SQLite Persistence

**What:** Background scheduler with persistent job store that survives restarts.
**When to use:** Main application loop for periodic polling.

```python
import atexit
import signal
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
from apscheduler.triggers.interval import IntervalTrigger

def create_scheduler(database_url: str, poll_interval_minutes: int) -> BlockingScheduler:
    jobstores = {
        'default': SQLAlchemyJobStore(url=database_url)
    }
    job_defaults = {
        'coalesce': True,         # Merge missed runs into one
        'max_instances': 1,       # Never overlap polling jobs
        'misfire_grace_time': 300  # 5 min grace for missed jobs
    }

    scheduler = BlockingScheduler(
        jobstores=jobstores,
        job_defaults=job_defaults,
    )

    # CRITICAL: use replace_existing=True with explicit ID
    # Otherwise, every restart creates a duplicate job
    scheduler.add_job(
        poll_all_channels,
        trigger=IntervalTrigger(minutes=poll_interval_minutes),
        id='youtube_poll',
        replace_existing=True,
        name='Poll YouTube channels for new videos',
    )

    return scheduler

def run():
    scheduler = create_scheduler(
        database_url="sqlite:///jobs.db",  # Separate from content DB
        poll_interval_minutes=30,
    )

    # Graceful shutdown
    def shutdown(signum=None, frame=None):
        scheduler.shutdown(wait=False)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    atexit.register(lambda: scheduler.shutdown(wait=False))

    scheduler.start()  # Blocks until shutdown
```

### Anti-Patterns to Avoid

- **Calling yt-dlp as subprocess:** Use the Python API directly. Subprocess loses structured metadata access and error handling.
- **Downloading before checking duration:** Always call `extract_info(download=False)` first, check `info['duration']`, then decide whether to download.
- **Missing `replace_existing=True` on APScheduler jobs:** Without this, every application restart creates a new copy of the job in the persistent store, causing duplicate polling.
- **Passing `cookiesfrombrowser` as a string:** Must be a 4-element tuple: `('firefox', None, None, None)`.
- **Not defining explicit job IDs in APScheduler:** Required when using persistent job stores; without explicit IDs, jobs accumulate on restart.
- **Storing binary blobs in SQLite:** Store file paths only; keep videos and thumbnails on the filesystem.
- **Using a single SQLite file for APScheduler and content:** Separate them to avoid lock contention.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YouTube video download | HTTP client + stream assembly | yt-dlp YoutubeDL class | YouTube's format negotiation, DASH/HLS, DRM, throttling, PO Tokens -- enormous complexity |
| RSS/Atom parsing | xml.etree + manual namespace handling | feedparser | Handles malformed feeds, encoding detection, date normalization, 20+ feed formats |
| PO Token generation | BotGuard reverse engineering | bgutil-ytdlp-pot-provider plugin | Tokens are bound per-video-ID, require BotGuard attestation challenge response |
| Job scheduling persistence | Custom cron + pickle state | APScheduler SQLAlchemyJobStore | Handles missed jobs, coalescing, concurrent execution limits, timezone handling |
| Config validation | argparse + manual YAML parsing | Pydantic Settings + YamlConfigSettingsSource | Type coercion, nested models, env var override, validation error messages |
| Retry with backoff | try/except + sleep loops | tenacity | Configurable retry count, exponential backoff, jitter, per-exception filtering |

**Key insight:** The YouTube acquisition domain is deceptively complex. YouTube's anti-bot measures (PO Tokens, SABR streaming, cookie rotation) and feed format quirks (namespace handling, last-15-only limitation) mean hand-rolling any part of the acquisition path will break within days on a server IP.

## Common Pitfalls

### Pitfall 1: yt-dlp cookiesfrombrowser TypeError
**What goes wrong:** Passing `'cookiesfrombrowser': 'firefox'` as a string causes yt-dlp to unpack it character by character, throwing a TypeError.
**Why it happens:** The Python API expects a tuple, but the CLI handles the string-to-tuple conversion internally.
**How to avoid:** Always pass as tuple: `('firefox', None, None, None)`. Alternatively, use `yt_dlp.parse_options(['--cookies-from-browser', 'firefox']).ydl_opts` to get correctly-typed options.
**Warning signs:** `TypeError` mentioning unexpected number of arguments in cookie extraction.

### Pitfall 2: APScheduler Job Duplication on Restart
**What goes wrong:** Each application restart adds a new copy of the polling job to the SQLite store, causing N parallel polls after N restarts.
**Why it happens:** Persistent job stores remember jobs across restarts. Without `replace_existing=True` and an explicit `id`, APScheduler creates a new job entry each time.
**How to avoid:** Always set `id='unique_name'` and `replace_existing=True` when adding jobs to a persistent store.
**Warning signs:** Multiple simultaneous downloads of the same videos; log entries showing the same poll job firing multiple times per interval.

### Pitfall 3: YouTube RSS Feed Returns Only Last 15 Videos
**What goes wrong:** High-output channels (multiple uploads per day) can push videos off the 15-entry feed before the next poll.
**Why it happens:** YouTube RSS feeds have no pagination and a fixed 15-entry limit.
**How to avoid:** Poll frequently enough for your highest-output channel. For channels posting 3+ videos/day, poll at least every 2 hours. For most channels, 30-minute intervals are safe.
**Warning signs:** Gaps in discovered videos compared to channel page; missed videos never appear in the database.

### Pitfall 4: Server IP Flagged by YouTube Within Hours
**What goes wrong:** Downloads start failing with 403 errors or throttled to unusable speeds after the first few hours of operation.
**Why it happens:** YouTube's bot detection (PO Token/SABR system) flags datacenter IP ranges aggressively.
**How to avoid:** Configure Firefox cookies from day one. Install and run the bgutil-ytdlp-pot-provider HTTP server. Update yt-dlp weekly. Monitor download success rate.
**Warning signs:** HTTP 403 errors; downloads taking 10x+ longer than expected; yt-dlp warnings about "Sign in to confirm you're not a bot".

### Pitfall 5: SQLModel Enum Handling Changes
**What goes wrong:** Enum values stored incorrectly or type errors during serialization/deserialization.
**Why it happens:** SQLModel changed how `(str, Enum)` fields are handled across versions. Recent versions may create native DB enum types instead of VARCHAR.
**How to avoid:** Explicitly use `sa_column=Column(SAEnum(ContentStatus))` to control database column type. For SQLite, this stores as VARCHAR which is correct.
**Warning signs:** Errors about enum type mismatch; values stored as integers instead of strings.

### Pitfall 6: Missing Crash Recovery for In-Progress Downloads
**What goes wrong:** A crash during download leaves a video in DISCOVERED state with partial files on disk.
**Why it happens:** Status transition happens after download completes; crash means the transition never fires.
**How to avoid:** Add a DOWNLOADING intermediate state. On startup, find all DOWNLOADING entries and either retry or clean up partial files. Use yt-dlp's built-in partial download recovery.
**Warning signs:** Orphaned partial files in the download directory; videos stuck in DOWNLOADING state after restart.

## Code Examples

### Duration-Based Filtering Before Download

```python
def should_download(video_url: str, max_duration: int = 180) -> tuple[bool, dict | None]:
    """Check video duration before committing to download.

    Returns (should_download, metadata_dict).
    """
    opts = {
        'quiet': True,
        'no_warnings': True,
        'cookiesfrombrowser': ('firefox', None, None, None),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(video_url, download=False)
        duration = info.get('duration', 0)
        if duration and duration > max_duration:
            return False, info
        return True, info
```

### Database Session and Deduplication Check

```python
from sqlmodel import Session, create_engine, select

engine = create_engine("sqlite:///crosspost.db")

def video_exists(video_id: str) -> bool:
    with Session(engine) as session:
        stmt = select(Content).where(Content.video_id == video_id)
        return session.exec(stmt).first() is not None

def insert_discovered(video_data: dict) -> Content:
    content = Content(
        video_id=video_data['video_id'],
        channel_id=video_data['channel_id'],
        title=video_data['title'],
        description=video_data.get('description', ''),
        video_url=f"https://www.youtube.com/watch?v={video_data['video_id']}",
        status=ContentStatus.DISCOVERED,
    )
    with Session(engine) as session:
        session.add(content)
        session.commit()
        session.refresh(content)
    return content
```

### Complete Poll-and-Download Flow

```python
from loguru import logger

def poll_and_download(settings: AppSettings):
    """Main job function called by APScheduler."""
    for channel in settings.channels:
        max_dur = channel.max_duration or settings.download.max_duration
        logger.info(f"Polling channel {channel.name} ({channel.channel_id})")

        try:
            videos = poll_channel(channel.channel_id)
        except Exception as e:
            logger.error(f"Failed to poll {channel.channel_id}: {e}")
            continue

        for video in videos:
            if video_exists(video['video_id']):
                continue

            # Insert as DISCOVERED
            content = insert_discovered({**video, 'channel_id': channel.channel_id})
            logger.info(f"Discovered: {video['title']} ({video['video_id']})")

            # Check duration before download
            should_dl, metadata = should_download(content.video_url, max_dur)
            if not should_dl:
                logger.info(
                    f"Skipping (duration {metadata.get('duration', '?')}s > {max_dur}s): "
                    f"{video['title']}"
                )
                continue

            # Update duration from metadata
            update_content(content.id, duration=metadata.get('duration', 0))

            # Download
            try:
                update_status(content.id, ContentStatus.DOWNLOADING)
                result = download_video(content.video_url, settings.download.output_dir)
                update_content(content.id,
                    status=ContentStatus.DOWNLOADED,
                    video_path=result.get('filepath', ''),
                    downloaded_at=datetime.utcnow(),
                )
                logger.info(f"Downloaded: {video['title']}")
            except Exception as e:
                update_content(content.id,
                    status=ContentStatus.FAILED,
                    error_message=str(e),
                    failed_at=datetime.utcnow(),
                )
                logger.error(f"Download failed for {video['video_id']}: {e}")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual PO Token extraction | PO Token Provider plugins (bgutil) | Mid-2025 | Tokens are now per-video-ID; manual extraction is impractical |
| yt-dlp subprocess calls | yt-dlp Python library API | Always available | Structured data access, proper error handling, no shell injection risk |
| APScheduler 4.x (async) | APScheduler 3.10.x (stable) | 4.x still alpha in 2026 | 3.x is production-ready; 4.x API not finalized |
| Custom YAML + dataclass | Pydantic Settings v2 + YamlConfigSettingsSource | 2024 | Built-in YAML source, nested model support, env override |
| youtube-dl | yt-dlp | 2021 fork | youtube-dl effectively unmaintained; yt-dlp is the community standard |

**Deprecated/outdated:**
- youtube-dl: Unmaintained; use yt-dlp
- APScheduler 4.x: Not ready for production (alpha)
- Manual PO Token via browser console: Tokens now per-video-ID, impractical for automation

## Open Questions

1. **feedparser namespace tag normalization**
   - What we know: feedparser converts `yt:videoId` to `yt_videoid` in entry dicts
   - What's unclear: Exact attribute name may vary across feedparser versions; need to verify with a live YouTube feed
   - Recommendation: Implement fallback extraction from entry.id (`yt:video:VIDEO_ID` format) and entry.link (`?v=VIDEO_ID`)

2. **bgutil-ytdlp-pot-provider on headless server**
   - What we know: Runs as HTTP server on port 4416; available as Docker image or Node.js app
   - What's unclear: Whether Node.js/Docker dependency is acceptable for this project's deployment model
   - Recommendation: Use Docker deployment if available; otherwise install Node.js alongside Python. Document as infrastructure dependency.

3. **APScheduler SQLite vs application SQLite**
   - What we know: APScheduler needs a SQLAlchemy URL for its job store; application uses SQLModel for content
   - What's unclear: Whether sharing the same SQLite database file is safe or if separate databases are better
   - Recommendation: Use separate SQLite files (`crosspost.db` for content, `jobs.db` for APScheduler) to avoid lock contention and simplify schema management

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x |
| Config file | None -- Wave 0 |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ACQ-01 | RSS feed returns parsed video entries | unit | `uv run pytest tests/test_feeds.py -x` | Wave 0 |
| ACQ-02 | yt-dlp downloads video with metadata files | integration | `uv run pytest tests/test_downloader.py -x` | Wave 0 |
| ACQ-03 | YAML config loads and validates | unit | `uv run pytest tests/test_config.py -x` | Wave 0 |
| ACQ-04 | Videos exceeding duration threshold are skipped | unit | `uv run pytest tests/test_downloader.py::test_duration_filter -x` | Wave 0 |
| AUTO-01 | Scheduler fires polling job on interval | integration | `uv run pytest tests/test_scheduler.py -x` | Wave 0 |
| AUTO-02 | Duplicate video_id is not re-inserted | unit | `uv run pytest tests/test_models.py::test_dedup -x` | Wave 0 |
| AUTO-03 | State transitions persist; DOWNLOADING recovered on restart | unit | `uv run pytest tests/test_models.py::test_state_machine -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `pyproject.toml` -- project initialization with uv, pytest dependency
- [ ] `tests/conftest.py` -- shared fixtures (in-memory SQLite engine, sample feed data, mock yt-dlp)
- [ ] `tests/test_config.py` -- YAML loading, validation, defaults
- [ ] `tests/test_models.py` -- Content table CRUD, dedup, state transitions
- [ ] `tests/test_feeds.py` -- feedparser output parsing (mock HTTP)
- [ ] `tests/test_downloader.py` -- metadata extraction, duration filter (mock yt-dlp)
- [ ] `tests/test_scheduler.py` -- scheduler setup, job registration
- [ ] Framework install: `uv add --dev pytest pytest-mock`

## Sources

### Primary (HIGH confidence)
- [yt-dlp GitHub - YoutubeDL.py](https://github.com/yt-dlp/yt-dlp/blob/master/yt_dlp/YoutubeDL.py) - Python API params documentation
- [yt-dlp PO Token Guide](https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide) - PO Token requirements, provider plugin system
- [APScheduler 3.x User Guide](https://apscheduler.readthedocs.io/en/3.x/userguide.html) - SQLAlchemyJobStore, triggers, shutdown
- [Pydantic Settings docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) - YamlConfigSettingsSource, custom sources
- [SQLModel Issue #96](https://github.com/fastapi/sqlmodel/issues/96) - Enum column patterns with sa_column
- [yt-dlp Issue #10196](https://github.com/yt-dlp/yt-dlp/issues/10196) - cookiesfrombrowser tuple format requirement
- [bgutil-ytdlp-pot-provider](https://github.com/Brainicism/bgutil-ytdlp-pot-provider) - PO Token provider installation

### Secondary (MEDIUM confidence)
- [feedparser PyPI](https://pypi.org/project/feedparser/) - Version and capabilities
- [YouTube RSS feed structure](https://www.nextstruggle.com/using-rss-feeds-to-extract-youtube-channel-data-with-python/askdushyant/) - Feed entry fields
- [6 Ways to Get YouTube Cookies for yt-dlp (2026)](https://dev.to/osovsky/6-ways-to-get-youtube-cookies-for-yt-dlp-in-2026-only-1-works-2cnb) - Current cookie extraction status
- [APScheduler SQLAlchemyJobStore API](https://apscheduler.readthedocs.io/en/3.x/modules/jobstores/sqlalchemy.html) - Job store configuration

### Tertiary (LOW confidence)
- feedparser namespace tag normalization for `yt:videoId` -- derived from documentation patterns, not verified with live feed
- bgutil provider Docker deployment on headless Linux server -- referenced but not tested

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries are mature, well-documented, and widely used
- Architecture: HIGH - patterns derived from official documentation and verified GitHub issues
- Pitfalls: HIGH - cookiesfrombrowser tuple format and APScheduler job duplication confirmed via GitHub issues
- yt-dlp PO Token: MEDIUM - ecosystem is actively evolving; bgutil plugin is current recommended approach but may change
- feedparser namespace handling: MEDIUM - namespace normalization rules derived from docs, not tested with live YouTube feed

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (30 days; yt-dlp PO Token ecosystem may shift sooner)
