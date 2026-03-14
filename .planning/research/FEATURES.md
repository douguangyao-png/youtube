# Feature Landscape: CrossPost — Cross-Platform Content Syndication Tool

**Domain:** Automated content acquisition, processing, and multi-platform publishing
**Researched:** 2026-03-14
**Overall confidence:** HIGH (stack-specific claims), MEDIUM (Chinese platform API claims)

---

## Table Stakes

Features without which the tool does not accomplish its stated purpose. Missing any one
of these makes the tool unusable for the defined workflow.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| YouTube video download | Core acquisition path — yt-dlp is the industry-standard tool | Low | yt-dlp supports 1800+ sites, handles auth via cookies, format selection, metadata extraction. Python API available via `yt_dlp` library. |
| YouTube Shorts download | Shorts behave differently (vertical 9:16, <60s) and need separate handling | Low | Same yt-dlp tooling; need format detection and different transcoding profile |
| X (Twitter) post/video acquisition | Second core acquisition path | High | X API severely rate-limited under free/basic tier since 2023. Browser scraping violates ToS; legal risk is real. Fallback: unofficial Python libraries (twscrape, ntscrape) — fragile and subject to breakage. Must treat as high-risk subsystem. |
| English-to-Chinese text translation | All source content is English; all target platforms are Chinese | Medium | LLM APIs (Claude, GPT-4o) outperform DeepL for cultural adaptation and idiomatic Chinese. DeepL/Google better for cost if volume is high. Two modes needed: short-form (titles/captions) and long-form (video descriptions). |
| ASR transcription (speech-to-text) | Required to generate source subtitles from video audio | Medium | faster-whisper (CTranslate2-based) is 4x faster than openai/whisper at equivalent accuracy. Whisper large-v3 has 97.9% accuracy (LibriSpeech). Run locally to avoid per-minute API cost accumulation. |
| Subtitle translation (EN→ZH) | Chinese viewers cannot read English subtitles | Medium | Separate from body translation — timing metadata (SRT/VTT) must be preserved. Translation should be sentence-aware, not line-by-line, for natural Chinese phrasing. |
| Subtitle burn-in (hardcoded) | Chinese platforms expect embedded subs; users cannot toggle external tracks | Medium | FFmpeg filter `subtitles=` or `ass=`. Must handle font selection (CJK fonts required), font size, and positioning for vertical video. |
| Video transcoding to platform specs | Each platform has strict resolution/bitrate/codec requirements | Medium | FFmpeg wrapping via `ffmpeg-python` or `subprocess`. See platform specs table below. |
| Publish to Douyin | Core target platform, 550M+ MAU | High | No individual-accessible open API. Requires Playwright/Selenium browser automation. Anti-bot detection is aggressive — stealth plugins (playwright-stealth, nodriver) needed. |
| Publish to Toutiao (今日头条) | Core target platform; ByteDance ecosystem has cross-promotion with Douyin | Medium | 头条号 has a documented content publish API. Less automation complexity than Douyin. |
| Publish to Xiaohongshu (小红书) | Core target platform, 300M+ MAU | High | No public API. Browser automation only. Known to use fingerprinting and behavioral detection. social-auto-upload (open-source) demonstrates it's possible but fragile. |
| Publish to Baidu (百家号) | Core target platform | Medium | 百家号 has a documented content API. Lower automation risk than Douyin/XHS. |
| Content deduplication | Without dedup, the same video gets published repeatedly on re-runs | Low | Hash-based (SHA256 of source URL + content ID). Persist seen-IDs in SQLite. Idempotency key pattern for upload jobs. |
| Persistent job state | Long-running pipeline steps (download, transcode, translate, publish) must survive crashes | Medium | SQLite or Redis-backed state machine per content item. States: DISCOVERED → DOWNLOADED → TRANSCODED → TRANSLATED → PUBLISHED/FAILED. |
| Cron/scheduled polling | Tool must run unattended on a cloud server, polling sources on a schedule | Low | APScheduler (in-process, suitable for single-server deployment) or simple cron. Celery only if multi-worker scale is needed — overkill for v1. |

