"""SQLModel data models for CrossPost content state machine."""

from datetime import datetime
from enum import Enum
from typing import Optional

from sqlalchemy import Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel


class ContentStatus(str, Enum):
    """State machine status values for content lifecycle tracking."""

    DISCOVERED = "DISCOVERED"
    DOWNLOADING = "DOWNLOADING"
    DOWNLOADED = "DOWNLOADED"
    PROCESSED = "PROCESSED"
    TRANSLATED = "TRANSLATED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class Content(SQLModel, table=True):
    """Represents a piece of content being tracked through the pipeline."""

    __tablename__ = "content"

    id: Optional[int] = Field(default=None, primary_key=True)
    video_id: str = Field(
        unique=True,
        index=True,
        description="YouTube video ID — unique across the entire table for deduplication",
    )
    channel_id: str = Field(description="YouTube channel ID")
    title: str = Field(default="", description="Video title")
    description: str = Field(default="", description="Video description")
    duration: int = Field(default=0, description="Video duration in seconds")
    thumbnail_url: str = Field(default="", description="URL to video thumbnail")
    video_url: str = Field(default="", description="Original YouTube video URL")

    published_at: Optional[datetime] = Field(
        default=None, description="When the video was published on YouTube"
    )
    status: ContentStatus = Field(
        default=ContentStatus.DISCOVERED,
        sa_column=Column(
            SAEnum(ContentStatus, values_callable=lambda x: [e.value for e in x]),
            nullable=False,
        ),
        description="Current state in the content lifecycle",
    )

    # Downloaded artifact paths
    video_path: Optional[str] = Field(default=None, description="Local path to downloaded video file")
    thumbnail_path: Optional[str] = Field(default=None, description="Local path to downloaded thumbnail")
    metadata_path: Optional[str] = Field(default=None, description="Local path to metadata JSON file")

    # Processing artifact paths
    srt_path: Optional[str] = Field(default=None, description="Path to English SRT file")
    translated_srt_path: Optional[str] = Field(default=None, description="Path to Chinese translated SRT")
    ass_path: Optional[str] = Field(default=None, description="Path to bilingual ASS subtitle file")
    processed_video_path: Optional[str] = Field(
        default=None, description="Path to final processed video with burned subtitles"
    )

    # Processing timestamps
    processed_at: Optional[datetime] = Field(default=None, description="When processing completed")
    translated_at: Optional[datetime] = Field(default=None, description="When metadata translation completed")

    # Platform metadata
    platform_metadata: Optional[str] = Field(
        default=None, description="JSON string of per-platform translated titles/descriptions"
    )

    # Lifecycle timestamps
    discovered_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this content was first discovered",
    )
    downloaded_at: Optional[datetime] = Field(
        default=None, description="When the video was successfully downloaded"
    )
    failed_at: Optional[datetime] = Field(
        default=None, description="When the last failure occurred"
    )
    error_message: Optional[str] = Field(
        default=None, description="Error details from the most recent failure"
    )


class PublishStatus(str, Enum):
    """State values for per-platform publish attempts."""

    PENDING = "PENDING"
    PUBLISHING = "PUBLISHING"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class PublishRecord(SQLModel, table=True):
    """Tracks publishing state for one content item on one platform."""

    __tablename__ = "publish_record"

    id: Optional[int] = Field(default=None, primary_key=True)
    content_id: int = Field(foreign_key="content.id", index=True)
    video_id: str = Field(index=True)
    platform: str = Field(index=True)
    status: PublishStatus = Field(
        default=PublishStatus.PENDING,
        sa_column=Column(
            SAEnum(PublishStatus, values_callable=lambda x: [e.value for e in x]),
            nullable=False,
        ),
    )
    attempts: int = Field(default=0)
    platform_post_id: Optional[str] = Field(default=None)
    platform_url: Optional[str] = Field(default=None)
    error_message: Optional[str] = Field(default=None)
    next_attempt_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    published_at: Optional[datetime] = Field(default=None)
