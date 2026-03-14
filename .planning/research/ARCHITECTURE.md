# Architecture Patterns: CrossPost

**Domain:** Cross-platform content syndication / automation pipeline
**Researched:** 2026-03-14
**Overall confidence:** HIGH (patterns well-established; platform-specific details MEDIUM)

---

## Standard Architecture: System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        SCHEDULER LAYER                          │
│              (APScheduler / Celery Beat — cron triggers)        │
└────────────────────────────┬────────────────────────────────────┘
                             │ enqueues jobs
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                         TASK QUEUE                              │
│                    (Redis + Celery Workers)                      │
└──┬──────────────┬──────────────┬──────────────┬────────────────┘
   │              │              │              │
   ▼              ▼              ▼              ▼
┌──────┐      ┌──────┐      ┌──────┐      ┌──────┐
│SOURCE│      │PROC. │      │TRANS.│      │PUBLI-│
│LAYER │─────▶│LAYER │─────▶│LAYER │─────▶│SHER  │
│      │      │      │      │      │      │LAYER │
└──────┘      └──────┘      └──────┘      └──────┘
   │              │              │              │
   └──────────────┴──────────────┴──────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       STORAGE LAYER                             │
│   SQLite (state/metadata) + Local FS (video files/assets)       │
└─────────────────────────────────────────────────────────────────┘
```

Every stage communicates through the task queue and writes/reads state from the storage layer. No stage calls another stage directly — all handoffs are via queued tasks.

---

## Component Responsibilities

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| **Scheduler** | Trigger periodic source-check jobs on cron schedule | Task Queue (enqueues) |
| **Task Queue** | Distribute jobs to workers, manage retries, track results | All workers |
| **Source Layer** | Discover new content from YouTube / X (Twitter), check against dedup store, enqueue download tasks | Task Queue, Storage (state) |
| **Downloader** | Download video/audio/images using yt-dlp or requests, store to local FS, enqueue processor tasks | Task Queue, Storage (files + state) |
| **Processor** | Transcode video to target format, extract audio, generate subtitles via Whisper ASR, burn subtitles via FFmpeg | Task Queue, Storage (files + state) |
| **Translator** | Translate title/description/subtitle text (LLM API or DeepL), produce Chinese-language assets | Task Queue, Storage (state) |
| **Publisher** | Publish to each target platform (API or Playwright browser automation), update publish state | Task Queue, Storage (state) |
| **Config Manager** | Load/watch YAML config: rules, credentials, schedules, platform settings | All components (read-only) |
| **Storage Layer** | SQLite for state tracking/metadata; local filesystem for binary assets | All components |

---

## Recommended Project Structure

```
crosspost/
├── config/
│   ├── settings.yaml          # credentials, schedules, rules
│   └── platforms/
│       ├── douyin.yaml
│       ├── toutiao.yaml
│       ├── xiaohongshu.yaml
│       └── baidu.yaml
│
├── crosspost/
│   ├── __init__.py
│   ├── main.py                # entrypoint: start scheduler + worker
│   ├── celery_app.py          # Celery application instance
│   ├── scheduler.py           # APScheduler or Celery Beat job definitions
│   ├── config.py              # Config loader (Pydantic Settings)
│   │
│   ├── sources/               # SOURCE LAYER
│   │   ├── base.py            # AbstractSource interface
│   │   ├── youtube.py         # YouTube Data API + yt-dlp discovery
│   │   └── twitter.py         # X scraper / API integration
│   │
│   ├── downloaders/           # DOWNLOAD LAYER
│   │   ├── base.py            # AbstractDownloader interface
│   │   ├── video.py           # yt-dlp wrapper
│   │   └── image.py           # requests-based image downloader
│   │
│   ├── processors/            # PROCESSING LAYER
│   │   ├── base.py            # AbstractProcessor interface
│   │   ├── transcoder.py      # FFmpeg transcode (format, resolution, bitrate)
│   │   ├── transcriber.py     # Whisper ASR → SRT subtitle file
│   │   └── subtitle_burner.py # FFmpeg subtitle burn-in
│   │
│   ├── translators/           # TRANSLATION LAYER
│   │   ├── base.py            # AbstractTranslator interface
│   │   ├── llm.py             # Claude/GPT API translation
│   │   └── deepl.py           # DeepL API translation (cost fallback)
│   │
│   ├── publishers/            # PUBLISHER LAYER
│   │   ├── base.py            # AbstractPublisher interface
│   │   ├── douyin.py          # Playwright browser automation
│   │   ├── toutiao.py         # REST API
│   │   ├── xiaohongshu.py     # Playwright browser automation
│   │   └── baidu.py           # REST API
│   │
│   ├── tasks/                 # CELERY TASK DEFINITIONS
│   │   ├── source_tasks.py    # check_source, discover_content
│   │   ├── download_tasks.py  # download_content
│   │   ├── process_tasks.py   # transcode, transcribe, burn_subtitles
│   │   ├── translate_tasks.py # translate_content
│   │   └── publish_tasks.py   # publish_to_platform
│   │
│   ├── storage/
│   │   ├── db.py              # SQLAlchemy or raw sqlite3 connection
│   │   ├── models.py          # Content, PublishRecord, FailureLog
│   │   └── file_store.py      # FS path management for assets
│   │
│   └── utils/
│       ├── retry.py           # Tenacity decorators
│       ├── browser.py         # Playwright context factory (stealth settings)
│       └── logging.py         # Structured logging setup
│
├── data/
│   ├── downloads/             # Downloaded video/audio/images
│   ├── processed/             # Transcoded video, SRT files
│   └── state.db               # SQLite database
│
├── tests/
├── requirements.txt
└── docker-compose.yml         # Redis + worker + scheduler containers
```

---

## Architectural Patterns

### Pattern 1: Linear Stage Pipeline with Queue Handoffs

Each stage of the pipeline is a discrete Celery task. On success, the task enqueues the next stage. No stage blocks waiting for another — all execution is async.

```python
# tasks/download_tasks.py
@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def download_content(self, content_id: str):
    try:
        content = db.get(content_id)
        downloader = VideoDownloader()
        file_path = downloader.download(content.source_url)
        db.update(content_id, status="downloaded", file_path=file_path)
        # Hand off to next stage
        process_content.delay(content_id)
    except DownloadError as exc:
        raise self.retry(exc=exc, countdown=exponential_backoff(self.request.retries))
