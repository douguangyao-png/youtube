"""Tests for the config system (AppSettings, YAML loading, validation)."""

import pytest
from pydantic import ValidationError

from crosspost.config import AppSettings, ChannelConfig, DownloadConfig, ProcessingConfig, ScheduleConfig


class TestChannelConfig:
    def test_channel_config_minimal(self):
        """ChannelConfig requires channel_id, name defaults to empty string."""
        ch = ChannelConfig(channel_id="UCtest123")
        assert ch.channel_id == "UCtest123"
        assert ch.name == ""
        assert ch.max_duration is None

    def test_channel_config_with_max_duration(self):
        """ChannelConfig accepts per-channel max_duration override."""
        ch = ChannelConfig(channel_id="UCtest123", name="My Channel", max_duration=60)
        assert ch.max_duration == 60

    def test_channel_config_full(self):
        """ChannelConfig stores all fields correctly."""
        ch = ChannelConfig(channel_id="UCabc", name="Test Channel", max_duration=90)
        assert ch.channel_id == "UCabc"
        assert ch.name == "Test Channel"
        assert ch.max_duration == 90


class TestDownloadConfig:
    def test_download_config_defaults(self):
        """DownloadConfig applies default values when no fields are provided."""
        dc = DownloadConfig()
        assert dc.output_dir == "./downloads"
        assert dc.max_duration == 180
        assert dc.cookies_browser == "firefox"

    def test_download_config_custom(self):
        """DownloadConfig accepts custom values."""
        dc = DownloadConfig(output_dir="/custom/path", max_duration=120, cookies_browser="chrome")
        assert dc.output_dir == "/custom/path"
        assert dc.max_duration == 120
        assert dc.cookies_browser == "chrome"


class TestScheduleConfig:
    def test_schedule_config_defaults(self):
        """ScheduleConfig applies default values."""
        sc = ScheduleConfig()
        assert sc.poll_interval_minutes == 30
        assert sc.misfire_grace_time == 300

    def test_schedule_config_negative_poll_interval_raises(self):
        """Negative or zero poll_interval_minutes raises ValidationError."""
        with pytest.raises(ValidationError):
            ScheduleConfig(poll_interval_minutes=0)

        with pytest.raises(ValidationError):
            ScheduleConfig(poll_interval_minutes=-5)

    def test_schedule_config_positive_interval(self):
        """Valid positive poll_interval_minutes is accepted."""
        sc = ScheduleConfig(poll_interval_minutes=15)
        assert sc.poll_interval_minutes == 15


class TestAppSettingsLoading:
    def test_app_settings_loads_from_yaml(self, tmp_config_file):
        """AppSettings loads channels, download, and schedule from a YAML file."""
        settings = AppSettings(_yaml_file=str(tmp_config_file))
        assert len(settings.channels) == 1
        assert settings.channels[0].channel_id == "UCtest123"
        assert settings.channels[0].name == "Test Channel"
        assert settings.download.output_dir == "/tmp/downloads"
        assert settings.download.max_duration == 180
        assert settings.schedule.poll_interval_minutes == 30

    def test_app_settings_defaults_when_fields_omitted(self, tmp_path):
        """AppSettings uses defaults when optional YAML fields are omitted."""
        minimal_yaml = """
channels:
  - channel_id: "UCminimal"
"""
        config_path = tmp_path / "minimal.yaml"
        config_path.write_text(minimal_yaml)

        settings = AppSettings(_yaml_file=str(config_path))
        assert settings.download.max_duration == 180
        assert settings.schedule.poll_interval_minutes == 30
        assert settings.log_level == "INFO"

    def test_app_settings_database_url_default(self, tmp_config_file):
        """AppSettings default database_url is SQLite."""
        settings = AppSettings(_yaml_file=str(tmp_config_file))
        assert "sqlite" in settings.database_url

    def test_get_max_duration_uses_channel_override(self, tmp_config_file):
        """get_max_duration returns channel-specific max_duration if set."""
        settings = AppSettings(_yaml_file=str(tmp_config_file))
        channel_with_override = ChannelConfig(channel_id="UCx", max_duration=60)
        assert settings.get_max_duration(channel_with_override) == 60

    def test_get_max_duration_falls_back_to_global(self, tmp_config_file):
        """get_max_duration returns global max_duration when channel has no override."""
        settings = AppSettings(_yaml_file=str(tmp_config_file))
        channel_no_override = ChannelConfig(channel_id="UCx")
        assert settings.get_max_duration(channel_no_override) == settings.download.max_duration

    def test_invalid_yaml_poll_interval_raises(self, tmp_path):
        """Negative poll_interval_minutes in YAML raises ValidationError."""
        bad_yaml = """
channels:
  - channel_id: "UCtest"
schedule:
  poll_interval_minutes: -1
"""
        config_path = tmp_path / "bad.yaml"
        config_path.write_text(bad_yaml)

        with pytest.raises((ValidationError, Exception)):
            AppSettings(_yaml_file=str(config_path))


class TestProcessingConfig:
    def test_processing_config_defaults(self):
        """ProcessingConfig has correct default values."""
        pc = ProcessingConfig()
        assert pc.asr_model == "medium"
        assert pc.output_dir == "./processed"

    def test_processing_config_api_key_fields(self):
        """ProcessingConfig exposes deepl_auth_key, anthropic_api_key, font_path."""
        pc = ProcessingConfig()
        assert pc.deepl_auth_key == ""
        assert pc.anthropic_api_key == ""
        assert pc.font_path == "src/crosspost/assets/fonts/NotoSansCJKsc-Bold.otf"

    def test_processing_config_max_retries(self):
        """ProcessingConfig has max_retries defaulting to 2."""
        pc = ProcessingConfig()
        assert pc.max_retries == 2

    def test_processing_config_custom_values(self):
        """ProcessingConfig accepts custom values."""
        pc = ProcessingConfig(asr_model="large-v3", output_dir="/custom", max_retries=3)
        assert pc.asr_model == "large-v3"
        assert pc.output_dir == "/custom"
        assert pc.max_retries == 3

    def test_app_settings_includes_processing(self):
        """AppSettings includes a processing field with ProcessingConfig."""
        settings = AppSettings()
        assert hasattr(settings, "processing")
        assert isinstance(settings.processing, ProcessingConfig)
        assert settings.processing.asr_model == "medium"
