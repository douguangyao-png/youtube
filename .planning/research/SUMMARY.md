# Project Research Summary

**Project:** CrossPost (跨平台内容搬运工具)
**Domain:** Automated cross-platform content syndication — YouTube/X acquisition + Chinese platform publishing
**Researched:** 2026-03-14
**Confidence:** MEDIUM (core pipeline HIGH, Chinese platform APIs LOW-MEDIUM)

## Executive Summary

CrossPost is a single-operator automation pipeline that downloads English-language video content from YouTube and X, processes it (transcode, ASR, translate, subtitle burn-in), and publishes to four major Chinese platforms: Douyin, Toutiao, Xiaohongshu, and Baidu Baijiahao. Experts build this class of tool as a linear staged pipeline with async handoffs between stages, a SQLite-backed job state machine for crash recovery, and a plugin-per-platform publisher architecture. The pipeline is: discover → download → transcode → transcribe → translate → publish, with each stage independently retryable. The recommended stack is Python 3.12, yt-dlp for acquisition, faster-whisper for ASR, DeepL for bulk subtitle translation, FFmpeg via subprocess for transcoding and subtitle burn-in, Playwright for browser-automated platform publishing, APScheduler for scheduling, and SQLModel/SQLite for state persistence.

The central architectural recommendation is to isolate the most fragile components — browser automation for Douyin and Xiaohongshu — behind a common AbstractPublisher interface and build them last, after validating the full pipeline with the API-accessible platforms (Toutiao, Baidu). Every stage must write its output to the state machine before handing off, so retries never repeat expensive operations (translation in particular). Anti-detection for Chinese platforms is a first-class design requirement, not an afterthought: behavioral fingerprinting at Douyin and Xiaohongshu detected and banned 2.6 million accounts in Q1 2025.

The most significant risks are operational and legal, not technical. YouTube's evolving PO Token / SABR anti-bot system will break the downloader on a server IP without proper cookie management and weekly yt-dlp updates. X scraping is a maintenance sinkhole at $0/month options; treat it as a degradable optional feature with a circuit breaker. Most critically, republishing third-party content without explicit permission is copyright infringement — the tool must enforce a per-channel whitelist with license verification from day one. China's AI content labeling law (effective Sept 1, 2025) additionally requires all AI-translated content to carry embedded disclosure labels on Chinese platforms.

---

## Key Findings

### Recommended Stack

The stack is well-determined with high confidence for core components. Python 3.12 is required (yt-dlp needs >= 3.10; 3.9 is EOL). The `uv` package manager replaces pip+venv and is now standard. For scheduling, APScheduler 3.x is recommended over Celery — this is a single-process personal tool and Celery's Redis broker infrastructure is unnecessary overhead. SQLite via SQLModel provides zero-ops state persistence appropriate for a single-user, single-server deployment.

The most consequential stack decision is the dual-backend publisher pattern: API-based publishing (Toutiao, Baidu) and browser-automation-based publishing (Douyin, Xiaohongshu) behind a common AbstractPublisher interface. Playwright is preferred over Selenium for browser automation due to built-in auto-waits, browser bundling, and dominant adoption in 2025. For translation, DeepL API is recommended for bulk subtitle content (20x cheaper than LLM at comparable quality); LLM (Claude/GPT-4o) is reserved for short metadata (titles, descriptions) where cultural tone matters.

**Core technologies:**
- Python 3.12 + uv: runtime and package management — current stable, required by yt-dlp
- yt-dlp 2026.03.x: video acquisition — de facto standard, 2000+ sites, actively maintained
- faster-whisper 1.1.x: ASR transcription — 4x faster than openai/whisper on CPU, INT8 quantization
- DeepL API: bulk subtitle translation — 20x cheaper than LLM, deterministic output for timing consistency
- FFmpeg 7.x (subprocess): transcoding and subtitle burn-in — direct subprocess preferred over wrappers for complex filter chains
- Playwright 1.49+: browser-based platform publishing — auto-waits, stealth support, bundles Chromium
- APScheduler 3.10.x: cron scheduling — in-process, SQLite-backed job persistence, no external broker
- SQLModel 0.21+: state persistence — unifies Pydantic validation with SQLAlchemy ORM
- Loguru 0.7.x: logging — built-in rotation, zero boilerplate
- tenacity 8.x: retry logic — exponential backoff with jitter across all external calls

