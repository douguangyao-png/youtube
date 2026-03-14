# Phase 2: Content Processing - Research

**Researched:** 2026-03-14
**Domain:** FFmpeg transcoding, faster-whisper ASR, pysubs2 ASS subtitle generation, DeepL translation, Anthropic Claude API, Python pipeline patterns
**Confidence:** HIGH (core stack), MEDIUM (bilingual subtitle positioning details)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Subtitle burn-in style**
- White text on semi-transparent black bar (60% opacity)
- Font: Noto Sans CJK SC Bold
- Bilingual: Chinese on top, English smaller below
- Horizontal video: 24px Chinese / 18px English, positioned 8% from bottom
- Vertical video (Shorts): 20px Chinese / 15px English, positioned 20% from bottom (avoid platform UI overlay)
- Long sentences auto-wrap, maximum 2 lines per subtitle
- Subtitles burned into all output videos — no soft subtitle option

**Platform title/description translation**
- LLM (not DeepL) generates titles and descriptions per platform
- Titles are re-created per platform style, not direct translations
- Descriptions are condensed/rewritten by LLM, not direct translations
- Three distinct platform prompts:
  - Toutiao (头条): news/information tone, ~30 chars
  - Baijiahao (百家号): formal/SEO tone, ~30 chars
  - Xiaohongshu — DEFERRED (not in v1)
- Original video tags/hashtags are NOT translated or carried over

**Output format**
- Single universal output per video (not per-platform)
- 1080p H.264 MP4
- Bitrate dynamically matched to source video quality
- No aspect ratio conversion (no cropping to 3:4)
- All outputs include burned-in bilingual subtitles

**Processing pipeline order**
- State flow: DOWNLOADED → (transcode + ASR in parallel) → translate → burn subtitles → PROCESSED → translate metadata → TRANSLATED
- Intermediate artifacts (SRT files, transcoded video) preserved on disk

**Failure handling**
- All processing steps retry 2 times before marking FAILED
- Pure music / no-dialogue videos: NOT a failure — skip subtitles, proceed to next step
- Partial success is preserved — resume from failure point, don't re-run completed steps
- DeepL free tier (500K chars/month) sufficient for personal use; monitor usage

### Claude's Discretion
- FFmpeg filter chain construction details
- faster-whisper model size selection (large-v3 vs medium)
- DeepL API integration details and chunking strategy
- LLM prompt engineering for platform-specific titles
- Exact retry/backoff timing (tenacity config)
- Intermediate file naming and directory structure

### Deferred Ideas (OUT OF SCOPE)
- Xiaohongshu publishing — XHS not in v1, no 3:4 aspect ratio conversion
- Per-platform video re-encoding for anti-detection (different perceptual hash) — Phase 3 if needed
- AI smart editing of long videos — v2 (PROC-08)
- Web UI for monitoring processing status — v2
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| PROC-01 | faster-whisper local ASR extracts English subtitles as SRT with accurate timestamps | faster-whisper 1.1.x API, WhisperModel.transcribe(), segment-to-SRT via pysubs2 |
| PROC-02 | English subtitles translated to Chinese, timing preserved, sentence-level | DeepL translate_text() batch API, srt library for parse/compose, timing passthrough |
| PROC-03 | Chinese subtitles burned into video with CJK font, horizontal/vertical adaptation | pysubs2 SSAStyle (BorderStyle=3, BackColour alpha), FFmpeg subtitles filter with fontsdir |
| PROC-04 | Title and description translated to natural Chinese per platform style via LLM | Anthropic Claude Haiku 4.5 API, platform-specific system prompts, structured output |
| PROC-05 | Transcode to H.264 MP4 1080p, dynamic bitrate, via FFmpeg subprocess | ffprobe JSON probe, FFmpeg libx264 CRF 20-23, subprocess pattern matching existing codebase |
</phase_requirements>

---

## Summary

Phase 2 builds the content processing pipeline: FFmpeg transcoding (PROC-05), faster-whisper ASR to SRT (PROC-01), DeepL subtitle translation (PROC-02), pysubs2 + FFmpeg bilingual subtitle burn-in (PROC-03), and Claude LLM metadata translation (PROC-04). All components are well-established Python libraries with clear APIs. The pipeline is synchronous, following the pattern established in Phase 1 (no async, tenacity retries, SQLModel state machine).