```

**Why:** Decouples stages, enables independent retry, easy to add stages without rewiring.

### Pattern 2: Abstract Publisher Interface

Each platform is a plugin implementing a common interface. The publish task selects and calls the correct plugin.

```python
# publishers/base.py
class AbstractPublisher(ABC):
    @abstractmethod
    def publish(self, content: ContentItem) -> PublishResult:
        ...

# tasks/publish_tasks.py
@celery_app.task(bind=True, max_retries=5)
def publish_to_platform(self, content_id: str, platform: str):
    publisher = PublisherRegistry.get(platform)
    result = publisher.publish(content)
    db.record_publish(content_id, platform, result)
```

**Why:** Adding a new target platform requires only a new publisher class, zero changes to the pipeline.

### Pattern 3: Idempotency via Content Hash Deduplication

Before downloading, compute a canonical ID from the source URL (or content hash). Check the database. Skip if already processed.

```python
# sources/youtube.py
def discover_new_content(channel_id: str) -> list[ContentItem]:
    items = youtube_api.list_videos(channel_id)
    return [
        item for item in items
        if not db.content_exists(source_id=item.video_id, source="youtube")
    ]
```

**Why:** Prevents reprocessing on scheduler reruns. Safe to crash and restart anywhere.

### Pattern 4: Staged Status Machine in SQLite

Every content item has an explicit status column. Transitions are: `discovered` → `downloading` → `processing` → `translating` → `publishing_{platform}` → `done` / `failed`.

```sql
CREATE TABLE content (
    id           TEXT PRIMARY KEY,
    source       TEXT NOT NULL,       -- 'youtube' | 'twitter'
    source_id    TEXT NOT NULL,
    source_url   TEXT NOT NULL,
    status       TEXT NOT NULL DEFAULT 'discovered',
    file_path    TEXT,
    error_msg    TEXT,
    retry_count  INTEGER DEFAULT 0,
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source, source_id)
);

CREATE TABLE publish_records (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id   TEXT REFERENCES content(id),
    platform     TEXT NOT NULL,       -- 'douyin' | 'toutiao' | 'xiaohongshu' | 'baidu'
    status       TEXT NOT NULL,       -- 'pending' | 'published' | 'failed'
    platform_id  TEXT,               -- returned post ID from platform
    published_at DATETIME,
    error_msg    TEXT
);
```

**Why:** Crash-safe. On restart, find all items in intermediate states and re-enqueue. No processing lost.

### Pattern 5: Separated Playwright Browser Context per Publisher

Each Playwright publisher gets its own persistent browser context with stored session cookies. Contexts are not shared between publisher workers to avoid cross-contamination.

```python
# utils/browser.py
def get_browser_context(platform: str) -> BrowserContext:
    storage_path = f"data/sessions/{platform}_session.json"
    context = browser.new_context(
        storage_state=storage_path if os.path.exists(storage_path) else None,
        user_agent=random_ua(),
        viewport={"width": 1280, "height": 800},
    )
    return context
