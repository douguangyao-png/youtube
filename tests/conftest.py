"""Shared test fixtures for crosspost tests."""

import pytest
from sqlmodel import Session, SQLModel, create_engine

from crosspost.database import init_db


@pytest.fixture(scope="function")
def in_memory_engine():
    """Create an in-memory SQLite engine with all tables created."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_db(engine)
    yield engine
    engine.dispose()


@pytest.fixture(scope="function")
def session(in_memory_engine):
    """Provide a SQLModel Session for the in-memory database."""
    with Session(in_memory_engine) as s:
        yield s


@pytest.fixture
def tmp_config_file(tmp_path):
    """Write a minimal YAML config to a temp file and return the path."""
    config_content = """
channels:
  - channel_id: "UCtest123"
    name: "Test Channel"

download:
  output_dir: "/tmp/downloads"
  max_duration: 180

schedule:
  poll_interval_minutes: 30
"""
    config_path = tmp_path / "config.yaml"
    config_path.write_text(config_content)
    return config_path


@pytest.fixture
def sample_content_data():
    """Return a dict with valid Content field values for testing."""
    from datetime import datetime, timezone

    return {
        "video_id": "dQw4w9WgXcQ",
        "channel_id": "UCtest123",
        "title": "Test Video Title",
        "description": "A test video description",
        "duration": 120,
        "thumbnail_url": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
        "video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "published_at": datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        "discovered_at": datetime(2024, 1, 15, 13, 0, 0, tzinfo=timezone.utc),
    }