---

## Platform Video Specifications Reference

| Platform | Format | Resolution | Aspect Ratio | Max Duration | Notes |
|----------|--------|------------|--------------|--------------|-------|
| Douyin | MP4, H.264 | 1080x1920 (primary) | 9:16 vertical | 15s–10min | 60fps supported; minimum 24fps |
| Xiaohongshu | MP4, H.264 | 1080x1920 (video), 1:1 or 4:3 also supported | 9:16 preferred | <5min for most content | AAC audio; process time 10–30 min after upload |
| Toutiao | MP4, H.264 | 1080p | 16:9 or 9:16 | Varies by content type | Toutiao accepts article+video embeds |
| Baidu 百家号 | MP4, H.264 | 1080p | 16:9 | Varies | API-based upload |

---

## Differentiators

Features that distinguish this tool from basic "download and repost" scripts.
Not required for a working v1, but provide competitive advantage as the tool matures.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Rule-based source monitoring | Automatically discover new content from configured channels/accounts without manual input | Medium | Subscribe to YouTube channel feeds (RSS: `https://www.youtube.com/feeds/videos.xml?channel_id=...`) + X account monitoring. Rules engine: filter by keyword, duration, view count, recency. |
| Per-platform content adaptation | Douyin needs vertical 9:16; Toutiao wants article format; XHS wants image+text notes — same content, different packaging | High | Platform profile system: given a source video, output profile defines crop strategy, subtitle style, title format, and publishing metadata per target. |
| Aspect ratio auto-conversion | Horizontal (16:9) YouTube videos converted to vertical (9:16) for Douyin/XHS via smart cropping | Medium | FFmpeg `crop` filter with face/subject-aware centering (more complex) OR simple center crop (simpler). Center crop works for most talking-head content. |
| Title/description localization | Titles and descriptions that read naturally in Chinese, not literal translations | Medium | LLM prompt engineering: provide source title + source context + platform norms. Different prompts per platform (Douyin title <30 chars; XHS title can be longer with hashtags). |
| Thumbnail generation | Attractive thumbnails improve CTR on Chinese platforms | Medium | Extract keyframe from video OR use source thumbnail. Overlay Chinese text with Pillow. |
| Configurable content filters | Don't publish content that is too short, too long, or in the wrong language | Low | Pre-processing filters: duration range, language detection (langdetect), explicit content keywords. |
| Retry with backoff on publish failure | Browser automation sessions expire; publishing fails transiently — smart retry avoids manual intervention | Medium | Exponential backoff with jitter. Classify errors: retryable (session timeout, rate limit) vs permanent (content violation, account suspended). |
| Publish queue scheduling | Spread publishing over time rather than burst-posting, which triggers platform spam detection | Medium | Per-platform configurable delay between posts (e.g., minimum 30 min between Douyin uploads). |
| Proxy rotation for acquisition | X and YouTube can rate-limit or block cloud server IPs | Medium | Support HTTP/SOCKS5 proxy list with rotation. yt-dlp has native `--proxy` support. |
| Cost tracking for API calls | Translation and ASR API calls have real costs — tracking prevents surprises | Low | Log token counts per job. Estimate cost per content item (useful for deciding whether to use LLM vs DeepL per content type). |
| Webhook/notification on completion or failure | Operator needs to know when something breaks without constantly checking logs | Low | Send notifications via Telegram bot, email, or webhook. Particularly valuable for unattended cloud deployment. |

---

## Anti-Features

