"""
Tests for bb/config.py

Success criteria:
- load_config() returns defaults when no file exists
- save_config() creates BB_DIR if missing, writes valid TOML
- save → load roundtrip is lossless
- Pydantic rejects invalid field values with ValidationError
"""
import tomllib
from unittest.mock import patch

import pytest
from pydantic import ValidationError


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


def test_load_returns_defaults_when_no_file_exists(tmp_path):
    """load_config() returns BBConfig with default values when config.toml is absent."""
    with patch("bb.config.BB_DIR", tmp_path):
        from bb.config import load_config

        cfg = load_config()

    assert cfg.lms_type == "blackboard_ultra"
    assert cfg.lms_url == "https://learn.senecapolytechnic.ca"
    assert cfg.notification.provider == "terminal"
    assert cfg.sync_interval_hours == 4


def test_load_returns_defaults_for_empty_notification_fields(tmp_path):
    """Notification sub-model defaults: all secret fields are empty strings."""
    with patch("bb.config.BB_DIR", tmp_path):
        from bb.config import load_config

        cfg = load_config()

    assert cfg.notification.ntfy_topic == ""
    assert cfg.notification.telegram_token == ""
    assert cfg.notification.telegram_chat_id == ""
    assert cfg.notification.discord_webhook == ""


# ---------------------------------------------------------------------------
# save_config
# ---------------------------------------------------------------------------


def test_save_creates_bb_dir_when_not_exists(tmp_path):
    """save_config() creates BB_DIR (and any parents) if the directory is absent."""
    missing_dir = tmp_path / "deep" / "bb"

    with patch("bb.config.BB_DIR", missing_dir):
        from bb.config import BBConfig, save_config

        save_config(BBConfig())

    assert missing_dir.exists()
    assert (missing_dir / "config.toml").exists()


def test_save_writes_valid_toml(tmp_path):
    """config.toml written by save_config() is readable by stdlib tomllib."""
    with patch("bb.config.BB_DIR", tmp_path):
        from bb.config import BBConfig, save_config

        save_config(BBConfig())

    with open(tmp_path / "config.toml", "rb") as f:
        data = tomllib.load(f)

    assert data["lms_type"] == "blackboard_ultra"
    assert data["lms_url"] == "https://learn.senecapolytechnic.ca"


def test_save_then_load_roundtrip_preserves_all_fields(tmp_path):
    """Saving a custom BBConfig then loading it returns an identical model."""
    with patch("bb.config.BB_DIR", tmp_path):
        from bb.config import BBConfig, NotificationConfig, load_config, save_config

        original = BBConfig(
            lms_url="https://custom.example.com",
            sync_interval_hours=2,
            notification=NotificationConfig(
                provider="terminal",
                ntfy_topic="my-topic",
            ),
        )
        save_config(original)
        loaded = load_config()

    assert loaded == original


def test_save_overwrites_existing_config(tmp_path):
    """Calling save_config() twice replaces the previous file cleanly."""
    with patch("bb.config.BB_DIR", tmp_path):
        from bb.config import BBConfig, load_config, save_config

        save_config(BBConfig(lms_url="https://first.example.com"))
        save_config(BBConfig(lms_url="https://second.example.com"))
        loaded = load_config()

    assert loaded.lms_url == "https://second.example.com"


# ---------------------------------------------------------------------------
# Pydantic validation
# ---------------------------------------------------------------------------


def test_invalid_lms_type_raises_validation_error():
    """BBConfig rejects unknown lms_type values."""
    from bb.config import BBConfig

    with pytest.raises(ValidationError):
        BBConfig(lms_type="canvas")


def test_invalid_notification_provider_raises_validation_error():
    """NotificationConfig rejects unknown provider values."""
    from bb.config import NotificationConfig

    with pytest.raises(ValidationError):
        NotificationConfig(provider="pushover")
