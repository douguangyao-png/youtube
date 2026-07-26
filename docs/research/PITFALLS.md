# Domain Pitfalls: Cross-Platform Content Syndication Tool

**Domain:** Automated YouTube/X scraping + Chinese platform publishing
**Project:** CrossPost (跨平台内容搬运工具)
**Researched:** 2026-03-14
**Confidence:** MEDIUM-HIGH (verified via GitHub issues, official Chinese platform reports, legal sources)

---

## Critical Pitfalls

These mistakes cause outright failures, account terminations, or legal exposure that require the project to be rebuilt or abandoned.

---

### Pitfall 1: YouTube Bot Detection Will Break the Downloader in Production

**What goes wrong:**
yt-dlp is the standard tool for YouTube downloads, but YouTube continuously evolves anti-bot systems. As of early 2026, YouTube requires "Proof of Origin" (PO Token) handshakes and enforces SABR (Server-Based Adaptive Bit Rate) that actively resets connections from recognized downloader traffic. Unattended server deployments get flagged within hours to days — the "Sign in to confirm you're not a bot" error blocks all downloads.

**Why it happens:**
YouTube recognizes server datacenter IPs and headless automation patterns. Guest tokens now bind to browser fingerprints; pure server IPs are permanently banned. yt-dlp's formerly reliable `android_sdkless` client fallback is being phased out. YouTube changes internal endpoints, client identifiers, and rate limits every few weeks, so any static configuration breaks on schedule.

**Consequences:**
- All downloads stop silently or with cryptic errors
- Without monitoring, the queue fills with failed jobs
- Account cookies used to bypass bot detection risk the Google account being banned

**Prevention:**
- Always pass `--cookies-from-browser firefox` (Firefox stores cookies in plain SQLite, not locked like Chrome/Chromium) and keep cookies refreshed weekly via a scheduled browser session
- Implement PO Token extraction support (yt-dlp has wiki docs on this)
- Keep yt-dlp updated weekly via cron: `pip install --upgrade yt-dlp`
- Use residential proxies or route traffic through a proxy that presents a non-datacenter IP
- Monitor download success rates; alert if success rate drops below 85%
- Use exponential backoff with random jitter — never fixed retry intervals

**Warning signs:**
- "Sign in to confirm you're not a bot" errors appearing
- Success rate drops in download metrics
- Sudden format unavailability errors

**Phase to address:** Phase 1 (YouTube scraping core) — design the downloader with health checks and update hooks from day one, not as an afterthought.

---

### Pitfall 2: Chinese Platform Automation Triggers Account Bans

**What goes wrong:**
Douyin banned 2.6 million accounts in Q1 2025 alone for "water army" and automated activity. Their AI risk detection processes individual cases in under 3 seconds with 85%+ accuracy. Xiaohongshu has upgraded its AI originality detection model that cross-checks content against Douyin and other platforms. Publishing the same video to multiple Chinese platforms with identical metadata, identical timestamps, or bot-like posting cadence is a near-certain ban trigger.

**Why it happens:**
Chinese platforms use behavioral fingerprinting: posting speed, device consistency, IP reputation, content fingerprint matching across platforms, and account age patterns. Automated publishing from a headless browser on a server IP hits multiple detection signals simultaneously.

**Consequences:**
- Account permanently banned with no recovery path
- Associated IP and device fingerprint banned, making new accounts immediately suspicious
- Platform appeals are slow or ineffective for automated-abuse flags

**Prevention:**
- Add human-like delays between all platform interactions: Gaussian jitter (not fixed intervals), random long pauses (5% of requests should be 15-30 seconds)
- Rotate between posting times — never publish on a fixed cron schedule like every hour on the hour
- Stagger cross-platform publishing by 2-6 hours per platform
- For Xiaohongshu specifically: use `playwright-stealth` to mask headless browser fingerprints; maintain consistent user-agent and viewport across sessions
- For Douyin: the Open Platform API (requires business verification) is safer than browser automation; pursue this first even if it takes longer to set up
- Never reuse the same video file byte-for-byte; re-encode or watermark slightly differently for each platform

**Warning signs:**
- "Rate limit" or "frequency limit" errors from platform APIs
- Captcha challenges appearing mid-session
- Posts going into permanent "under review" status

**Phase to address:** Phase 3 (platform publishing) — must be designed with anti-detection as a first-class requirement, not bolted on after an account ban.

---