Features to deliberately NOT build in v1. These are either explicitly out of scope or
would add complexity without proportional value.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Web management UI | Adds substantial frontend complexity for a single-operator tool | Config file + CLI commands. Log files + optional Telegram notifications for visibility. |
| Multi-user / SaaS mode | Account management, billing, and per-user isolation multiply every other feature's complexity | Single-user assumption throughout. No auth layer, no tenant isolation. |
| Live stream capture | Fundamentally different acquisition model (continuous, chunked, real-time processing) from VOD | Explicitly exclude live content using duration/live-status metadata from yt-dlp. |
| Comment management / engagement | Engagement is a separate domain (platform-specific, requires ongoing interaction) | Only publish; never read or respond to comments. |
| AI-generated content creation | Creating original content is a different product | Only process and republish existing source content. |
| Video editing / effects | Platform-specific effects (Douyin stickers, XHS filters) require platform-native tooling | Stick to format conversion, subtitle overlay, and optional crop. No creative editing. |
| Automatic monetization | Ad-insertion or affiliate links in republished content dramatically increases legal exposure | Strictly publish without modification to revenue-generating elements. |
| On-the-fly re-translation on edit | Triggering re-translation whenever source content is updated is complex and wasteful | Process once, store result. Manual re-trigger only. |
| Distributed worker farm | Single-server is the stated deployment target; distributed architecture adds operational burden | APScheduler + subprocess concurrency is sufficient for one-person's content volume. |
| Platform analytics ingestion | Reading analytics from each platform (views, likes) requires additional API permissions | Focus exclusively on the write path. |

---

## Feature Dependencies

Dependencies that constrain build order:

```
YouTube RSS/API → Content Discovery (channels/playlists)
yt-dlp download → all downstream processing (nothing works without source media)

ASR transcription (faster-whisper) → Source subtitle file (SRT/VTT)
Source subtitle file → Subtitle translation
Subtitle translation → Subtitle burn-in

Text translation → Chinese title + description for publishing
Video transcoding → Platform-compliant video file
Subtitle burn-in → Final video file (must happen after transcoding OR transcode after burn-in)

  Note: Subtitle burn-in and transcoding order matters.
  Option A: Transcode first (to target resolution) → burn subtitles at target resolution [recommended]
  Option B: Burn subtitles first → transcode (risks subtitle re-scaling artifacts)

Final video file + Chinese metadata → Platform publishing
Platform publishing → Deduplication record write (only after confirmed success)

Job state persistence → All pipeline stages (required from day 1; retrofitting is painful)
Deduplication store → Content discovery (prevents re-queuing already-processed items)

Scheduled polling → Source monitoring rules engine
Source monitoring rules → Content discovery filtering
```

---

## MVP Definition

The minimal set that delivers end-to-end working automation for one source and one target:

**Must Have (MVP)**
1. YouTube channel polling via RSS (no API key needed for RSS)
2. yt-dlp download (video + metadata)
3. faster-whisper ASR transcription (local, offline)
4. Subtitle translation via LLM API (one provider, configurable)
5. Subtitle burn-in via FFmpeg
6. Video transcoding to 1080x1920 H.264 MP4 (Douyin vertical profile)
7. Publish to Douyin via Playwright automation
8. SQLite job state tracking with deduplication
9. APScheduler for periodic polling
10. Config file (YAML/TOML) for channel list, credentials, and API keys

**Defer from MVP**
- X (Twitter) acquisition — legal/technical risk; add after YouTube path is stable
- Toutiao, Xiaohongshu, Baidu publishing — add one at a time after Douyin is solid
- Rule-based filtering beyond basic channel subscription
- Thumbnail generation
- Notifications / webhooks
- Proxy rotation
- Aspect ratio auto-conversion (center crop is a later enhancement; start with 9:16 source content or accept letterboxing)

---

## Feature Prioritization Matrix