The most technically nuanced component is bilingual subtitle burn-in: the approach requires generating a two-style ASS file (Chinese Bold on top of a dark bar, English smaller below) rather than burning two separate SRT files sequentially. This is done with pysubs2 generating a single ASS file with two styled SSAEvent layers per time segment. The FFmpeg `subtitles` filter with `fontsdir` pointing to a bundled Noto Sans CJK SC font directory handles the CJK rendering correctly on headless Linux.

The pipeline order locked by user decisions — transcode + ASR in parallel, then translate subtitles, then burn-in — means the processor module orchestrates two branches before merging. State idempotency is achieved by writing artifact paths to the Content row before advancing status; a restart skips any step whose output path is already populated.

**Primary recommendation:** Build `processor.py` as a single orchestration module with discrete step functions: `probe_video()`, `transcode()`, `transcribe()`, `translate_subtitles()`, `build_ass()`, `burn_subtitles()`. Each step checks for existing output before running. Use `pysubs2` exclusively for all subtitle manipulation (SRT and ASS). Drive FFmpeg and ffprobe via `subprocess.run()` directly — no wrappers.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| faster-whisper | 1.1.x | ASR transcription, English speech to SRT segments | 4x faster than openai/whisper on CPU via CTranslate2, INT8 quantization |
| pysubs2 | 1.8.x | SRT parsing, ASS generation with full style control | Native whisper segment loader, supports BorderStyle=3 background box, Color alpha |
| deepl | 1.x (official SDK) | Subtitle translation EN→ZH batch API | Official SDK, 500K chars/month free tier, tag_handling for structure preservation |
| anthropic | 0.40.x | Claude Haiku 4.5 API for title/description rewrite | Best EN→ZH cultural tone, $1/$5 per M tokens, structured output |
| FFmpeg 7.x | system binary | Transcoding (libx264) and subtitle burn-in (subtitles filter) | Direct subprocess — no wrapper needed, handles complex filter chains |
| opencc-python-reimplemented | 1.x | Traditional → Simplified Chinese conversion on Whisper output | Whisper outputs Traditional Chinese; mainland platforms require Simplified |
| tenacity | 8.x | Retry decorator — already in codebase | Matches established pattern from downloader.py |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| srt | 3.5.x | Simple SRT parse/compose for DeepL chunking pass | Lightweight SRT round-trip when pysubs2 full ASS overhead not needed |
| loguru | 0.7.x | Logging — already in codebase | All processing steps |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pysubs2 | python-ass | pysubs2 has whisper loader, better docs, active maintenance |
| pysubs2 | srt only | srt has no style system — cannot generate ASS for burn-in |
| anthropic SDK | openai SDK | Either works; Claude is locked decision for this project |
| opencc-python-reimplemented | opencc-py | opencc-py requires C extension; reimplemented is pure Python |

**Installation:**
```bash
uv add faster-whisper pysubs2 deepl anthropic opencc-python-reimplemented srt
```

---

## Architecture Patterns

### Recommended Project Structure

```
src/crosspost/
├── processor.py          # Main orchestration: process_downloaded_videos()
├── transcoder.py         # FFmpeg transcode + ffprobe probe functions
├── transcriber.py        # faster-whisper ASR → pysubs2 SRT
├── translator.py         # DeepL subtitle translation, Claude metadata translation
├── subtitler.py          # pysubs2 ASS assembly + FFmpeg burn-in
├── config.py             # Extend AppSettings with ProcessingConfig
└── models.py             # Add srt_path, translated_srt_path, processed_video_path fields
```

### Pattern 1: Idempotent Step Functions

Each processing step checks whether its output artifact already exists before running. This enables crash recovery without re-running expensive operations (ASR, translation).

**What:** Every step function takes `content: Content` and returns the output artifact path. If the path is already set on the Content row, the step is skipped.
**When to use:** All processing steps that write artifacts (transcode, transcribe, translate, burn-in).

```python
# Source: established project pattern from downloader.py
def transcode_video(content: Content, settings: ProcessingConfig) -> str:
    """Returns path to transcoded video. No-op if already done."""
    if content.processed_video_path and Path(content.processed_video_path).exists():
        logger.info("Transcode already done for video_id={}", content.video_id)
        return content.processed_video_path
    # ... run FFmpeg
```

### Pattern 2: Parallel Transcode + ASR, Then Sequential Steps

The pipeline runs transcode and ASR in parallel (both read the same input file, both are slow), then subtitle translation and burn-in proceed sequentially.

**What:** Use Python `concurrent.futures.ThreadPoolExecutor` for the parallel branch. Both tasks are I/O + CPU bound and do not share state.
**When to use:** The DOWNLOADED → transcode + ASR branch only.

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

