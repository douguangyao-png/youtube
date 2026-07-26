# Technology Stack

**Project:** CrossPost (跨平台内容搬运工具)
**Researched:** 2026-03-14
**Confidence:** MEDIUM-HIGH (core libraries HIGH, Chinese platform publishing APIs LOW due to opaque documentation)

---

## Recommended Stack

### Core Technologies

| Layer | Technology | Version | Purpose | Why |
|-------|------------|---------|---------|-----|
| Runtime | Python | 3.12.x | Application runtime | Required by user. 3.12 is current stable with best performance; yt-dlp now requires >=3.10 (3.9 EOL Oct 2025) |
| Video Download | yt-dlp | 2026.03.x (auto-update) | Download YouTube/Shorts/X video | De facto standard, actively maintained (latest: 2026-03-13), 2000+ supported sites |
| Browser Automation | Playwright (Python) | 1.49+ | Publish to Xiaohongshu + Douyin (personal) | Faster, auto-waits, bundles browsers, no driver mismatches vs Selenium; dominant in 2025 surveys |
| Video Transcoding | FFmpeg (via subprocess) | 7.x system install | Format conversion, subtitle burn-in | Direct subprocess calls are simpler and more reliable than Python wrappers for complex pipelines |
| ASR / Subtitles | faster-whisper | 1.1.x | English speech-to-text for subtitle generation | 4x faster than openai/whisper, CTranslate2 backend, works on CPU (no GPU required on cloud VMs) |
| Translation | DeepL API | deepl>=1.20 | English-to-Chinese text + subtitle translation | Best cost/quality for EN→ZH vs GPT-4 for bulk translation; $25/1M chars vs LLM token costs |
| Task Scheduling | APScheduler | 3.10.x | Cron-style periodic scraping and publishing | No external broker needed (unlike Celery), sufficient for single-process personal tool |
| Data Storage | SQLite (via SQLModel) | SQLModel 0.0.21+ | Job state, content queue, deduplication | Single-user, no concurrent writers, zero-ops; SQLModel unifies Pydantic + SQLAlchemy |
| Config | Pydantic Settings | 2.x | Configuration management from env/files | Type-safe config, supports .env files, integrates naturally with Pydantic models used elsewhere |
| Logging | Loguru | 0.7.x | Structured application logging | Dead-simple API, file rotation built-in, no boilerplate vs stdlib logging |

---

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| httpx | 0.27+ | Async HTTP client for API calls | Toutiao API, Baidu Baijiahao API, translation API calls |
| tenacity | 8.x | Retry logic with backoff | Wrap all external API calls and browser automation steps |
| social-auto-upload (reference) | GitHub HEAD | Community-maintained Playwright scripts for Douyin/Xiaohongshu/Bilibili | Use as reference implementation; do not take as a direct dependency — copy and adapt patterns |
| ffmpeg-python | 0.2.0 | FFmpeg Python binding | Use ONLY for simple probe/metadata operations; use subprocess for actual transcoding pipelines |
| srt | 3.5.x | SRT subtitle file parsing and writing | Parse Whisper output segments into SRT format for burning/uploading |
| Pillow | 10.x | Image manipulation | Thumbnail creation, cover image resizing for platform requirements |
| schedule | 1.2.x | Lightweight in-process cron fallback | Only if APScheduler proves too heavy; simpler but less feature-rich |
| python-dotenv | 1.x | Load .env files for secrets | Development-time secret management |
| rich | 13.x | Terminal output formatting | CLI progress display when running manually |

---

### Development Tools

| Tool | Version | Purpose |
|------|---------|---------|
| uv | 0.5+ | Package management and virtual envs — replaces pip+venv, dramatically faster |
| ruff | 0.9+ | Linting and formatting — replaces flake8+black+isort in one tool |
| pytest | 8.x | Testing framework |
| pytest-asyncio | 0.24+ | Async test support |
| mypy | 1.x | Static type checking |

---

## Architecture Decision: Platform Publishing

