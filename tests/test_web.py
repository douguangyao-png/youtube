"""Tests for the CrossPost web dashboard."""

from datetime import datetime, timezone

from sqlmodel import Session

from crosspost.models import Content, ContentStatus, PublishRecord, PublishStatus
from crosspost.web import (
    build_dashboard_model,
    enqueue_video_url,
    extract_youtube_video_id,
    render_dashboard,
)


def test_dashboard_counts_content_and_publish_status(in_memory_engine, sample_content_data):
    """Dashboard model aggregates content and publish states."""
    with Session(in_memory_engine) as session:
        content = Content(**sample_content_data, status=ContentStatus.TRANSLATED)
        session.add(content)
        session.commit()
        session.refresh(content)
        session.add(
            PublishRecord(
                content_id=content.id,
                video_id=content.video_id,
                platform="toutiao",
                status=PublishStatus.PUBLISHED,
            )
        )
        session.commit()

    model = build_dashboard_model(in_memory_engine, "sqlite:///:memory:")

    assert model.total == 1
    assert model.content_counts[ContentStatus.TRANSLATED] == 1
    assert model.publish_counts[PublishStatus.PUBLISHED] == 1


def test_dashboard_filters_by_content_status(in_memory_engine, sample_content_data):
    """Dashboard supports content status filtering."""
    with Session(in_memory_engine) as session:
        session.add(Content(**sample_content_data, status=ContentStatus.FAILED))
        session.add(
            Content(
                **{**sample_content_data, "video_id": "translated"},
                status=ContentStatus.TRANSLATED,
            )
        )
        session.commit()

    model = build_dashboard_model(in_memory_engine, "sqlite:///:memory:", status="FAILED")

    assert model.selected_status == "FAILED"
    assert len(model.items) == 1
    assert model.items[0].status == ContentStatus.FAILED


def test_render_dashboard_escapes_user_content(in_memory_engine, sample_content_data):
    """Dashboard rendering escapes title and error fields."""
    with Session(in_memory_engine) as session:
        session.add(
            Content(
                **{
                    **sample_content_data,
                    "title": "<script>alert(1)</script>",
                    "discovered_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
                },
                status=ContentStatus.FAILED,
                error_message="<b>bad</b>",
            )
        )
        session.commit()

    body = render_dashboard(build_dashboard_model(in_memory_engine, "sqlite:///:memory:"))

    assert "<script>alert(1)</script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body
    assert "&lt;b&gt;bad&lt;/b&gt;" in body


def test_render_dashboard_uses_base_path_for_filter_links(in_memory_engine):
    """Dashboard links can live behind an HTTPS reverse proxy subpath."""
    model = build_dashboard_model(
        in_memory_engine,
        "sqlite:///:memory:",
        base_path="/crosspost/",
    )

    body = render_dashboard(model)

    assert 'href="/crosspost/?status=all"' in body
    assert 'href="/crosspost/?status=DISCOVERED"' in body


def test_render_dashboard_records_view_uses_records_filter_links(in_memory_engine):
    """Records page keeps status filters inside /records."""
    model = build_dashboard_model(
        in_memory_engine,
        "sqlite:///:memory:",
        base_path="/crosspost",
        view="records",
    )

    body = render_dashboard(model)

    assert 'href="/crosspost/records?status=all"' in body
    assert 'href="/crosspost/records?status=DISCOVERED"' in body
    assert '制作记录' in body


def test_extract_youtube_video_id_accepts_common_url_shapes():
    """Manual submit accepts normal, short, and shorts URLs."""
    assert extract_youtube_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_video_id("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"


def test_enqueue_video_url_creates_manual_discovered_item(in_memory_engine):
    """Submitting a URL creates a DISCOVERED item for the pipeline."""
    content, created = enqueue_video_url(
        in_memory_engine,
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    )

    assert created is True
    assert content.video_id == "dQw4w9WgXcQ"
    assert content.channel_id == "manual"
    assert content.status == ContentStatus.DISCOVERED

    again, created_again = enqueue_video_url(
        in_memory_engine,
        "https://youtu.be/dQw4w9WgXcQ",
    )
    assert created_again is False
    assert again.id == content.id


def test_enqueue_video_url_resets_failed_item_for_retry(in_memory_engine):
    """Resubmitting a failed URL moves it back into the processing queue."""
    with Session(in_memory_engine) as session:
        session.add(
            Content(
                video_id="dQw4w9WgXcQ",
                channel_id="manual",
                title="Failed",
                video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                status=ContentStatus.FAILED,
                error_message="old error",
            )
        )
        session.commit()

    content, created = enqueue_video_url(
        in_memory_engine,
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    )

    assert created is False
    assert content.status == ContentStatus.DISCOVERED
    assert content.error_message is None