### Pitfall 3: Republishing Copyrighted Content Is Legally Exposed

**What goes wrong:**
This tool's core function — taking videos from YouTube/X and republishing them on Chinese platforms — is copyright infringement by default unless the content is licensed CC, the original creator has given permission, or the content is in the public domain. Chinese law explicitly requires online short video platforms to verify copyright before distribution. Willful copyright violation in the US carries statutory damages up to $150,000 per work. A 2019 Chinese court case found an app that republished 50,000+ Douyin videos liable for 5 million RMB.

**Why it happens:**
The "it's already public" misconception: content being publicly viewable does not mean it is freely redistributable. YouTube's own Terms of Service Section 5.1 prohibits downloading content without written permission. X/Twitter's ToS prohibits scraping even public data without API authorization.

**Consequences:**
- Takedown notices, account bans on Chinese platforms
- Civil litigation exposure (especially if the tool is monetized)
- Chinese platforms may cooperate with copyright holders and preemptively ban accounts republishing from known foreign creators

**Prevention:**
- Implement a per-channel/creator whitelist: only process content from creators who have explicitly permitted redistribution (e.g., Creative Commons channels)
- Check YouTube video license field via the Data API (`snippet.license == 'creativeCommon'`)
- Add a content filter that rejects any video with third-party copyright claims already attached (detectable via YouTube Data API `contentDetails.contentRating`)
- Consider adding attribution overlays to published content as a minimum good-faith measure
- Document the whitelist approval process so the user consciously reviews what they're republishing

**Warning signs:**
- Receiving DMCA takedown notices
- Chinese platform moderators flagging "infringing" content and removing posts
- Original creator complaining or contacting platform

**Phase to address:** Phase 1 (design) — the rule engine that decides what content to process must have licensing checks as a gate, not a filter applied later.

---

### Pitfall 4: X (Twitter) Scraping Is Fundamentally Unreliable Without Budget

**What goes wrong:**
The official X API costs $5,000-$42,000/month at tiers that support automation. The free tier was removed. Browser-based scraping of X breaks every 2-4 weeks because guest tokens are now bound to browser fingerprints, doc_ids rotate, and datacenter IPs are permanently banned. Maintaining a DIY X scraper costs 10-15 developer hours per month in repairs.

**Why it happens:**
X actively combats scraping as a business priority (to force API revenue). In January 2025, X implemented guest token binding to browser fingerprints, making datacenter IP scraping extremely difficult.

**Consequences:**
- X scraping becomes a perpetual maintenance burden consuming most available engineering time
- If X scraping breaks silently, the rule engine continues trying and burning through retries
- Third-party scraping services (TwitterAPI.io at $0.15/1,000 tweets) become a recurring cost

**Prevention:**
- Design the X scraper as a pluggable adapter with a circuit breaker — when it fails, fail fast and degrade gracefully rather than retrying indefinitely
- Budget for a third-party X API service as the primary approach, with browser automation as a fallback only
- Use `snscrape` or third-party paid APIs rather than raw browser automation for X
- Implement an "X scraping is down" alert with a health dashboard showing per-source success rates
- Treat X as optional feature scope that can be disabled without affecting YouTube functionality

**Warning signs:**
- X scraper success rate drops to 0% without code changes
- Guest token or rate limit errors
- Content suddenly appearing as empty/protected

**Phase to address:** Phase 2 (X scraping) — architect as a separate, isolated module with health monitoring; clearly scope it as higher-maintenance than YouTube.

---

## Moderate Pitfalls

---

### Pitfall 5: ASR Transcription + Translation Quality Is Deceptively Hard

**What goes wrong:**
Whisper produces good English transcription under clean conditions but degrades significantly with background music, overlapping speech, accents, and technical jargon. Translation from English to Chinese introduces a second compounding error layer. Chinese has many homophones and context-dependent meanings that machine translation mishandles. The result is subtitles that are grammatically correct but semantically wrong — which looks worse than no subtitles at all on Chinese platforms where viewers will notice.

**Specific failure modes:**
- Background music causes hallucinated words or repeated phrases in Whisper output
- Subtitle timing drifts on videos with long pauses or silent intros
- Technical/domain-specific terms (especially proper nouns, product names) are transliterated incorrectly
- Simplified vs Traditional Chinese: Whisper defaults to Traditional; Chinese mainland platforms need Simplified (GB2312/UTF-8 Simplified)