with ThreadPoolExecutor(max_workers=2) as executor:
    futures = {
        executor.submit(transcode_video, content, settings): "transcode",
        executor.submit(transcribe_video, content, settings): "transcribe",
    }
    results = {}
    for future in as_completed(futures):
        step_name = futures[future]
        results[step_name] = future.result()  # raises on exception
```

### Pattern 3: State Machine Integration (Write Before Advance)

All artifact paths are written to the Content row before the status is advanced. A partial write (e.g., only srt_path written) means the next run skips ASR but still translates.

```python
# Source: adapted from downloader.py state transition pattern
with Session(engine) as session:
    item = session.get(Content, content.id)
    item.srt_path = srt_path
    item.translated_srt_path = translated_srt_path
    item.processed_video_path = processed_video_path
    item.status = ContentStatus.PROCESSED
    item.processed_at = datetime.utcnow()
    session.commit()
```

### Pattern 4: Bilingual ASS Subtitle Construction

For each SRT segment pair (English + Chinese translation), create TWO SSAEvent entries in a single SSAFile with different styles: `Chinese` style (top, larger, bold) and `English` style (bottom, smaller).

The Chinese subtitle uses Alignment=2 (bottom center) with MarginV set to 8% of video height. The English subtitle uses the same timing but with a negative vertical offset applied via `\pos()` override tag to place it just below the Chinese line.

```python
# Source: pysubs2 API docs + ASS format specification
import pysubs2
from pysubs2 import SSAFile, SSAStyle, SSAEvent, Color

def build_bilingual_ass(
    en_srt_path: str,
    zh_srt_path: str,
    output_ass_path: str,
    video_height: int,
    is_vertical: bool,
) -> str:
    subs = SSAFile()

    # Chinese style: white text, black semi-transparent box (60% opacity = &H99 alpha)
    # BorderStyle=3 draws opaque box; BackColour alpha &H99 = ~60% opacity
    zh_fontsize = 20 if is_vertical else 24
    en_fontsize = 15 if is_vertical else 18
    margin_pct = 0.20 if is_vertical else 0.08
    marginv = int(video_height * margin_pct)

    subs.styles["Chinese"] = SSAStyle(
        fontname="Noto Sans CJK SC",
        fontsize=zh_fontsize,
        bold=True,
        primarycolor=Color(255, 255, 255, 0),   # white, fully opaque
        backcolor=Color(0, 0, 0, 153),           # black, 60% opaque (255*0.6=153)
        borderstyle=3,
        outline=0,
        shadow=0,
        alignment=2,  # bottom center
        marginv=marginv + en_fontsize + 6,        # above English line
        wrap_style=0,
    )
    subs.styles["English"] = SSAStyle(
        fontname="Noto Sans CJK SC",
        fontsize=en_fontsize,
        bold=False,
        primarycolor=Color(255, 255, 255, 0),
        backcolor=Color(0, 0, 0, 153),
        borderstyle=3,
        outline=0,
        shadow=0,
        alignment=2,  # bottom center
        marginv=marginv,
        wrap_style=0,
    )
    # Merge EN + ZH segments by timestamp, create paired events
    # ... iterate segments, create SSAEvent for each with style="Chinese"/"English"
    subs.save(output_ass_path)
    return output_ass_path
```

**CRITICAL:** The `Color` constructor in pysubs2 uses `Color(r, g, b, a)` where `a=0` is fully opaque and `a=255` is fully transparent — this is the INVERSE of standard RGBA alpha. For 60% opacity: `a = int(255 * 0.4) = 102`.

### Pattern 5: FFmpeg Probe + Transcode

```python
import subprocess, json