### Expected Features

All research files converge on a clear MVP: a single YouTube-to-Douyin end-to-end path, with additional platforms and X acquisition added sequentially after the core pipeline is stable.

**Must have (table stakes):**
- YouTube channel polling via RSS — no API key required, lowest friction acquisition path
- yt-dlp video download with metadata extraction — core pipeline entry point
- faster-whisper ASR transcription to SRT — required before subtitle workflow
- Subtitle translation EN→ZH with timing preservation — Chinese viewers cannot read English subtitles
- FFmpeg subtitle burn-in — Chinese platforms expect hardcoded subs; soft tracks unreliable
- FFmpeg transcoding to H.264 MP4 per platform spec — VP9/AV1 not accepted by Chinese upload systems
- Publish to Douyin via Playwright — core value delivery, 550M+ MAU
- SQLite job state machine with deduplication — crash recovery, idempotency from day one
- APScheduler periodic polling — unattended cloud server operation
- YAML config with channel allowlist and credential management — enforces copyright gate

**Should have (differentiators):**
- Toutiao publishing (REST API) — ByteDance ecosystem, lower automation risk than Douyin
- Xiaohongshu publishing (Playwright) — 300M+ MAU, high value despite fragility
- Baidu Baijiahao publishing (REST API) — completes the four-platform target
- Retry with exponential backoff and circuit breaker — operational resilience
- Publish queue scheduling with Gaussian jitter — ban prevention
- Webhook/Telegram notifications for failures — unattended operation visibility
- Per-platform content adaptation (title format, metadata variation) — ban prevention, platform norms
- Credential TTL tracking with health checks — prevent silent auth rot

**Defer (v2+):**
- X (Twitter) acquisition — high legal risk, extreme maintenance burden ($5K/month API or weekly breakage)
- Rule-based content filtering beyond channel subscription
- Aspect ratio auto-conversion (smart crop) — center crop sufficient initially
- Thumbnail generation with Chinese text overlay
- Proxy rotation for acquisition
- Web management UI — single operator, config file is sufficient
- Multi-user / SaaS mode

### Architecture Approach

The architecture is a linear staged pipeline where each stage is an independent unit that reads from and writes to a central SQLite state machine, then enqueues the next stage on success. No stage calls another directly — all handoffs are via the scheduler or task queue. This decouples stages, enables independent retry at any granularity, and ensures the pipeline is crash-safe by design. The storage layer is split between SQLite (state and metadata) and the local filesystem (binary assets), with SQLite storing only file paths, never binary blobs. Publishers are implemented as plugins behind a common AbstractPublisher interface with a registry pattern, so adding a new platform requires zero changes to existing pipeline code.

**Major components:**
1. Scheduler — fires periodic source-check jobs via APScheduler cron; enqueues discovery tasks
2. Source Layer — polls YouTube RSS/API, checks dedup, inserts new content rows with status `discovered`
3. Downloader — wraps yt-dlp; downloads to local FS; updates status to `downloaded`
4. Processor — FFmpeg transcoding, faster-whisper ASR, FFmpeg subtitle burn-in; updates status to `processed`
5. Translator — DeepL/LLM translation of title, description, SRT; persists Chinese assets; updates status to `translated`
6. Publisher Layer — per-platform plugins (AbstractPublisher); fans out to N parallel publish tasks after translation; writes publish_records rows
7. Storage Layer — SQLite (content table + publish_records table) + local FS (downloads/, processed/, sessions/)
8. Config Manager — Pydantic Settings loading YAML config; per-platform credential and rule config

### Critical Pitfalls

1. **YouTube bot detection breaks the downloader in production** — Server datacenter IPs are flagged by YouTube's PO Token + SABR system within hours. Mitigation: use Firefox cookies passed to yt-dlp, implement PO Token support, update yt-dlp weekly via cron, monitor download success rate with alerts below 85%.

2. **Chinese platform automation triggers account bans** — Douyin banned 2.6M accounts in Q1 2025 for automated behavior; XHS cross-checks content against other platforms. Mitigation: Gaussian jitter on all delays, stagger cross-platform publishing by 2-6 hours, re-encode video uniquely per platform, use playwright-stealth to mask headless fingerprints.