**Prevention:**
- Pre-process audio to reduce background music before ASR (use `demucs` for vocal separation on music-heavy content)
- Use `whisper-large-v3` or `faster-whisper` with `language=en` explicitly set; never rely on auto-detect for non-Chinese content
- Add a post-processing pass that checks subtitle segment duration (flag segments under 0.5s or over 10s)
- For Simplified Chinese: use `--language zh` and verify output is Simplified; add a conversion step with `opencc` (OpenCC library) if needed
- Queue a human review flag for videos where ASR confidence is below threshold
- Test translation quality specifically on technical vocabulary relevant to the target content categories

**Warning signs:**
- Subtitles that repeat phrases multiple times
- Very long single subtitle segments (indication of hallucination)
- Comments on published content complaining about subtitle accuracy

**Phase to address:** Phase 2 (transcription and translation pipeline) — build quality checks into the pipeline output, not just assume Whisper+translation is "good enough."

---

### Pitfall 6: Video Format Mismatches Cause Silent Upload Failures

**What goes wrong:**
Chinese platforms have strict format requirements that differ from each other and from YouTube source formats. Douyin requires minimum 1080p, H.264, MP4 container, up to 60fps. Videos from YouTube may be 4K VP9/AV1 in MKV containers, portrait or landscape, with variable framerates. Uploading the wrong format via browser automation usually results in a silent failure or a "processing failed" status with no actionable error message.

**Specific format pitfalls:**
- YouTube Shorts are 9:16 vertical; regular YouTube is 16:9 horizontal. Douyin and Xiaohongshu prefer vertical (9:16)
- VP9/AV1 codecs are not accepted by all Chinese platform upload systems — must transcode to H.264
- File size limits: Douyin mobile uploads cap around 4GB; API uploads have different limits. Oversized files fail silently
- Bitrate: Douyin's recommended range is 500Kbps-3000Kbps; YouTube 4K videos can have bitrates of 30-50Mbps requiring aggressive transcoding

**Prevention:**
- Define a canonical output profile per platform: `{codec: h264, container: mp4, audio: aac_128k, resolution: 1080p, fps_max: 60}`
- Always transcode via FFmpeg to the canonical profile, never pass-through or re-mux assuming the source is compatible
- Verify output file against expected format specs before attempting upload (use `ffprobe` to check codec, container, bitrate)
- Implement upload response parsing: treat any non-explicit "success" response as a failure requiring investigation
- Add file size validation step before upload attempt

**Warning signs:**
- Upload returning "processing" status that never resolves
- Platform showing video as uploaded but not playable
- File size unexpectedly large (forgot bitrate cap) or small (transcoding error)

**Phase to address:** Phase 2 (video processing pipeline) — the transcoder module must have validation before and after processing.

---

### Pitfall 7: Error Cascading in the Processing Pipeline

**What goes wrong:**
The pipeline has many sequential steps: scrape → download → transcode → ASR → translate → format → upload. A failure in any step is not always visible at the next step. Examples: a partially downloaded video that appears complete but is corrupt; an ASR timeout that produces an empty SRT file that is passed to the subtitle burner, which succeeds but produces a video with no subtitles; an upload session that times out after 95% completion leaving a "phantom" video on the platform.

**Why it happens:**
Automation pipelines assume each step succeeds fully. File existence checks pass even for zero-byte or corrupt files. Network timeouts during long operations (large video downloads/uploads) are not the same as clean failures — partial states require explicit detection.

**Prevention:**
- Validate every artifact between pipeline stages:
  - After download: check file size > 0, verify duration with `ffprobe`, check MD5 if expected length is known
  - After transcode: verify output duration matches input within 0.5%, codec matches spec
  - After ASR: check SRT line count > 0, check timing coverage > 80% of video duration
  - After upload: parse the platform response explicitly; check for published URL
- Use a job state machine (e.g., Celery with explicit task states or a simple SQLite state table) — never assume a job succeeded because it didn't raise an exception
- Implement dead letter queues: jobs that fail 3 times move to manual review, not infinite retry
- Alert on partial failures immediately; do not batch-report errors at end-of-day

**Warning signs:**
- Videos published with no subtitles when subtitles were expected
- Upload counts on platform don't match successful job counts in the database
- Log files show jobs "completing" but published content count stagnates

**Phase to address:** Phase 1 (core pipeline design) — design the state machine before the first feature; retrofitting robust error handling onto a working pipeline is much harder.

---