def probe_video(video_path: str) -> dict:
    """Returns stream info dict with width, height, codec, bit_rate."""
    cmd = [
        "ffprobe", "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,bit_rate,codec_name,r_frame_rate",
        "-show_entries", "stream_tags=rotate",
        "-of", "json", video_path
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    return data["streams"][0] if data.get("streams") else {}

def transcode_to_h264(
    input_path: str,
    output_path: str,
    source_bitrate_kbps: int,
) -> str:
    """Transcode to H.264 MP4 1080p with CRF encoding."""
    # CRF 20-23: visually lossless for 1080p; lower = higher quality
    crf = 20 if source_bitrate_kbps > 4000 else 23
    cmd = [
        "ffmpeg", "-y", "-i", input_path,
        "-vf", "scale=-2:1080",        # scale to 1080p, keep aspect ratio
        "-c:v", "libx264", "-crf", str(crf), "-preset", "medium",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",      # web-compatible MP4
        output_path
    ]
    subprocess.run(cmd, capture_output=True, check=True, timeout=600)
    return output_path
```

### Pattern 6: faster-whisper Transcription

```python
from faster_whisper import WhisperModel
import pysubs2

def transcribe_to_srt(video_path: str, output_srt_path: str, model_size: str = "medium") -> str:
    """Transcribe English audio to SRT via faster-whisper."""
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        video_path,
        language="en",
        beam_size=5,
        vad_filter=True,           # silence filtering — pure music returns empty segments
        vad_parameters={"threshold": 0.5},
    )
    segment_list = list(segments)  # generator must be consumed

    if not segment_list:
        return ""  # empty = pure music / no dialogue — not a failure

    # Convert faster-whisper segments to pysubs2 format
    # pysubs2.load_from_whisper() expects list of dicts with start/end/text
    whisper_segments = [
        {"start": s.start, "end": s.end, "text": s.text.strip()}
        for s in segment_list
    ]
    subs = pysubs2.load_from_whisper(whisper_segments)
    subs.save(output_srt_path, format_="srt")
    return output_srt_path
```

**Note:** `pysubs2.load_from_whisper()` accepts a list of dicts with `start`, `end` (float seconds), and `text` — faster-whisper segment objects must be converted to this dict format first.

### Pattern 7: DeepL Subtitle Translation

```python
import deepl
import srt
from datetime import timedelta

def translate_srt(
    input_srt_path: str,
    output_srt_path: str,
    auth_key: str,
) -> str:
    """Translate SRT from English to Simplified Chinese via DeepL, preserving timing."""
    translator = deepl.Translator(auth_key)

    with open(input_srt_path) as f:
        subtitles = list(srt.parse(f.read()))

    texts = [sub.content for sub in subtitles]

    # Batch translate — DeepL accepts list of strings in one call
    results = translator.translate_text(
        texts,
        source_lang="EN",
        target_lang="ZH",        # Simplified Chinese
        split_sentences="nonewlines",
    )

    for sub, result in zip(subtitles, results):
        sub.content = result.text

    with open(output_srt_path, "w") as f:
        f.write(srt.compose(subtitles))

    return output_srt_path
```

**Note:** DeepL's `target_lang="ZH"` outputs Simplified Chinese by default. The `split_sentences="nonewlines"` prevents DeepL from splitting subtitle lines at internal newlines.

### Pattern 8: Claude Metadata Translation

```python
import anthropic

PLATFORM_PROMPTS = {
    "toutiao": (
        "You are a Chinese content editor for 今日头条 (Toutiao). "
        "Rewrite the following YouTube video title in Chinese for Toutiao. "
        "Use a news/information tone. Maximum 30 Chinese characters. "
        "Output ONLY the title, no explanation."
    ),
    "baijiahao": (
        "You are a Chinese content editor for 百家号 (Baijiahao). "
        "Rewrite the following YouTube video title in Chinese for Baijiahao. "
        "Use a formal, SEO-friendly tone. Maximum 30 Chinese characters. "
        "Output ONLY the title, no explanation."
    ),
}

def translate_metadata(
    title: str,
    description: str,
    platform: str,
    api_key: str,
) -> dict:
    """Returns {'title': str, 'description': str} in Chinese for the given platform."""
    client = anthropic.Anthropic(api_key=api_key)

    title_msg = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=100,
        system=PLATFORM_PROMPTS[platform],
        messages=[{"role": "user", "content": title}],
    )
    translated_title = title_msg.content[0].text.strip()

    desc_system = (
        f"You are a Chinese content editor. Condense and rewrite this YouTube video "
        f"description in Chinese for {platform}. Keep it under 200 characters. "
        f"Output ONLY the description."
    )
    desc_msg = client.messages.create(
        model="claude-haiku-4-5",
        max_tokens=300,
        system=desc_system,
        messages=[{"role": "user", "content": description}],
    )
    translated_desc = desc_msg.content[0].text.strip()

    return {"title": translated_title, "description": translated_desc}
```

### Pattern 9: FFmpeg Subtitle Burn-in

```python
def burn_subtitles(
    video_path: str,
    ass_path: str,
    output_path: str,
    fonts_dir: str,
) -> str:
    """Burn ASS subtitles into video using FFmpeg subtitles filter."""
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"subtitles={ass_path}:fontsdir={fonts_dir}",
        "-c:v", "libx264", "-crf", "20", "-preset", "medium",
        "-c:a", "copy",
        output_path,
    ]
    subprocess.run(cmd, capture_output=True, check=True, timeout=900)
    return output_path
