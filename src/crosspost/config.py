"""Configuration system for CrossPost using Pydantic Settings with YAML support."""

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource


class ChannelConfig(BaseModel):
    """Configuration for a single YouTube channel to monitor."""

    channel_id: str
    name: str = ""
    max_duration: int | None = None  # None means "use global default"


class ProcessingConfig(BaseModel):
    """Processing pipeline settings for transcription, translation, and subtitle burn-in."""

    asr_model: str = "medium"
    output_dir: str = "./processed"
    font_path: str = "src/crosspost/assets/fonts/NotoSansCJKsc-Bold.otf"
    deepl_auth_key: str = ""
    anthropic_api_key: str = ""
    max_retries: int = 2


class DownloadConfig(BaseModel):
    """Download settings for yt-dlp."""

    output_dir: str = "./downloads"
    max_duration: int = 180  # seconds; videos longer than this are skipped
    format: str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
    cookies_browser: str = "firefox"
    cookies_file: str = ""


class ScheduleConfig(BaseModel):
    """APScheduler polling and job configuration."""

    poll_interval_minutes: int = Field(default=30, ge=1)
    misfire_grace_time: int = 300  # seconds

    @field_validator("poll_interval_minutes")
    @classmethod
    def must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("poll_interval_minutes must be >= 1")
        return v


class ApiPublisherConfig(BaseModel):
    """Configuration for an HTTP API based publisher."""

    endpoint: str = ""
    token: str = ""
    token_header: str = "Authorization"
    token_prefix: str = "Bearer"
    title_field: str = "title"
    description_field: str = "description"
    video_field: str = "video_path"
    extra_payload: dict[str, Any] = Field(default_factory=dict)


class BrowserPublisherConfig(BaseModel):
    """Configuration for a Playwright browser based publisher."""

    login_url: str = ""
    upload_url: str = ""
    storage_state_path: str = ""
    headless: bool = True
    title_selector: str = ""
    description_selector: str = ""
    file_selector: str = "input[type=file]"
    submit_selector: str = ""
    success_selector: str = ""
    wait_after_submit_seconds: int = 10


class PublisherConfig(BaseModel):
    """Per-platform publisher settings."""

    enabled: bool = False
    backend: str = "api"  # api, browser, dry_run
    min_interval_minutes: int = Field(default=120, ge=0)
    max_retries: int = Field(default=2, ge=1)
    api: ApiPublisherConfig = Field(default_factory=ApiPublisherConfig)
    browser: BrowserPublisherConfig = Field(default_factory=BrowserPublisherConfig)


class PublishingConfig(BaseModel):
    """Publishing stage configuration."""

    enabled: bool = False
    platforms: dict[str, PublisherConfig] = Field(default_factory=dict)


class YamlFileSource(PydanticBaseSettingsSource):
    """A settings source that reads from a YAML file path passed at init time."""

    def __init__(self, settings_cls: type[BaseSettings], yaml_file: str | None = None):
        super().__init__(settings_cls)
        self._yaml_file = yaml_file

    def get_field_value(self, field: Any, field_name: str) -> Any:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        if not self._yaml_file:
            return {}
        path = Path(self._yaml_file)
        if not path.exists():
            return {}
        import yaml

        with open(path) as f:
            data = yaml.safe_load(f) or {}
        return data


class AppSettings(BaseSettings):
    """Top-level application settings loaded from YAML config file."""

    channels: list[ChannelConfig] = []
    download: DownloadConfig = Field(default_factory=DownloadConfig)
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    publishing: PublishingConfig = Field(default_factory=PublishingConfig)
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    database_url: str = "sqlite:///crosspost.db"
    log_level: str = "INFO"

    # Store the yaml file path so we can expose it to the customise_sources classmethod
    # via a class-level attribute that gets set before each instantiation
    _yaml_file: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)

    def __new__(cls, _yaml_file: str | None = None, **values: Any) -> "AppSettings":
        # Temporarily store on class so settings_customise_sources can access it
        cls._yaml_file = _yaml_file
        instance = super().__new__(cls)
        return instance

    def __init__(self, _yaml_file: str | None = None, **values: Any) -> None:
        # Store yaml file on class before BaseSettings.__init__ calls settings_customise_sources
        self.__class__._yaml_file = _yaml_file
        super().__init__(**values)

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_source = YamlFileSource(settings_cls, yaml_file=cls._yaml_file)
        return (init_settings, env_settings, yaml_source)

    def get_max_duration(self, channel: ChannelConfig) -> int:
        """Return the effective max_duration for a channel.

        Uses channel-specific override if set, otherwise falls back to
        the global download.max_duration setting.
        """
        if channel.max_duration is not None:
            return channel.max_duration
        return self.download.max_duration
