"""Processing pipeline orchestrator for CrossPost.

Wires together transcode, ASR, subtitle translation, burn-in, and metadata
translation. Implements parallel execution, idempotent steps, crash recovery,
and retry-with-failure handling.

State flow (per locked decision):
DOWNLOADED -> (transcode + ASR parallel) -> translate srt -> burn subtitles
-> PROCESSED -> translate metadata -> TRANSLATED
"""

import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from loguru import logger
from sqlalchemy.engine import Engine
from sqlmodel import Session, select
from tenacity import retry, stop_after_attempt, wait_exponential

from crosspost.config import AppSettings
from crosspost.models import Content, ContentStatus
from crosspost.subtitler import build_bilingual_ass, burn_subtitles
from crosspost.transcoder import probe_video, transcode_to_h264
from crosspost.transcriber import transcribe_to_srt
from crosspost.translator import translate_metadata, translate_srt


def _process_single(engine: Engine, settings: AppSettings, video_id: str) -> None:
    """Run the full processing pipeline for a single content item.

    Each phase is idempotent: if the artifact path is already set on the
    Content row, that step is skipped. A crash mid-pipeline preserves
    completed steps; restart resumes from the failed step.

    Args:
        engine: SQLAlchemy engine for DB access.
        settings: Application settings with processing config.
        video_id: The video_id to process.
    """
    cfg = settings.processing
    output_dir = cfg.output_dir
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    max_retries = cfg.max_retries

    try:
        # ------------------------------------------------------------------
        # Phase A: Parallel transcode + ASR (ThreadPoolExecutor, max_workers=2)
        # ------------------------------------------------------------------
        with Session(engine) as session:
            content = session.exec(
                select(Content).where(Content.video_id == video_id)
            ).one()
            video_path = content.video_path
            need_transcode = content.processed_video_path is None
            need_asr = content.srt_path is None

        transcode_path = os.path.join(output_dir, f"{video_id}_transcoded.mp4")
        srt_path = os.path.join(output_dir, f"{video_id}_en.srt")

        def _do_transcode():
            info = probe_video(video_path)
            bitrate_kbps = int(info.get("bit_rate", 0)) // 1000
            return transcode_to_h264(video_path, transcode_path, bitrate_kbps)

        def _do_asr():
            return transcribe_to_srt(video_path, srt_path, cfg.asr_model)

        _transcode_with_retry = retry(
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            reraise=True,
        )(_do_transcode)

        _asr_with_retry = retry(
            stop=stop_after_attempt(max_retries),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            reraise=True,
        )(_do_asr)

        transcoded_result = None
        asr_result = None

        with ThreadPoolExecutor(max_workers=2) as pool:
            transcode_future = None
            asr_future = None

            if need_transcode:
                transcode_future = pool.submit(_transcode_with_retry)
            if need_asr:
                asr_future = pool.submit(_asr_with_retry)

            if transcode_future is not None:
                transcoded_result = transcode_future.result()
            if asr_future is not None:
                asr_result = asr_future.result()

        with Session(engine) as session:
            content = session.exec(
                select(Content).where(Content.video_id == video_id)
            ).one()
            if transcoded_result is not None:
                content.processed_video_path = transcoded_result
            if asr_result is not None:
                content.srt_path = asr_result
            session.add(content)
            session.commit()

        with Session(engine) as session:
            content = session.exec(
                select(Content).where(Content.video_id == video_id)
            ).one()
            current_srt = content.srt_path
            current_translated_srt = content.translated_srt_path
            current_ass = content.ass_path
            current_processed_video = content.processed_video_path

        # ------------------------------------------------------------------
        # Phase B: Subtitle translation (sequential)
        # ------------------------------------------------------------------
        is_music_video = current_srt == "" or current_srt is None

        if not is_music_video and current_translated_srt is None:
            translated_srt_path = os.path.join(output_dir, f"{video_id}_zh.srt")

            _translate_srt_retry = retry(
                stop=stop_after_attempt(max_retries),
                wait=wait_exponential(multiplier=1, min=2, max=30),
                reraise=True,
            )(lambda: translate_srt(current_srt, translated_srt_path, cfg.deepl_auth_key))

            translated_result = _translate_srt_retry()

            with Session(engine) as session:
                content = session.exec(
                    select(Content).where(Content.video_id == video_id)
                ).one()
                content.translated_srt_path = translated_result
                session.add(content)
                session.commit()
            current_translated_srt = translated_result

        # ------------------------------------------------------------------
        # Phase C: Build ASS + burn subtitles (sequential)
        # ------------------------------------------------------------------
        if not is_music_video and current_ass is None:
            ass_path = os.path.join(output_dir, f"{video_id}_bilingual.ass")
            final_path = os.path.join(output_dir, f"{video_id}_final.mp4")

            info = probe_video(current_processed_video)
            video_height = int(info.get("height", 1080))
            video_width = int(info.get("width", 1920))
            is_vertical = video_height > video_width

            _build_ass_retry = retry(
                stop=stop_after_attempt(max_retries),
                wait=wait_exponential(multiplier=1, min=2, max=30),
                reraise=True,
            )(lambda: build_bilingual_ass(
                current_srt, current_translated_srt, ass_path,
                video_height, is_vertical,
            ))

            ass_result = _build_ass_retry()

            fonts_dir = str(Path(cfg.font_path).parent)

            _burn_retry = retry(
                stop=stop_after_attempt(max_retries),
                wait=wait_exponential(multiplier=1, min=2, max=30),
                reraise=True,
            )(lambda: burn_subtitles(current_processed_video, ass_result, final_path, fonts_dir))

            burned_result = _burn_retry()

            with Session(engine) as session:
                content = session.exec(
                    select(Content).where(Content.video_id == video_id)
                ).one()
                content.ass_path = ass_result
                content.processed_video_path = burned_result
                session.add(content)
                session.commit()

        # ------------------------------------------------------------------
        # Phase D: Advance to PROCESSED
        # ------------------------------------------------------------------
        with Session(engine) as session:
            content = session.exec(
                select(Content).where(Content.video_id == video_id)
            ).one()
            content.status = ContentStatus.PROCESSED
            content.processed_at = datetime.utcnow()
            session.add(content)
            session.commit()

        # ------------------------------------------------------------------
        # Phase E: Metadata translation
        # ------------------------------------------------------------------
        with Session(engine) as session:
            content = session.exec(
                select(Content).where(Content.video_id == video_id)
            ).one()
            if content.platform_metadata is not None:
                logger.info("Metadata already translated for {}, skipping", video_id)
                return

            title = content.title
            description = content.description

        platform_meta = {}
        for platform in ["toutiao", "baijiahao"]:
            _meta_retry = retry(
                stop=stop_after_attempt(max_retries),
                wait=wait_exponential(multiplier=1, min=2, max=30),
                reraise=True,
            )(lambda p=platform: translate_metadata(title, description, p, cfg.anthropic_api_key))

            platform_meta[platform] = _meta_retry()

        with Session(engine) as session:
            content = session.exec(
                select(Content).where(Content.video_id == video_id)
            ).one()
            content.platform_metadata = json.dumps(platform_meta, ensure_ascii=False)
            content.status = ContentStatus.TRANSLATED
            content.translated_at = datetime.utcnow()
            session.add(content)
            session.commit()

        logger.info("Processing complete for video_id={}", video_id)

    except Exception as exc:
        logger.error("Processing failed for video_id={}: {}", video_id, exc)
        with Session(engine) as session:
            content = session.exec(
                select(Content).where(Content.video_id == video_id)
            ).one()
            content.status = ContentStatus.FAILED
            content.error_message = str(exc)
            content.failed_at = datetime.utcnow()
            session.add(content)
            session.commit()


def process_downloaded_videos(engine: Engine, settings: AppSettings) -> int:
    """Process all DOWNLOADED content through the full pipeline.

    Queries all Content rows with status == DOWNLOADED and runs _process_single
    for each. One failure does not block others.

    Args:
        engine: SQLAlchemy engine for DB access.
        settings: Application settings.

    Returns:
        Count of successfully processed videos.
    """
    with Session(engine) as session:
        downloaded = session.exec(
            select(Content).where(Content.status == ContentStatus.DOWNLOADED)
        ).all()
        video_ids = [c.video_id for c in downloaded]

    if not video_ids:
        logger.info("No DOWNLOADED content to process")
        return 0

    logger.info("Processing {} downloaded video(s)", len(video_ids))
    success_count = 0

    for vid in video_ids:
        try:
            _process_single(engine, settings, vid)
            with Session(engine) as session:
                content = session.exec(
                    select(Content).where(Content.video_id == vid)
                ).one()
                if content.status != ContentStatus.FAILED:
                    success_count += 1
        except Exception as exc:
            logger.error("Unexpected error processing {}: {}", vid, exc)

    logger.info("Processing complete: {}/{} succeeded", success_count, len(video_ids))
    return success_count