```

**Note:** `fontsdir` must point to a directory containing the Noto Sans CJK SC font files. The font should be bundled with the project under `src/crosspost/assets/fonts/`. The `subtitles` filter (not `ass`) is used because it handles both SRT and ASS input files.

### Anti-Patterns to Avoid

- **Do not call DeepL once per subtitle line:** Batch all subtitle texts in a single `translate_text([...])` call. Per-line calls exhaust the free tier 20x faster and are rate-limited.
- **Do not use two sequential FFmpeg subtitle burn-in passes:** One for Chinese, one for English. Build a single ASS file with both layers — one FFmpeg pass only.
- **Do not use `ffmpeg-python` wrapper:** The project calls FFmpeg via `subprocess.run()` directly (matching research in SUMMARY.md). Wrappers add complexity for complex filter chains.
- **Do not use `whisper` (openai) instead of `faster-whisper`:** 4x slower on CPU, identical accuracy.
- **Do not advance status before writing artifact paths:** A crash between file write and DB update would be unrecoverable. Write paths first, status second, in a single `session.commit()`.
- **Do not load the faster-whisper model inside a retry loop:** Model loading is expensive (~2-10s). Load once, retry only the `transcribe()` call.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SRT timestamp parsing | Custom regex parser | `srt` library or `pysubs2` | Edge cases: missing blank lines, BOM, Windows CRLF, negative timestamps |
| ASS subtitle styling | Manual string formatting | `pysubs2` SSAStyle/SSAEvent | ASS format has 20+ style fields; pysubs2 validates and serializes correctly |
| Traditional→Simplified conversion | Manual character mapping | `opencc-python-reimplemented` | 70,000+ character mappings, phrase-level disambiguation, regional variants |
| Audio extraction for Whisper | FFmpeg subprocess | Pass video path directly to WhisperModel | faster-whisper handles audio extraction internally via ffmpeg |
| DeepL character count tracking | Custom counter | `result.billed_characters` on TextResult | SDK provides exact billed count per call |

**Key insight:** The subtitle pipeline (SRT → translate → ASS → burn) has a large number of edge cases at every stage. Use the established libraries for parsing and serialization; keep custom code only in the orchestration logic.

---

## Common Pitfalls

### Pitfall 1: faster-whisper Model Download on First Run

**What goes wrong:** On first run, faster-whisper downloads the model from Hugging Face (~1.5GB for large-v3, ~300MB for medium). This blocks the pipeline for 10-30 minutes with no progress indication, appearing as a hang.

**Why it happens:** `WhisperModel("medium", ...)` triggers lazy model download to `~/.cache/huggingface/`.

**How to avoid:** Pre-download the model during deployment (`python -c "from faster_whisper import WhisperModel; WhisperModel('medium', device='cpu', compute_type='int8')"`) or add a startup check that logs download progress. Document this in config comments.

**Warning signs:** First processing job takes 20+ minutes with no log output from the transcription step.

### Pitfall 2: pysubs2 Color Alpha is INVERTED

**What goes wrong:** Semi-transparent background box appears fully opaque or fully transparent.

**Why it happens:** pysubs2 `Color(r, g, b, a)` uses `a=0` for fully opaque and `a=255` for fully transparent — the OPPOSITE of standard RGBA. For 60% opacity on the black bar: `a = int(255 * 0.4) = 102`, not `int(255 * 0.6) = 153`.

**How to avoid:** Always comment the alpha formula: `# a=0 is opaque, a=255 is transparent; 60% opacity = a=102`.

**Warning signs:** Black bar is completely solid or subtitles appear without background box.

### Pitfall 3: Empty Segments = Pure Music, Not Failure

**What goes wrong:** `vad_filter=True` returns zero segments for a music-only video. Naively treating this as an error marks the video FAILED, blocking it permanently.

**Why it happens:** Silero VAD correctly identifies no speech — this is expected behavior for music videos.

**How to avoid:** Check `if not segment_list: return ""` (empty string, not error). Downstream subtitle steps skip gracefully when `srt_path` is `""`. The video is still transcoded and metadata-translated.

**Warning signs:** Music videos consistently in FAILED state with "transcription returned no segments" error.

