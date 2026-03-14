"""Tests for Content model, ContentStatus enum, and database operations."""

import pytest
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from crosspost.models import Content, ContentStatus


class TestContentStatusEnum:
    def test_all_enum_values_exist(self):
        """All expected ContentStatus enum values are defined."""
        assert ContentStatus.DISCOVERED
        assert ContentStatus.DOWNLOADING
        assert ContentStatus.DOWNLOADED
        assert ContentStatus.PROCESSED
        assert ContentStatus.TRANSLATED
        assert ContentStatus.PUBLISHED
        assert ContentStatus.FAILED

    def test_enum_values_are_strings(self):
        """ContentStatus values are string-typed for SQLite storage."""
        assert isinstance(ContentStatus.DISCOVERED.value, str)
        assert isinstance(ContentStatus.FAILED.value, str)

    def test_enum_round_trips_through_sqlite(self, session, sample_content_data):
        """ContentStatus values serialize and deserialize correctly through SQLite."""
        base_data = {k: v for k, v in sample_content_data.items() if k != "video_id"}
        for status in ContentStatus:
            content = Content(**base_data, video_id=f"vid_{status.value}", status=status)
            session.add(content)
        session.commit()

        results = session.exec(select(Content)).all()
        statuses_found = {r.status for r in results}
        assert statuses_found == set(ContentStatus)


class TestContentCRUD:
    def test_create_content_with_discovered_status(self, session, sample_content_data):
        """Content row can be created with DISCOVERED status and persisted."""
        content = Content(**sample_content_data, status=ContentStatus.DISCOVERED)
        session.add(content)
        session.commit()
        session.refresh(content)

        assert content.id is not None
        assert content.status == ContentStatus.DISCOVERED
        assert content.video_id == sample_content_data["video_id"]

    def test_content_fields_round_trip(self, session, sample_content_data):
        """Content fields store and retrieve correctly from SQLite."""
        content = Content(**sample_content_data, status=ContentStatus.DISCOVERED)
        session.add(content)
        session.commit()
        session.refresh(content)

        assert content.channel_id == sample_content_data["channel_id"]
        assert content.title == sample_content_data["title"]
        assert content.description == sample_content_data["description"]
        assert content.duration == sample_content_data["duration"]
        assert content.thumbnail_url == sample_content_data["thumbnail_url"]
        assert content.video_url == sample_content_data["video_url"]

    def test_content_optional_fields_default_to_none(self, session, sample_content_data):
        """Optional fields (video_path, error_message, etc.) default to None."""
        content = Content(**sample_content_data, status=ContentStatus.DISCOVERED)
        session.add(content)
        session.commit()
        session.refresh(content)

        assert content.video_path is None
        assert content.thumbnail_path is None
        assert content.metadata_path is None
        assert content.downloaded_at is None
        assert content.failed_at is None
        assert content.error_message is None


class TestContentDeduplication:
    def test_duplicate_video_id_raises_integrity_error(self, session, sample_content_data):
        """Inserting a duplicate video_id raises IntegrityError (unique constraint)."""
        content1 = Content(**sample_content_data, status=ContentStatus.DISCOVERED)
        session.add(content1)
        session.commit()

        content2 = Content(**sample_content_data, status=ContentStatus.DISCOVERED)
        session.add(content2)
        with pytest.raises(IntegrityError):
            session.commit()

    def test_different_video_ids_can_coexist(self, session, sample_content_data):
        """Different video_ids can be stored without conflict."""
        base_data = {k: v for k, v in sample_content_data.items() if k != "video_id"}
        content1 = Content(**base_data, video_id="vid001", status=ContentStatus.DISCOVERED)
        content2 = Content(**base_data, video_id="vid002", status=ContentStatus.DISCOVERED)
        session.add(content1)
        session.add(content2)
        session.commit()

        results = session.exec(select(Content)).all()
        assert len(results) == 2


class TestStateTransitions:
    def test_transition_discovered_to_downloading(self, session, sample_content_data):
        """Status transitions from DISCOVERED to DOWNLOADING."""
        content = Content(**sample_content_data, status=ContentStatus.DISCOVERED)
        session.add(content)
        session.commit()

        content.status = ContentStatus.DOWNLOADING
        session.add(content)
        session.commit()
        session.refresh(content)

        assert content.status == ContentStatus.DOWNLOADING

    def test_transition_downloading_to_downloaded(self, session, sample_content_data):
        """Status transitions from DOWNLOADING to DOWNLOADED with downloaded_at set."""
        content = Content(**sample_content_data, status=ContentStatus.DOWNLOADING)
        session.add(content)
        session.commit()

        now = datetime.now(timezone.utc)
        content.status = ContentStatus.DOWNLOADED
        content.downloaded_at = now
        session.add(content)
        session.commit()
        session.refresh(content)

        assert content.status == ContentStatus.DOWNLOADED
        assert content.downloaded_at is not None

    def test_transition_downloading_to_failed(self, session, sample_content_data):
        """Status transitions from DOWNLOADING to FAILED with error_message set."""
        content = Content(**sample_content_data, status=ContentStatus.DOWNLOADING)
        session.add(content)
        session.commit()

        now = datetime.now(timezone.utc)
        content.status = ContentStatus.FAILED
        content.failed_at = now
        content.error_message = "Download failed: network timeout"
        session.add(content)
        session.commit()
        session.refresh(content)

        assert content.status == ContentStatus.FAILED
        assert content.error_message == "Download failed: network timeout"
        assert content.failed_at is not None

    def test_full_happy_path_transitions(self, session, sample_content_data):
        """Full state machine path: DISCOVERED -> DOWNLOADING -> DOWNLOADED."""
        content = Content(**sample_content_data, status=ContentStatus.DISCOVERED)
        session.add(content)
        session.commit()

        content.status = ContentStatus.DOWNLOADING
        session.add(content)
        session.commit()

        content.status = ContentStatus.DOWNLOADED
        content.downloaded_at = datetime.now(timezone.utc)
        content.video_path = "/downloads/vid.mp4"
        session.add(content)
        session.commit()
        session.refresh(content)

        assert content.status == ContentStatus.DOWNLOADED
        assert content.video_path == "/downloads/vid.mp4"