3. **Republishing copyrighted content is legally exposed** — Statutory damages up to $150,000/work in the US; Chinese platforms cooperate with copyright holders. Mitigation: enforce per-channel allowlist from day one; check YouTube license field via Data API; filter videos with existing copyright claims.

4. **Pipeline error cascading causes silent failures** — Partial downloads, empty SRT files, and timed-out uploads pass through without detection. Mitigation: validate every artifact between stages with ffprobe checks, SRT line count checks, and explicit success parsing of upload responses; use dead letter queue after 3 failures.

5. **Credential rot silently kills all platform publishing** — Browser sessions expire in days; API tokens rotate; yt-dlp cookies expire. Mitigation: store credentials with explicit TTL metadata; credential health check before each job batch; alert within 24h of expiry.

---

## Implications for Roadmap

Based on the dependency chain in FEATURES.md and the build order in ARCHITECTURE.md, the following phase structure is recommended. The ordering is driven by two rules: (1) infrastructure must precede all features, and (2) stable low-risk pipeline components must be validated end-to-end before building high-risk browser automation.

### Phase 1: Foundation Infrastructure
**Rationale:** Every subsequent component depends on the state machine, config system, logging, and credential management. Building these first prevents the most expensive technical debt patterns identified in PITFALLS.md. The job state machine is explicitly called out as requiring design before any feature implementation.
**Delivers:** SQLite schema with content and publish_records tables; Pydantic Settings YAML config loader; Loguru logging with rotation; credential TTL storage and health check; per-destination proxy profile design; file store path management.
**Addresses:** job state persistence (P0 table stakes), config file system (P0), credential rot (Pitfall 8), proxy routing (Pitfall 10).
**Avoids:** error cascading from no state machine (Pitfall 7), secrets in git (security mistake).

### Phase 2: Acquisition — YouTube
**Rationale:** YouTube is the primary and lowest-risk acquisition path. X is explicitly deferred. This phase validates the download-to-storage path that all processing stages depend on.
**Delivers:** YouTube RSS channel poller; yt-dlp downloader wrapper with Firefox cookie support and PO Token; deduplication logic; APScheduler periodic polling; download success rate monitoring.
**Addresses:** YouTube download (P0), deduplication (P0), scheduled polling (P0).
**Avoids:** bot detection breaking the downloader (Pitfall 1) — cookie and PO Token support must be in from day one, not retrofitted.

### Phase 3: Video Processing Pipeline
**Rationale:** Transcoding, ASR, and subtitle burn-in are tightly coupled (transcode first, burn after translation) and must all be stable before any publishing can be tested. Format validation must be built into this phase to prevent silent upload failures.
**Delivers:** FFmpeg transcoder with per-platform canonical output profiles and ffprobe validation; faster-whisper ASR with language=en, Simplified Chinese output via OpenCC, and subtitle coverage validation; FFmpeg subtitle burn-in with bundled CJK font; artifact validation between every stage.
**Addresses:** video transcoding (P0), ASR transcription (P0), subtitle burn-in (P0), Douyin/XHS format compliance.
**Avoids:** format mismatches causing silent upload failures (Pitfall 6), ASR hallucination passing through unchecked (Pitfall 5).
**Uses:** faster-whisper (large-v3 for production, medium for dev), FFmpeg subprocess, srt library, OpenCC for Traditional→Simplified conversion.

### Phase 4: Translation
**Rationale:** Translation is its own pipeline stage — explicitly separated from publishing so that publish retries do not re-call expensive translation APIs. Cost tracking is required from the start to prevent budget runaway on long videos.
**Delivers:** DeepL-based subtitle translation with sentence-aware chunking and timing preservation; LLM-based title/description translation with per-platform prompt profiles (Douyin <30 chars, XHS hashtag format); per-video cost estimation and cap; Chinese asset persistence to SQLite before publish tasks are enqueued.
**Addresses:** subtitle translation (P0), title/description localization, China AI labeling law compliance (AI disclosure injection).
**Avoids:** re-translation on publish retry (Anti-Pattern 6), translation cost runaway (technical debt pattern).