### Pitfall 4: DeepL Splits Subtitle Lines Internally

**What goes wrong:** A subtitle entry with multiple sentences gets split by DeepL into multiple Chinese sentences that don't map 1:1 to the English segments — timing is broken.

**Why it happens:** Default `split_sentences="1"` means DeepL splits on punctuation within the text you send.

**How to avoid:** Set `split_sentences="nonewlines"` on all translate_text calls. This preserves line structure while still translating within each subtitle block.

**Warning signs:** Translated SRT has different number of subtitle entries than source SRT.

### Pitfall 5: FFmpeg `subtitles` Filter Requires fontsdir on Headless Linux

**What goes wrong:** Noto Sans CJK characters render as boxes/question marks on a headless server without the font installed system-wide.

**Why it happens:** The FFmpeg `subtitles` filter uses libass, which falls back to a default font when the named font isn't found. Default fonts don't contain CJK glyphs.

**How to avoid:** Bundle the Noto Sans CJK SC Bold font file in the project (`src/crosspost/assets/fonts/NotoSansCJKsc-Bold.otf`) and always pass `fontsdir=<absolute path to fonts dir>` to the subtitles filter. Verify with `fc-list | grep Noto` on the target server.

**Warning signs:** Burned-in video has empty rectangles where Chinese characters should be.

### Pitfall 6: `scale=-2:1080` Fails if Source is Already Below 1080p

**What goes wrong:** FFmpeg error "width/height not divisible by 2" or upscaling artifacts on short-form vertical videos that are 720p or smaller.

**Why it happens:** `scale=-2:1080` upscales short videos; `-2` auto-calculates width to be divisible by 2 but some codecs require divisibility by other factors.

**How to avoid:** Use `scale='if(gt(ih,1080),trunc(ow/a/2)*2,-2):if(gt(ih,1080),1080,-2)'` — only scale down if source exceeds 1080p. Or probe source dimensions first and skip scaling if already ≤ 1080p.

**Warning signs:** FFmpeg exits with code 1, stderr contains "not divisible by 2" or "invalid argument".

### Pitfall 7: Whisper Language Detection Confusion on Music Videos

**What goes wrong:** `language="en"` constraint is ignored by faster-whisper when vad_filter removes all speech, causing the model to try to transcribe music as speech in the detected language.

**Why it happens:** When segments are empty after VAD, `info.language` may still report a detected language; the behavior varies by model version.

**How to avoid:** Check `len(segment_list) == 0` explicitly after consuming the generator. Do NOT check `info.language` for this decision.

### Pitfall 8: ThreadPoolExecutor Swallows Exceptions Silently

**What goes wrong:** Transcode or ASR fails but the processing pipeline continues with missing artifacts.

**Why it happens:** `concurrent.futures` wraps exceptions; if you iterate `as_completed()` without re-raising, exceptions are lost.

**How to avoid:** Always call `future.result()` (which re-raises) on each completed future, or use `executor.map()` which propagates exceptions automatically.

---

## Code Examples

### Verified: faster-whisper transcription with VAD

```python
# Source: SYSTRAN/faster-whisper GitHub README
from faster_whisper import WhisperModel

model = WhisperModel("medium", device="cpu", compute_type="int8")
segments, info = model.transcribe(
    "audio.mp3",
    language="en",
    beam_size=5,
    vad_filter=True,
    vad_parameters={"threshold": 0.5, "min_silence_duration_ms": 500},
)
segment_list = list(segments)  # MUST consume generator before accessing info
```

### Verified: pysubs2 whisper segment loading

```python
# Source: pysubs2 1.8.0 API Reference
import pysubs2

# faster-whisper segments must be converted to dict format
whisper_dicts = [
    {"start": s.start, "end": s.end, "text": s.text.strip()}
    for s in faster_whisper_segments
]
subs = pysubs2.load_from_whisper(whisper_dicts)
subs.save("output.srt", format_="srt")
```

### Verified: pysubs2 SSAStyle with background box

```python
# Source: pysubs2 1.8.0 API Reference + ASS format spec
from pysubs2 import SSAStyle, Color

style = SSAStyle(
    fontname="Noto Sans CJK SC",
    fontsize=24,
    bold=True,
    primarycolor=Color(255, 255, 255, 0),  # white, opaque (a=0 is opaque in pysubs2)
    backcolor=Color(0, 0, 0, 102),          # black, 60% opacity (a=102 → 40% transparent)
    borderstyle=3,                           # 3 = opaque box background
    outline=0,
    shadow=0,
    alignment=2,   # bottom center (numpad layout)
    marginv=80,    # vertical margin in pixels from bottom edge
)
```

