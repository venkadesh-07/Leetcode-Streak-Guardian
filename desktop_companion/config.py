"""
Local configuration manager for LeetCode Streak Guardian Desktop Companion.
Persists user settings safely in %APPDATA%/LeetCodeStreakGuardian/config.json
"""

import json
import os
from pathlib import Path

APP_NAME = "LeetCodeStreakGuardian"


def get_app_data_dir() -> Path:
    """Return the platform-appropriate application data directory."""
    if os.name == "nt":
        base_dir = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    else:
        base_dir = str(Path.home() / ".config")
    app_dir = Path(base_dir) / APP_NAME
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_config_path() -> Path:
    return get_app_data_dir() / "config.json"


def load_config() -> dict:
    """Load configuration from disk with safe defaults."""
    default_config = {
        "server_url": "http://127.0.0.1:5000",
        "api_token": "",
        "check_interval_hours": 2,
        "run_on_startup": True,
        "last_notified_date_utc": "",
        "last_notified_ts": 0,
    }
    path = get_config_path()
    if not path.exists():
        save_config(default_config)
        return default_config

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            default_config.update(data)
            return default_config
    except Exception:
        return default_config


def save_config(config: dict) -> None:
    """Save configuration to disk."""
    path = get_config_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except Exception as e:
        print(f"Error saving config: {e}")