### Phase 5: Publishing — API-Based Platforms
**Rationale:** Toutiao and Baidu Baijiahao have documented REST APIs, making them substantially lower risk than browser automation. Building these first validates the entire end-to-end pipeline (source → process → translate → publish) before tackling the fragile Playwright-based publishers. If the API integrations prove more complex than expected (LOW confidence per STACK.md), the pipeline is still proven.
**Delivers:** AbstractPublisher base class and registry; Toutiao publisher (REST API); Baidu Baijiahao publisher (REST API); publish_records tracking with platform_id; retry with exponential backoff and circuit breaker; publish queue scheduling with configurable per-platform delay.
**Addresses:** Toutiao publishing (P1), Baidu publishing (P1), retry with backoff (P1), publish queue scheduling (P1).
**Avoids:** retrying failed API calls without circuit breaker (security mistake), Toutiao/Baijiahao cross-posting conflicts (Pitfall 12).
**Note:** Toutiao and Baidu API access requires registration and may be denied — have browser automation fallback design ready.

### Phase 6: Publishing — Browser-Automated Platforms
**Rationale:** Douyin and Xiaohongshu are the highest-value but most fragile target platforms. Building them last ensures the entire upstream pipeline is stable and validated, reducing the surface of debugging when browser automation issues arise. Anti-detection requirements (stealth, jitter, per-platform re-encoding) are first-class in this phase.
**Delivers:** Douyin Playwright publisher with playwright-stealth, Gaussian jitter delays, and per-platform re-encode; Xiaohongshu Playwright publisher with hardcoded selectors extracted to config file, selector health checks; per-platform persistent browser context with session storage; human-like delay patterns; cross-platform publish staggering (2-6 hours); notification/webhook on failure.
**Addresses:** Douyin publishing (P0 core value), Xiaohongshu publishing (P1), cross-platform duplicate detection (Pitfall 9).
**Avoids:** account bans from automated behavior (Pitfall 2), shared browser context across publishers (Anti-Pattern 3), hardcoded Playwright selectors (technical debt).

### Phase 7: Operational Hardening
**Rationale:** The tool must run unattended on a cloud server. This phase adds the observability, resilience, and maintenance automation that make unattended operation viable long-term.
**Delivers:** Telegram/webhook failure notifications; per-source download success rate monitoring; yt-dlp weekly auto-update cron; cookie refresh scheduling; download storage TTL cleanup; log rotation enforcement; dead letter queue for jobs exceeding retry limit; credential expiry alerts.
**Addresses:** webhook notifications (P2), proxy rotation (P2), operational monitoring.
**Avoids:** silent failure accumulation, disk fill from unbounded logs and downloads, credential rot.

### Phase 8: X (Twitter) Acquisition (Optional)
**Rationale:** X acquisition is deferred until the entire pipeline is proven. It is architecturally a pluggable Source Layer adapter and requires no changes to processing or publishing. Its fragility is isolated by the circuit breaker pattern — when it fails, it degrades gracefully rather than consuming engineering time.
**Delivers:** X source adapter with circuit breaker and degradable failure mode; third-party X API integration (TwitterAPI.io or equivalent paid service); health monitoring with per-source success rates.
**Addresses:** X post/video acquisition (P2).
**Avoids:** X scraping becoming a maintenance sinkhole (Pitfall 4) — circuit breaker and graceful degradation are mandatory, not optional.

---

### Phase Ordering Rationale

- Foundation first: the SQLite state machine, config loader, and credential management are depended on by every other phase; retrofitting them is described as "painful" in FEATURES.md and "much harder" in PITFALLS.md.
- YouTube before X: YouTube is lower legal and technical risk; X scraping is explicitly scoped as a separate, degradable optional feature.
- Processing before publishing: the transcoder, ASR, and subtitle burn-in must produce validated artifacts before any publisher can use them; format mismatches cause silent failures.
- Translation before publishing: translation output is persisted before publish tasks are enqueued; this architectural requirement means the two phases must be separate.
- API publishers before browser automation publishers: validates the full end-to-end pipeline path with lower risk; stable pipeline reduces browser automation debugging surface.
- Operational hardening after core functionality: unattended operation is the goal, but hardening requires knowing what actually breaks in practice.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 5 (Toutiao/Baidu APIs):** API documentation is in Chinese, behind registration, and confidence is LOW per STACK.md. Actual API capabilities, rate limits, and content requirements need hands-on verification. May require browser automation fallback design.
- **Phase 6 (Browser automation — Douyin/XHS):** Anti-detection measures evolve every 2-4 weeks. Current social-auto-upload patterns provide reference implementation but may be stale. Selector configurations for XHS need live testing. Requires deeper research on current stealth plugin compatibility.
- **Phase 8 (X acquisition):** X API pricing tiers and current third-party API reliability need validation before committing to an approach. Budget implications are significant ($0.15/1,000 tweets for paid APIs).