| Platform | Method | Confidence | Notes |
|----------|--------|------------|-------|
| Douyin (抖音) | Playwright browser automation | MEDIUM | Open Platform API requires enterprise verification; personal accounts use browser automation. social-auto-upload project demonstrates working Playwright approach |
| Toutiao (今日头条) | HTTP API (头条号 API) | LOW | Official API exists but documentation is in Chinese and behind registration; may need browser automation fallback if API access is denied |
| Xiaohongshu (小红书) | Playwright browser automation | HIGH (method), LOW (stability) | No public API exists; browser automation is the only option; expect breakage as anti-bot measures update |
| Baidu Baijiahao (百家号) | HTTP API | LOW | API reportedly exists; no English documentation found; requires account registration and verification |

**Decision: Build a unified publisher interface with two backends — `APIPublisher` and `BrowserPublisher` — switchable per platform via config. This isolates brittleness.**

---

## Architecture Decision: Translation

Use **DeepL API** (not an LLM) as the primary translation engine because:
- DeepL EN→ZH quality is competitive with GPT-4 at ~1/20th the cost per character
- Deterministic output (no temperature variation) — critical for subtitle timing consistency
- Rate limits are predictable and documented

Use **LLM (Claude/GPT-4o) as fallback only** for:
- Short metadata (titles, descriptions) where context and tone matter more than cost
- Cases where DeepL output requires cultural adaptation

---

## Architecture Decision: Scheduling

Use **APScheduler 3.x** (not Celery) because:
- This is a single-process personal tool; Celery's message broker (Redis/RabbitMQ) is unnecessary overhead
- APScheduler runs in-process, persists jobs to SQLite, survives restarts
- Cron expressions supported natively

---

## Architecture Decision: ASR

Use **faster-whisper** (not openai/whisper or WhisperX) because:
- 4x faster on CPU — important since cloud VMs typically lack GPU
- Lower memory footprint via INT8 quantization
- WhisperX adds diarization/alignment which is unnecessary for single-speaker YouTube content
- openai/whisper requires more RAM and is slower

Model size recommendation: `large-v3` for production (best accuracy), `medium` for development/testing.

---

## Installation

```bash
# Package manager (recommended over pip)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create project
uv init crosspost && cd crosspost
uv python pin 3.12

# Core dependencies
uv add yt-dlp httpx tenacity pydantic-settings sqlmodel apscheduler loguru

# Playwright (installs browser binaries separately)
uv add playwright
uv run playwright install chromium

# ASR
uv add faster-whisper

# Translation
uv add deepl

# Video/image utilities
uv add srt pillow

# Dev dependencies
uv add --dev ruff pytest pytest-asyncio mypy rich

# System dependency (install via OS package manager)
# Ubuntu/Debian: sudo apt install ffmpeg
# Verify: ffmpeg -version
```

---

## Alternatives Considered

| Category | Recommended | Alternative | Why NOT |
|----------|-------------|-------------|---------|
| Browser automation | Playwright | Selenium | Selenium requires manual driver version matching, slower, older architecture; Playwright dominates 2025 adoption surveys |
| Browser automation | Playwright | DrissionPage | DrissionPage is China-popular but smaller ecosystem, less documentation in English, less stable long-term |
| ASR | faster-whisper | openai/whisper | 4x slower, higher memory use; identical accuracy |
| ASR | faster-whisper | WhisperX | Adds unnecessary complexity (diarization, word-level alignment) for this use case |
| Translation | DeepL | Google Translate API | DeepL quality is demonstrably better for EN→ZH; Google Translate API costs are similar |
| Translation | DeepL + LLM | LLM only (GPT-4/Claude) | LLM translation costs 20x more for bulk subtitle content with no quality advantage over DeepL |
| Scheduling | APScheduler | Celery + Redis | Celery requires Redis broker, worker processes, separate beat process — massive complexity for a personal tool |
| Scheduling | APScheduler | Python `schedule` | APScheduler has persistent job storage (SQLite), missed-job handling, and better cron expression support |
| Database | SQLite (SQLModel) | PostgreSQL | Completely unnecessary for single-user, single-server personal tool; operational overhead with zero benefit |
| ORM | SQLModel | SQLAlchemy directly | SQLModel combines Pydantic validation with SQLAlchemy ORM, eliminating duplicate model definitions |
| Logging | Loguru | stdlib logging | stdlib logging requires verbose configuration; Loguru is simpler with built-in rotation and formatting |
| Package manager | uv | pip + venv | uv is 10-100x faster, handles lockfiles natively, now standard in 2025 Python projects |
| FFmpeg binding | subprocess (direct) | ffmpeg-python library | ffmpeg-python adds an abstraction layer that makes debugging harder; direct subprocess gives full control over complex filter chains needed for subtitle burn-in |