| Feature | Impact | Effort | Risk | Priority |
|---------|--------|--------|------|----------|
| YouTube download (yt-dlp) | High | Low | Low | P0 — MVP |
| Job state persistence (SQLite) | High | Low | Low | P0 — MVP |
| ASR transcription (faster-whisper) | High | Medium | Low | P0 — MVP |
| Subtitle translation | High | Medium | Low | P0 — MVP |
| Subtitle burn-in (FFmpeg) | High | Medium | Low | P0 — MVP |
| Video transcoding (FFmpeg) | High | Medium | Low | P0 — MVP |
| Douyin publishing (Playwright) | High | High | High | P0 — MVP (core value) |
| Deduplication | High | Low | Low | P0 — MVP |
| APScheduler polling | Medium | Low | Low | P0 — MVP |
| Config file system | Medium | Low | Low | P0 — MVP |
| Toutiao publishing (API) | High | Medium | Medium | P1 — Phase 2 |
| Baidu 百家号 publishing (API) | Medium | Medium | Low | P1 — Phase 2 |
| Xiaohongshu publishing (Playwright) | High | High | High | P1 — Phase 2 |
| X acquisition | Medium | High | High | P2 — Phase 3 |
| Rule-based source filtering | Medium | Medium | Low | P2 — Phase 3 |
| Thumbnail generation | Low | Medium | Low | P3 — Later |
| Retry with backoff | Medium | Medium | Low | P1 — Phase 2 |
| Publish queue scheduling | Medium | Low | Low | P1 — Phase 2 |
| Proxy rotation | Medium | Medium | Low | P2 — Phase 3 |
| Notification / webhook | Low | Low | Low | P2 — Phase 3 |
| Per-platform content adaptation | Medium | High | Low | P3 — Later |
| Aspect ratio auto-conversion | Low | Medium | Low | P3 — Later |

---

## Compliance Notes

These are not features to build but constraints that shape every feature:

- **China AI labeling law (effective Sept 1, 2025):** All AI-processed content (including AI-translated subtitles, LLM-generated descriptions) must carry explicit and embedded labels when published on Chinese platforms. The tool must support injecting disclosure text in titles or descriptions (e.g., "AI翻译" tag). Failure risks account suspension and regulatory penalties.
- **Copyright:** Republishing third-party content without authorization is a copyright violation in most jurisdictions. This is a personal tool and the operator bears responsibility. Build-in a configurable allowlist (only process content from explicitly approved channels) to force intentional opt-in.
- **X ToS:** Browser scraping of X is explicitly prohibited and X has filed lawsuits against scrapers (since 2023). Any X acquisition feature must be clearly flagged as high-risk and use official API where possible.
- **Platform account safety:** Burst-publishing and automated sessions risk account bans. Rate limiting and human-like delays between actions are required, not optional.

---

## Sources

- [social-auto-upload (dreammis) — open source Douyin/XHS/Bilibili auto-uploader](https://github.com/dreammis/social-auto-upload)
- [youtube-uploader (jack-jackhui) — LLM video → Chinese platforms pipeline](https://github.com/jack-jackhui/youtube-uploader)
- [Xiaohongshu video specs — Hashmeta](https://hashmeta.com/blog/ideal-xiaohongshu-video-specs-complete-guide-to-resolution-length-formats/)
- [Douyin video quality optimization — Oreate AI](https://www.oreateai.com/blog/a-comprehensive-analysis-of-douyin-video-quality-optimization-7-key-elements-from-shooting-to-uploading/6f43f6357e107589dfb0443a34e81a47)
- [yt-dlp GitHub](https://github.com/yt-dlp/yt-dlp)
- [Choosing Whisper variants (faster-whisper, WhisperX) — Modal](https://modal.com/blog/choosing-whisper-variants)
- [Playwright stealth / anti-bot evasion — Scrapeless](https://www.scrapeless.com/en/blog/avoid-bot-detection-with-playwright-stealth)
- [X/Twitter scraping challenges 2025 — APIScrapy](https://apiscrapy.com/twitter-x-scraping-challenges/)
- [China AI content labeling rules (Sept 2025) — Harris Sliwoski](https://harris-sliwoski.com/chinalawblog/chinas-new-ai-labeling-rules-what-every-china-business-needs-to-know/)
- [APScheduler vs Celery comparison](https://calmops.com/programming/python/task-scheduling-apscheduler-celery/)
- [TikHub multi-platform API (Douyin, XHS, Toutiao, etc.)](https://api.tikhub.io/)
- [ByteDance/Toutiao cross-platform ecosystem — AIR Media-Tech](https://air.io/en/audience-growth/20-most-popular-chinese-platforms-to-distribute-youtube-videos)
