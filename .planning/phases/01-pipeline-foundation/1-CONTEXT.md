# Phase 1: Pipeline Foundation - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

The system can discover, download, and track YouTube videos unattended. Delivers: YAML config, YouTube RSS polling, yt-dlp download, duration filtering, SQLite state machine with dedup, APScheduler scheduling, crash recovery.

Requirements: ACQ-01, ACQ-02, ACQ-03, ACQ-04, AUTO-01, AUTO-02, AUTO-03

</domain>

<decisions>
## Implementation Decisions

### Content filtering
- Only download videos ≤ 3 minutes (configurable via YAML, default 180 seconds)
- Duration obtained from yt-dlp metadata before download — skip videos exceeding threshold
- Applies to both regular videos and Shorts

### State machine design
- SQLite with content table tracking status: DISCOVERED → DOWNLOADED → PROCESSED → TRANSLATED → PUBLISHED / FAILED
- Deduplication by video ID — persistent across restarts
- All state defined upfront even though Phase 1 only uses DISCOVERED → DOWNLOADED

### Config approach
- YAML config file for channel list, credentials, schedule intervals, filter rules
- No web UI — config file + CLI is sufficient for v1
- Pydantic Settings for validation and type safety

### YouTube acquisition
- RSS feed polling (no API key needed): `https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID`
- RSS returns last 15 videos — polling interval must be frequent enough for high-output channels
- yt-dlp with Firefox cookies + PO Token support from day one (per research recommendation)

### Scheduling
- APScheduler with configurable polling interval
- SQLite-backed job persistence for APScheduler (survives restarts)

### Claude's Discretion
- SQLite schema details and column design
- Project directory structure and module organization
- Logging configuration (Loguru)
- Error handling patterns and retry logic
- Exact APScheduler job configuration

</decisions>

<specifics>
## Specific Ideas

- Duration filter is the primary content selection mechanism for v1 — keeps only short-form content suitable for Chinese platforms
- Research identified that server IPs get flagged by YouTube quickly — cookie/PO Token support is critical, not optional

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- No existing code — greenfield project

### Established Patterns
- Python 3.12 + uv (per research recommendation)
- SQLModel for ORM (Pydantic + SQLAlchemy)
- Loguru for logging

### Integration Points
- Phase 2 (Content Processing) consumes DOWNLOADED videos from SQLite
- Phase 3 (Publishing) consumes PUBLISHED-ready videos

</code_context>

<deferred>
## Deferred Ideas

- Web management UI for viewing conversion status, upload history, and managing subscriptions — potential Phase 4+ (currently Out of Scope for v1)
- AI smart editing — auto-extract key points from long videos and compress to short clips — v2 (PROC-08)

</deferred>

---

*Phase: 01-pipeline-foundation*
*Context gathered: 2026-03-14*