---

## What NOT to Use

| Technology | Reason |
|------------|--------|
| **Selenium** | Superseded by Playwright for new projects. Driver management is a maintenance burden. Slower. |
| **snscrape** | Breaks every few weeks as X changes its HTML/API. X scraping is inherently fragile; yt-dlp already handles X video downloads. For tweets, accept that X data may require Playwright-based scraping directly. |
| **Tweepy** | X API free tier is severely restricted (read-limited). Paid tiers are expensive. Not viable for this use case. |
| **MoviePy** | v2.0 introduced breaking changes; v1 unmaintained. Direct FFmpeg subprocess is more reliable for transcoding + subtitle burn-in. |
| **Celery** | Overkill for single-process personal tool. Requires broker infrastructure (Redis/RabbitMQ). |
| **FastAPI / Django** | No web interface in scope for v1. Adds unnecessary dependency. |
| **PyTorch (full)** | faster-whisper uses CTranslate2, not PyTorch. Avoid pulling in full PyTorch unless GPU inference is added later. |
| **OpenAI Whisper (openai/whisper package)** | 4x slower than faster-whisper with same accuracy; use faster-whisper instead. |

---

## Platform-Specific Notes

### X (Twitter) Content Scraping
X has aggressively restricted API access since 2023. The free API tier allows only 1,500 tweets/month read access. Practical options:
1. **yt-dlp** already handles X video downloads natively — use it for video content
2. **Playwright scraping** of the public web interface for tweet text/images — fragile but viable
3. Accept that X scraping reliability is LOW; build with retry and graceful-skip logic

### Douyin / TikTok
The official Douyin Open Platform API requires enterprise business license (营业执照) verification. For personal use, Playwright automation against the creator web interface is the only viable path. The `social-auto-upload` open-source project (GitHub: dreammis/social-auto-upload) demonstrates working patterns using Playwright + cookie persistence.

### Xiaohongshu (小红书)
No official publishing API exists. Playwright automation is the only option. Expect 2-4 week breakage cycles as Xiaohongshu updates anti-bot detection. Plan for:
- Cookie-based session management (login once, reuse cookies)
- Randomized delays between actions
- Detection handling with graceful pause/retry

### Baidu Baijiahao (百家号)
An official content API reportedly exists behind account registration. Treat as LOW confidence until verified via the official developer portal (baijiahao.baidu.com/builder/theme/developer). Build with browser automation fallback.

---

## Sources

- yt-dlp releases: https://github.com/yt-dlp/yt-dlp/releases (version 2026.03.13 confirmed current)
- Playwright vs Selenium 2025: https://www.browserless.io/blog/playwright-vs-selenium-2025-browser-automation-comparison
- faster-whisper performance: https://github.com/SYSTRAN/faster-whisper (4x faster, CTranslate2)
- Whisper variants comparison: https://modal.com/blog/choosing-whisper-variants
- DeepL vs GPT translation: https://intlpull.com/blog/best-translation-api-2026
- APScheduler vs Celery: https://leapcell.io/blog/scheduling-tasks-in-python-apscheduler-vs-celery-beat
- SQLite appropriate uses: https://sqlite.org/whentouse.html
- social-auto-upload (Douyin/Xiaohongshu Playwright patterns): https://github.com/dreammis/social-auto-upload
- Loguru production usage: https://www.dash0.com/guides/python-logging-with-loguru
- SQLModel overview: https://sqlmodel.tiangolo.com/features/