### Verified: DeepL batch translation

```python
# Source: DeepL Python SDK official README
import deepl

translator = deepl.Translator(auth_key)
results = translator.translate_text(
    ["Hello world", "How are you?"],
    source_lang="EN",
    target_lang="ZH",
    split_sentences="nonewlines",
)
# results[i].text = translated string
# results[i].billed_characters = int (for usage tracking)
```

### Verified: ffprobe JSON probe

```python
# Source: ffprobe documentation + community gists (verified pattern)
import subprocess, json

def probe_video(path: str) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height,bit_rate,codec_name",
         "-show_entries", "stream_tags=rotate",
         "-of", "json", path],
        capture_output=True, text=True, check=True
    )
    data = json.loads(result.stdout)
    return data.get("streams", [{}])[0]
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| openai/whisper (Python) | faster-whisper (CTranslate2) | 2023 | 4x CPU speedup, INT8 quantization, lower memory |
| Whisper large only | distil-large-v3 available | 2024 | 6x faster than large-v3 at 95% accuracy — usable for dev/test |
| Manual SRT parsing | pysubs2 / srt library | 2022+ | Edge case handling, format interop |
| openai/whisper for translation | DeepL for subtitles + LLM for metadata | 2024 | 20x cost reduction for bulk; LLM reserved for tone-critical short text |
| Claude 3.5 Haiku | Claude Haiku 4.5 | 2025 | $1/$5 per M tokens (input/output), same quality |

**Deprecated/outdated:**
- `openai/whisper` Python package: superseded by faster-whisper for production CPU use — use faster-whisper.
- `pysrt` library: less maintained than `srt` and `pysubs2` — use one of those instead.
- `google-cloud-translate`: not needed — DeepL for subtitles is cheaper and better for EN→ZH subtitle content.

---

## Model Size Recommendation (Claude's Discretion)

**Recommendation: `medium` for development and production on CPU-only servers.**

Rationale:
- `large-v3` (~1.5GB model): Higher accuracy (WER ~2.7% on English), but ~2-4x slower than medium on CPU. On a typical cloud CPU, large-v3 processes 1 minute of audio in 2-4 minutes. Suitable if GPU is available.
- `medium` (~290MB model): Sufficient accuracy for clear English speech (WER ~3.5%), processes 1 minute of audio in 30-60 seconds on CPU with INT8. Appropriate for the target content (short YouTube videos, clear speech).
- `distil-large-v3` (~756MB): 6x faster than large-v3 at 95% accuracy — viable if accuracy concerns arise with medium.

**Config flag:** Expose `asr_model: str = "medium"` in `ProcessingConfig` so operators can switch to `large-v3` without code changes.

---

## Open Questions

1. **Noto Sans CJK SC font availability on target server**
   - What we know: The font must be bundled or pre-installed; headless servers don't have it by default
   - What's unclear: License for font redistribution in the project repo (OFL 1.1 — open)
   - Recommendation: Bundle font file in `src/crosspost/assets/fonts/`. The SIL Open Font License 1.1 permits redistribution.

2. **DeepL `target_lang="ZH"` vs `"ZH-HANS"`**
   - What we know: DeepL documents `ZH` as Simplified Chinese; `ZH-HANS` may also work
   - What's unclear: Whether `ZH` is deprecated in favor of `ZH-HANS` in newer API versions
   - Recommendation: Use `"ZH"` initially; switch to `"ZH-HANS"` if DeepL raises a deprecation warning.

3. **Parallel transcode + ASR thread safety**
   - What we know: Both operations are independent subprocess/model calls reading the same input file
   - What's unclear: Whether faster-whisper `WhisperModel` is thread-safe when shared between threads
   - Recommendation: Instantiate a separate `WhisperModel` instance per transcription call (or use a module-level singleton with a lock). Given these videos are ≤3 minutes, single-threaded sequential is also acceptable if parallelism adds complexity.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-mock 3.14.x |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_processor.py -x -q` |