```

**Why:** Session persistence avoids repeated logins (reduces detection risk). Per-platform isolation prevents cookie leakage.

---

## Data Flow

```
1. SCHEDULER fires check_sources every N minutes
         │
         ▼
2. SOURCE LAYER queries YouTube API / X for new content
   → Dedup check against SQLite (source + source_id unique)
   → Insert new rows with status='discovered'
   → Enqueue download_content task for each new item
         │
         ▼
3. DOWNLOADER receives task (content_id)
   → Fetch row from SQLite
   → yt-dlp downloads to data/downloads/{content_id}/
   → Update status='downloaded', file_path
   → Enqueue process_content task
         │
         ▼
4. PROCESSOR receives task (content_id)
   → FFmpeg transcode to target codec/resolution
   → Whisper ASR → SRT subtitle file
   → FFmpeg burn subtitles into video copy
   → Update status='processed', processed_path
   → Enqueue translate_content task
         │
         ▼
5. TRANSLATOR receives task (content_id)
   → Read title, description, SRT from SQLite + FS
   → Call LLM/DeepL API for EN→ZH translation
   → Write Chinese SRT, translated title/description to SQLite
   → Update status='translated'
   → Enqueue publish_to_platform task for EACH enabled platform
         │
         ├──▶ publish_to_platform(content_id, 'douyin')
         ├──▶ publish_to_platform(content_id, 'toutiao')
         ├──▶ publish_to_platform(content_id, 'xiaohongshu')
         └──▶ publish_to_platform(content_id, 'baidu')
                   │
                   ▼
6. PUBLISHER receives task (content_id, platform)
   → Read content + translated assets from SQLite + FS
   → API call (Toutiao, Baidu) or Playwright session (Douyin, XHS)
   → Insert publish_record row with status + platform_id
   → If all platforms done: update content status='done'
```

Key properties of this flow:
- Steps 5→6 fan out: one content item spawns N publish tasks (one per platform), running concurrently.
- Any step can fail and retry independently without affecting other steps or items.
- The SQLite state machine means the system can be restarted at any point and resume correctly.

---

## Suggested Build Order (Phase Dependencies)

```
Phase 1: Foundation
  Storage layer (SQLite schema, file_store)
  Config loader (Pydantic Settings from YAML)
  Celery app + Redis setup
  Logging infrastructure
  ↓ required by: everything

Phase 2: Source + Download
  YouTube source (YouTube Data API + channel rule matching)
  yt-dlp downloader wrapper
  Deduplication logic
  ↓ required by: all processing stages

Phase 3: Processing
  FFmpeg transcoder (format normalization)
  Whisper transcriber (ASR → SRT)
  Subtitle burner (FFmpeg drawtext/subtitles filter)
  ↓ required by: translation, publishing

Phase 4: Translation
  LLM translator (title + description + subtitle SRT)
  Cost tracking / rate limiting
  ↓ required by: publishing

Phase 5: Publishing — API platforms first
  Toutiao publisher (has REST API)
  Baidu publisher (has REST API)
  ↓ validates end-to-end pipeline before tackling harder platforms

Phase 6: Publishing — Browser automation
  Douyin Playwright publisher
  Xiaohongshu Playwright publisher
  Session management + stealth config
  ↓ most complex, most fragile — build last

Phase 7: Sources — X/Twitter
  X scraper / API integration
  ↓ separate from YouTube; shares download + processing stages

Phase 8: Scheduler + Automation polish
  Cron scheduling (Celery Beat or APScheduler)
  Failure alerting, retry dashboards (Flower)
  Config rule engine (keyword/channel filters)