Phases with standard patterns (skip research-phase):
- **Phase 1 (Foundation):** SQLite schema, Pydantic Settings, Loguru, APScheduler — well-documented with established patterns.
- **Phase 3 (Video processing):** FFmpeg, faster-whisper, SRT handling — well-documented libraries with extensive community resources and working code examples.
- **Phase 4 (Translation):** DeepL Python SDK and LLM API integration — standard API client patterns with good documentation.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH (core), LOW (CN platform APIs) | Python/yt-dlp/FFmpeg/Playwright/faster-whisper choices are well-validated. Toutiao and Baidu API access is LOW — documentation is in Chinese, behind registration, requirements unverified. |
| Features | HIGH (YouTube path), MEDIUM (CN platforms) | MVP feature set is clear and consistent across all research files. Chinese platform API capabilities need hands-on verification. X acquisition deliberately deferred. |
| Architecture | HIGH | Pipeline pattern is well-established for this problem class. SQLite state machine, abstract publisher, and separated translation stage patterns are industry-standard. |
| Pitfalls | MEDIUM-HIGH | YouTube bot detection and Chinese platform ban patterns are verified via GitHub issues and primary Chinese sources. Legal exposure is well-documented. API-specific behavior (Toutiao/Baidu) less verified. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Toutiao API access:** Verify whether 头条号 API is actually accessible without enterprise verification. Build design must have browser automation fallback ready before committing to the API path in Phase 5.
- **Baidu Baijiahao API:** Same gap as Toutiao — reportedly exists but unverified. Plan for potential browser automation path.
- **Douyin Open Platform API:** Requires business license (营业执照) verification. If the operator can obtain this, it is substantially more stable than Playwright automation. Clarify early whether this is in scope.
- **PO Token implementation complexity:** yt-dlp wiki documents the PO Token system but implementation complexity is unclear. Spike this in Phase 2 before designing the downloader fully.
- **OpenCC Simplified/Traditional conversion:** Whisper's default Chinese output is Traditional; all mainland platforms require Simplified. Verify OpenCC integration adds acceptable overhead and handles all edge cases in the target content vocabulary.
- **Per-video re-encoding for anti-detection:** The recommendation to re-encode video uniquely per platform (to change perceptual hash) adds processing time and storage. Quantify this overhead during Phase 6 planning.

---

## Sources

### Primary (HIGH confidence)
- yt-dlp GitHub (releases + issues #13067, #15865): YouTube bot detection and PO Token system
- faster-whisper GitHub (SYSTRAN): 4x speedup benchmarks, CTranslate2 backend
- social-auto-upload (dreammis): Working Playwright patterns for Douyin/XHS/Bilibili
- China AI labeling law — Harris Sliwoski legal blog: Sept 2025 enforcement date confirmed
- 抖音Q1 2025 enforcement report (新浪科技): 2.6M accounts banned, 3-second detection time

### Secondary (MEDIUM confidence)
- Playwright vs Selenium 2025 (Browserless): adoption survey data, feature comparison
- DeepL vs GPT translation quality (intlpull.com 2026): EN→ZH quality and cost comparison
- APScheduler vs Celery (Leapcell): scheduling architecture comparison for single-process tools
- Modal blog: Whisper variant comparison (faster-whisper, WhisperX, openai/whisper)
- 小红书 2026 originality detection (微盛企微管家): cross-platform content detection details

### Tertiary (LOW confidence)
- Toutiao 头条号 API existence — referenced in multiple sources but documentation unverified
- Baidu Baijiahao API — reportedly exists behind registration; no verified documentation found
- TwitterAPI.io pricing ($0.15/1,000 tweets) — from third-party source, needs confirmation

---
*Research completed: 2026-03-14*
*Ready for roadmap: yes*