| Full suite command | `uv run pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PROC-01 | faster-whisper transcribes English audio to SRT segments | unit (mocked model) | `uv run pytest tests/test_transcriber.py -x` | ❌ Wave 0 |
| PROC-01 | Empty segment list (music video) returns empty string, not error | unit | `uv run pytest tests/test_transcriber.py::test_transcribe_music_video -x` | ❌ Wave 0 |
| PROC-02 | DeepL translates SRT lines preserving count and timing | unit (mocked API) | `uv run pytest tests/test_translator.py::test_translate_srt -x` | ❌ Wave 0 |
| PROC-02 | Batch translation sends all lines in one API call | unit (mocked API) | `uv run pytest tests/test_translator.py::test_translate_srt_batches -x` | ❌ Wave 0 |
| PROC-03 | build_bilingual_ass produces valid ASS file with two styles | unit | `uv run pytest tests/test_subtitler.py::test_build_bilingual_ass -x` | ❌ Wave 0 |
| PROC-03 | Vertical video uses 20% marginv; horizontal uses 8% | unit | `uv run pytest tests/test_subtitler.py::test_margin_by_orientation -x` | ❌ Wave 0 |
| PROC-04 | Claude API called with platform-specific system prompt | unit (mocked API) | `uv run pytest tests/test_translator.py::test_translate_metadata_toutiao -x` | ❌ Wave 0 |
| PROC-05 | ffprobe probe returns width/height/bitrate | unit (mocked subprocess) | `uv run pytest tests/test_transcoder.py::test_probe_video -x` | ❌ Wave 0 |
| PROC-05 | transcode_to_h264 builds correct ffmpeg command | unit (mocked subprocess) | `uv run pytest tests/test_transcoder.py::test_transcode_command -x` | ❌ Wave 0 |
| PROC-05 | Idempotent step skips if artifact already exists | unit | `uv run pytest tests/test_processor.py::test_transcode_skips_if_done -x` | ❌ Wave 0 |
| All | process_downloaded_videos transitions DOWNLOADED → PROCESSED → TRANSLATED | unit (mocked steps) | `uv run pytest tests/test_processor.py::test_full_processing_pipeline -x` | ❌ Wave 0 |
| All | Crash recovery: partial state skips completed steps on retry | unit | `uv run pytest tests/test_processor.py::test_resume_from_partial -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_processor.py tests/test_transcriber.py tests/test_transcoder.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `tests/test_processor.py` — covers PROC-01 through PROC-05 orchestration and state machine transitions
- [ ] `tests/test_transcriber.py` — covers faster-whisper ASR, music-video pass-through (PROC-01)
- [ ] `tests/test_transcoder.py` — covers ffprobe, transcode command construction (PROC-05)
- [ ] `tests/test_translator.py` — covers DeepL subtitle translation, Claude metadata translation (PROC-02, PROC-04)
- [ ] `tests/test_subtitler.py` — covers pysubs2 ASS generation, horizontal/vertical margin logic (PROC-03)
- [ ] `src/crosspost/assets/fonts/NotoSansCJKsc-Bold.otf` — bundled font file for CI and production

---

## Sources

### Primary (HIGH confidence)

- SYSTRAN/faster-whisper GitHub README — transcription API, compute_type, vad_filter parameters
- pysubs2 1.8.0 API Reference (pysubs2.readthedocs.io) — SSAStyle fields, borderstyle=3, Color alpha semantics, load_from_whisper
- DeepLcom/deepl-python GitHub README — translate_text batch API, split_sentences parameter, target_lang ZH
- Anthropic pricing page (platform.claude.com) — Haiku 4.5 at $1/$5 per million tokens
- FFmpeg documentation (ffmpeg.org) — subtitles filter, fontsdir, force_style

### Secondary (MEDIUM confidence)

- pysubs2 tutorial + ASS format spec (tcax.org/docs/ass-specs.htm) — BorderStyle=3 box background, BackColour alpha encoding
- Modal blog "Choosing Whisper variants" — faster-whisper vs WhisperX performance comparison
- ffprobe JSON format documentation (filmalize.readthedocs.io) — stream fields, rotation tag location
- Multiple WebSearch results on CRF encoding for H.264 1080p (CRF 20-23 range)

### Tertiary (LOW confidence)

- DeepL `target_lang="ZH"` vs `"ZH-HANS"` — not definitively confirmed which is current canonical value; verify against SDK at implementation time

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all libraries are well-documented with official sources
- Architecture: HIGH — follows established project patterns from Phase 1
- Pitfalls: HIGH for ASR/FFmpeg, MEDIUM for DeepL edge cases
- Bilingual ASS styling: MEDIUM — pysubs2 Color alpha semantics confirmed via API docs; exact pixel positioning requires runtime testing

**Research date:** 2026-03-14
**Valid until:** 2026-09-14 (stable libraries; Claude model IDs may change sooner)
