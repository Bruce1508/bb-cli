from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

import tomli_w
from pydantic import BaseModel

BB_DIR = Path.home() / ".bb"


class NotificationConfig(BaseModel):
    provider: Literal["terminal", "ntfy", "telegram", "discord"] = "terminal"
    ntfy_topic: str = ""
    telegram_token: str = ""  # plaintext — moves to keyring Day 4
    telegram_chat_id: str = ""
    discord_webhook: str = ""  # plaintext — moves to keyring Day 4


class BBConfig(BaseModel):
    lms_type: Literal["blackboard_ultra"] = "blackboard_ultra"
    lms_url: str = "https://learn.senecapolytechnic.ca"
    ical_url: str | None = None  # saved automatically after first bb import-ical run
    notification: NotificationConfig = NotificationConfig()
    sync_interval_hours: int = 4  # used by bb auto-setup (Day 7)


def load_config() -> BBConfig:
    """Return config from ~/.bb/config.toml, or defaults if file not found."""
    config_path = BB_DIR / "config.toml"
    if not config_path.exists():
        return BBConfig()
    with config_path.open("rb") as f:
        data = tomllib.load(f)
    return BBConfig.model_validate(data)


def save_config(cfg: BBConfig) -> None:
    """Write config to ~/.bb/config.toml, creating the directory if needed."""
    BB_DIR.mkdir(parents=True, exist_ok=True)
    config_path = BB_DIR / "config.toml"
    with config_path.open("wb") as f:
        # exclude_none=True: TOML has no null type; omit optional fields when unset
        tomli_w.dump(cfg.model_dump(exclude_none=True), f)