```

Build API-based publishers before browser automation publishers. The former validates the whole pipeline path with lower risk. Browser automation is the most fragile component and benefits from having a stable pipeline underneath it.

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Synchronous Sequential Execution

**What:** Run all stages in a single blocking function call (download → process → translate → publish in one script).

**Why bad:** A failure anywhere aborts all subsequent stages for that item. No retry granularity. No parallelism across items.

**Instead:** Each stage is a Celery task. On success, enqueue next task. On failure, Celery retries only the failed stage.

---

### Anti-Pattern 2: Storing Binary Assets in the Database

**What:** Store video bytes or image bytes as BLOBs in SQLite.

**Why bad:** SQLite is not optimized for large binary blobs. Backup, query performance, and memory use all degrade severely.

**Instead:** Store files on local FS under `data/downloads/` and `data/processed/`. Store only the file path in SQLite.

---

### Anti-Pattern 3: Shared Playwright Browser Instance Across Publishers

**What:** One global browser instance shared by all publisher workers.

**Why bad:** Session cookies bleed between platforms. Concurrent tasks interfere. A browser crash takes down all publishers simultaneously.

**Instead:** Each publisher maintains its own named persistent browser context. Workers acquire a per-platform lock if needed.

---

### Anti-Pattern 4: Re-downloading Already-Processed Content on Restart

**What:** No deduplication state — every scheduler run re-discovers and re-processes all content.

**Why bad:** Wastes bandwidth, API quota, compute time, and storage. Can cause duplicate posts on target platforms.

**Instead:** `UNIQUE(source, source_id)` constraint in SQLite. Check before enqueuing. Status machine prevents re-entering any completed stage.

---

### Anti-Pattern 5: Monolithic Publisher Class

**What:** A single `Publisher` class with if/elif branches for each platform.

**Why bad:** Adding a new platform requires editing a shared class. Testing one platform risks breaking others. No isolation.

**Instead:** `AbstractPublisher` base class. One file per platform. Registry pattern maps platform name → publisher class. Zero modification of existing code to add a platform.

---

### Anti-Pattern 6: Calling Translation API on Every Retry

**What:** Translate content in the same task that publishes it, so a publish failure retriggers translation.

**Why bad:** Translation API calls are expensive. Retrying a publish failure should not re-translate.

**Instead:** Translation is its own stage with its own task. Output (translated text) is persisted to SQLite before publish tasks are enqueued. Publish retries read from DB, not re-translate.

---

## Scalability Considerations

| Concern | Single-server personal use | If scale needed later |
|---------|----------------------------|-----------------------|
| Download bandwidth | Single yt-dlp worker sufficient | Add concurrent download workers |
| Whisper ASR speed | CPU-only: ~1x realtime (faster-whisper with quantization: 4-8x) | GPU instance or OpenAI Whisper API |
| Translation cost | Cache translated text in DB; skip re-translation | Batch API calls; use DeepL for lower cost |
| Browser automation stability | Use persistent sessions; human-like delays | Rotate accounts; add proxy pool |
| Storage growth | Purge `data/downloads/` after publish; keep only `processed/` | Object storage (S3/OSS) if long-term archiving needed |

---

## Sources

- Celery 5.5.3 documentation and production patterns: [Celery + Redis Production Guide](https://medium.com/@dewasheesh.rana/celery-redis-fastapi-the-ultimate-2025-production-guide-broker-vs-backend-explained-5b84ef508fa7)
- APScheduler vs Celery Beat scheduling comparison: [Scheduling Tasks in Python](https://leapcell.io/blog/scheduling-tasks-in-python-apscheduler-vs-celery-beat)
- yt-dlp post-processing pipeline: [yt-dlp DeepWiki](https://deepwiki.com/yt-dlp/yt-dlp/2.5-configuration-system)
- Whisper + FFmpeg subtitle pipeline: [DigitalOcean Whisper + FFmpeg Guide](https://www.digitalocean.com/community/tutorials/how-to-generate-and-add-subtitles-to-videos-using-python-openai-whisper-and-ffmpeg)
- Retry with exponential backoff (Tenacity): [Building Resilient Python Applications with Tenacity](https://www.amitavroy.com/articles/building-resilient-python-applications-with-tenacity-smart-retries-for-a-fail-proof-architecture)
- Idempotent pipeline design: [The Importance of Idempotent Data Pipelines](https://www.prefect.io/blog/the-importance-of-idempotent-data-pipelines-for-resilience)
- Playwright stealth / anti-detection: [Avoid Bot Detection With Playwright Stealth](https://www.scrapeless.com/en/blog/avoid-bot-detection-with-playwright-stealth)
- Publishing pipeline modular design: [Publishing Pipeline Refactoring](https://dev.to/12ww1160/publishing-pipeline-refactoring-3c9n)