### Pitfall 8: Stale Sessions and Credential Rot

**What goes wrong:**
The tool runs unattended on a cloud server. Browser sessions for Xiaohongshu (and Douyin without Open Platform API) expire within days to weeks. Cookie files for yt-dlp expire and are not automatically refreshed. API tokens for 今日头条 and 百度百家号 rotate on fixed schedules. The tool continues to "run" but all operations fail silently because session refresh is not implemented.

**Why it happens:**
Browser sessions require periodic human-like re-authentication. The server has no browser GUI to complete OAuth flows. Cookie-based auth doesn't automatically renew the way OAuth tokens can. Many developers implement initial auth but skip the renewal path, which only becomes a problem after initial testing.

**Prevention:**
- Design credential storage with explicit TTL metadata: `{token: "...", expires_at: "2026-04-01T00:00:00Z"}`
- Implement a credential health check that runs before each job batch and fails fast with alerts if any credential is expired or within 24h of expiry
- For browser automation: implement a "re-authentication flow" that can be triggered remotely (e.g., via a simple HTTP endpoint or SSH command) for accounts that require manual login
- For yt-dlp cookies: schedule a weekly cookie refresh task that either extracts from a maintained Firefox profile or alerts the user to manually refresh
- Store credentials encrypted at rest (use Python's `cryptography` library with a key stored in environment variables, not hardcoded)

**Warning signs:**
- All jobs for a specific platform failing simultaneously while other platforms succeed
- HTTP 401 or "session expired" errors in logs
- A sudden jump in error rate that aligns with a known token expiry date

**Phase to address:** Phase 1 (infrastructure) — credential management design must precede any platform integration work.

---

## Minor Pitfalls

---

### Pitfall 9: Cross-Platform Duplicate Content Detection

**What goes wrong:**
Xiaohongshu's 2026 AI originality system explicitly cross-checks uploaded content against Douyin and other platforms. Publishing identical video (same perceptual hash) to multiple Chinese platforms triggers originality violation flags. Baidu Baijiahao flags "old content republished as news" if the same article/video appears on Toutiao first.

**Prevention:**
- Re-encode video for each platform with platform-specific watermarks or metadata variations to change the perceptual hash
- Stagger publication: publish to platforms in sequence with 2-6 hour gaps, not simultaneously
- Vary metadata (title phrasing, description, tags) per platform rather than copy-pasting

**Phase to address:** Phase 3 (publishing workflow).

---

### Pitfall 10: Proxy Configuration for Mainland China Access

**What goes wrong:**
The tool runs on a cloud server that needs to access YouTube and X (blocked in China) while also publishing to Chinese platforms that may block foreign IPs. A single proxy configuration cannot serve both needs — you need different routing for outbound scraping vs. outbound publishing.

**Prevention:**
- Design the network layer with per-destination proxy profiles: `SCRAPING_PROXY` (routes to YouTube/X via a non-China IP) and `PUBLISHING_PROXY` (routes to Chinese platforms without proxy, or with a China-IP proxy)
- Test from the deployment server that Chinese platforms are reachable without proxy (many Chinese platforms block overseas datacenter IPs)
- Never route Chinese platform traffic through a VPN exit node that appears as a foreign IP — this is a ban trigger

**Phase to address:** Phase 1 (infrastructure/deployment) — network topology must be resolved before any integration testing.

---

### Pitfall 11: Subtitle Burn-In vs. Soft Subtitle Compatibility

**What goes wrong:**
Chinese platforms vary in their support for embedded (soft) subtitle tracks vs. burned-in (hard) subtitles. Douyin's mobile app displays burned-in subtitles correctly but may not render embedded SRT/ASS tracks from uploaded videos. Uploading with soft subtitles results in videos showing with no Chinese text.

**Prevention:**
- Default to burned-in subtitles (FFmpeg `subtitles` filter) for all Chinese platform uploads
- Burn in during the final transcoding step, after translation and timing verification
- Choose a font and size readable on mobile (minimum 36px at 1080p, with background shadow)

**Phase to address:** Phase 2 (video processing).

---

### Pitfall 12: 今日头条 / 百度百家号 Cross-Posting Conflicts

**What goes wrong:**
Baidu Baijiahao explicitly rejects content flagged as "old news" if the same content was already published on Toutiao/头条号. Publishing to both platforms from the same content source requires content-level differentiation, not just timing variation. The review system at Toutiao has flagged AI-translated content as "low quality" and reduced distribution.

**Prevention:**
- Treat 头条号 and 百家号 as separate content variants, not copies
- Consider publishing slightly different cut/edit of content or unique commentary for each
- Monitor distribution metrics per platform; if Toutiao consistently shows low distribution, the content may be flagged as low-quality AI-generated

**Phase to address:** Phase 3 (publishing workflow).

---

## Technical Debt Patterns

These are not immediate failures but become expensive to fix if not addressed early.

| Pattern | What Happens | Prevention |
|---------|-------------|------------|
| No download deduplication | Same video downloaded and processed multiple times as the rule engine rescans | Implement content hash DB from day one |
| Hardcoded platform selectors | Playwright selectors for Xiaohongshu break on every app update; breaks silently | Abstract all selectors into a configuration file; add selector health checks |
| Blocking I/O in pipeline | Long FFmpeg transcode blocks the entire job queue | Use subprocess with async wrappers or Celery task workers |
| Log files grow unbounded | 24/7 operation on a server fills disk and crashes the process | Implement log rotation (Python `logging.handlers.RotatingFileHandler`) from day one |
| Translation cost runaway | Unthrottled LLM API calls for long videos burn budget; a single 2-hour video can cost $5+ in tokens | Implement per-video cost estimation before API call; cap maximum video length |

---

## Integration Gotchas

| Integration | Specific Gotcha | Mitigation |
|-------------|----------------|------------|
| yt-dlp + proxy | Proxy auth format differs between HTTP/SOCKS5; `--proxy socks5://user:pass@host:port` syntax must be exact | Test proxy format independently before automation |
| Playwright + Douyin | Douyin detects `navigator.webdriver` flag; standard Playwright fails immediately | Use `playwright-stealth` or inject override scripts |
| Whisper + GPU | Whisper large-v3 requires 10GB VRAM; if running on CPU-only server, inference takes 10x real-time | Profile server resources; use `faster-whisper` with `int8` quantization for CPU deployments |
| FFmpeg + subtitles | Font file must be present on server for subtitle burn-in; default font paths differ by OS | Bundle font file with the project; specify absolute path in FFmpeg command |
| 小红书 + image posts | Image aspect ratio must be 1:1 or 3:4; other ratios auto-cropped in ways that cut subject out of frame | Pre-validate and pad/crop images to target ratio before upload |
| Celery + long tasks | Default Celery task timeout kills FFmpeg mid-transcode on large videos | Set `soft_time_limit` and `time_limit` based on actual video length; use chord for pipeline stages |

---

## Performance Traps

| Concern | Trap | Better Approach |
|---------|------|----------------|
| Transcoding queue | Processing videos sequentially blocks the queue for hours | Use Celery workers with concurrency matching available CPU cores; keep transcode and upload workers separate |
| ASR on long videos | Whisper processes entire audio in memory; 2-hour video = OOM on small servers | Chunk audio into 10-minute segments; process in parallel; stitch SRT output |
| Database for job state | Using a flat JSON file or SQLite with no indexing slows as job history grows | Use SQLite with proper indexes on `(status, created_at)` from the start |
| Download storage | Unprocessed downloads accumulate; 100 videos/day = ~200GB/week if not cleaned up | Implement TTL-based cleanup: delete source files after successful processing |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|-----------|
| Credentials in `.env` committed to git | API keys, cookies, browser sessions leaked | Use `.gitignore` for all `.env` files; use a secrets manager or environment variables injected at deploy time |
| Platform session cookies stored unencrypted | If server is compromised, attacker can hijack platform accounts | Encrypt credential store with key derived from environment variable |
| No rate limiting on retry logic | On API failure, infinite retry hammers the platform and accelerates ban | Implement circuit breaker pattern: after 3 failures in 5 minutes, open circuit for 30 minutes |
| Running browser automation as root | Chromium/Firefox vulnerabilities can be exploited for privilege escalation | Run Playwright in a dedicated non-root user; use Docker with `--cap-drop=ALL` |

---

## Phase-Specific Warnings

| Phase Topic | Most Likely Pitfall | Mitigation Strategy |
|-------------|--------------------|--------------------|
| Phase 1: Core infrastructure | No state machine for pipeline jobs → silent failures cascade | Design job state machine before any feature implementation |
| Phase 1: Credential management | Stale sessions kill all platform publishing after 2 weeks | Implement credential TTL and health check before any integration |
| Phase 1: Network/proxy setup | Wrong proxy routing causes YouTube blocks and Chinese platform blocks simultaneously | Test each destination independently; implement per-destination proxy profiles |
| Phase 2: YouTube download | Bot detection breaks downloader within hours of server deployment | Use Firefox cookies + PO token support + weekly cookie refresh from day one |
| Phase 2: X scraping | X scraping breaks every 2-4 weeks; becomes maintenance sinkhole | Implement circuit breaker and treat X as degradable optional feature |
| Phase 2: Video processing | Format mismatches cause silent upload failures | Always validate `ffprobe` output against platform spec before upload attempt |
| Phase 2: ASR/translation | Poor quality subtitles look worse than no subtitles | Add ASR confidence check and subtitle coverage validation |
| Phase 3: Douyin publishing | Automated publishing triggers ban within days | Human-like delays, Gaussian jitter, staggered publishing cadence |
| Phase 3: Xiaohongshu | Identical content cross-posted from other platforms detected and flagged | Re-encode video per platform, vary metadata, stagger publication |
| Phase 3: 头条 + 百家号 | Same content rejected as "old news" or "low quality AI translation" | Treat each platform as distinct content target, not copy-paste |
| All phases | Copyright exposure from republishing without permission | Implement whitelist-only mode with per-channel license verification |

---

## Sources

- [yt-dlp GitHub Issue #13067: YouTube bot detection](https://github.com/yt-dlp/yt-dlp/issues/13067)
- [yt-dlp GitHub Issue #15865: All public YouTube videos require login](https://github.com/yt-dlp/yt-dlp/issues/15865)
- [PO Token System: yt-dlp DeepWiki](https://deepwiki.com/yt-dlp/yt-dlp/3.4.1-potoken-authentication-system)
- [Bypassing YouTube 2026 SABR blocks - DEV Community](https://dev.to/ali_ibrahim/bypassing-the-2026-youtube-great-wall-a-guide-to-yt-dlp-v2rayng-and-sabr-blocks-1dk8)
- [6 Ways to Get YouTube Cookies for yt-dlp in 2026](https://dev.to/osovsky/6-ways-to-get-youtube-cookies-for-yt-dlp-in-2026-only-1-works-2cnb)
- [抖音一季度封禁涉水军账号260万个 - 新浪科技](https://finance.sina.com.cn/tech/roll/2025-04-22/doc-inetzraw0883821.shtml)
- [抖音2025避坑指南 - 知乎](https://zhuanlan.zhihu.com/p/1945791642775827314)
- [小红书内容搬运封号风险 - 知乎](https://zhuanlan.zhihu.com/p/21702399149)
- [小红书2026新规 - 微盛企微管家](https://college.wshoto.com/a/308199.html)
- [X Twitter API Alternatives 2026](https://twitterapi.io/articles/twitter-api-alternatives-tools-for-developers-2026)
- [Scraping Twitter 2025: API Apocalypse - DEV Community](https://dev.to/sivarampg/scraping-twitter-in-2025-a-developers-guide-to-surviving-the-api-apocalypse-5bbd)
- [Playwright CAPTCHA & Bot Detection 2026 - BrowserStack](https://www.browserstack.com/guide/playwright-captcha)
- [Playwright Stealth - Scrapeless](https://www.scrapeless.com/en/blog/avoid-bot-detection-with-playwright-stealth)
- [Legal Risks in Cross-Platform Content Syndication 2025](https://www.influencers-time.com/legal-risks-in-cross-platform-content-syndication/)
- [China Online Short Video Platform Norms - China Law Translate](https://www.chinalawtranslate.com/en/norms-for-the-administration-of-online-short-video-platforms-and-detailed-implementation-rules-for-online-short-video-content-review-standards/)
- [Whisper Chinese Subtitle Issues - GitHub Discussion #277](https://github.com/openai/whisper/discussions/277)
- [Whisper Subtitle Timing Issues - GitHub Discussion #1147](https://github.com/openai/whisper/discussions/1147)
- [Douyin Video Specs - Oreate AI Blog](https://www.oreateai.com/blog/a-comprehensive-analysis-of-douyin-video-quality-optimization-7-key-elements-from-shooting-to-uploading/6f43f6357e107589dfb0443a34e81a47)
- [百家号将旧闻冒充新闻发布拒绝 - CSDN](https://blog.csdn.net/zengmingen/article/details/121597501)
