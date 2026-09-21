"""Remember the last folder, ffmpeg path, and form options."""

from __future__ import annotations

import json
from pathlib import Path

from ytdlp_gui.options import FORMAT_HUD, PLAYLIST_VIDEO, PRESET_CAR_HUD

SETTINGS_DIR = Path.home() / ".yt-dlp-gui"
SETTINGS_PATH = SETTINGS_DIR / "settings.json"

PREFERRED_OUTPUT = Path(r"D:\Downloads\done")


def default_output_dir(
    preferred: Path | None = None,
    fallback: Path | None = None,
) -> str:
    preferred = PREFERRED_OUTPUT if preferred is None else preferred
    if preferred.is_dir():
        return str(preferred)
    fallback = Path.home() / "Downloads" if fallback is None else fallback
    return str(fallback)


def default_settings() -> dict:
    return {
        "output_dir": default_output_dir(),
        "ffmpeg_location": "",
        "preset": PRESET_CAR_HUD,
        "quality": "480p",
        "container": FORMAT_HUD,
        "playlist": PLAYLIST_VIDEO,
        "cookies_browser": "None",
        "overwrite": False,
        "resume": True,
    }


def load_settings(path: Path | None = None) -> dict:
    path = SETTINGS_PATH if path is None else path
    settings = default_settings()
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return settings
    if isinstance(saved, dict):
        settings.update({key: saved[key] for key in settings if key in saved})
    return settings


def save_settings(settings: dict, path: Path | None = None) -> None:
    path = SETTINGS_PATH if path is None else path
    path.parent.mkdir(parents=True, exist_ok=True)
    stored = default_settings()
    stored.update({key: settings[key] for key in stored if key in settings})
    path.write_text(json.dumps(stored, indent=2), encoding="utf-8")
