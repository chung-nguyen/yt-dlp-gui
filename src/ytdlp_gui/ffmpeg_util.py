"""Locate ffmpeg/ffprobe and decide whether a file already matches the HUD."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Used only when ffmpeg is not on PATH and not installed beside the app.
_EXTRA_CANDIDATES = [Path(r"F:\tools\ffmpeg-8.1-full_build\bin")]


def install_dir() -> Path:
    """Folder the app is installed in.

    Frozen builds use the directory that contains the executable. A source
    checkout uses the repository root.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    here = Path(__file__).resolve()
    checkout = here.parents[2]
    if (checkout / "pyproject.toml").is_file():
        return checkout
    return Path(sys.executable).resolve().parent


def bundled_ffmpeg_dirs() -> list[Path]:
    """ffmpeg folder downloaded next to the app, then its bin directory."""
    root = install_dir() / "ffmpeg"
    return [root, root / "bin"]


def find_ffmpeg(explicit: str | None = None) -> str | None:
    """Return the directory that contains ffmpeg, or None."""
    if explicit:
        found = _as_ffmpeg_dir(explicit)
        if found:
            return found
    for candidate in bundled_ffmpeg_dirs():
        if _dir_has_ffmpeg(candidate):
            return str(candidate)
    which = shutil.which("ffmpeg")
    if which:
        return str(Path(which).resolve().parent)
    for candidate in _EXTRA_CANDIDATES:
        if _dir_has_ffmpeg(candidate):
            return str(candidate)
    return None


def ffprobe_path(ffmpeg_dir: str | None) -> str | None:
    if ffmpeg_dir:
        for name in ("ffprobe.exe", "ffprobe"):
            candidate = Path(ffmpeg_dir) / name
            if candidate.is_file():
                return str(candidate)
    return shutil.which("ffprobe")


def probe_media(ffprobe: str, media: Path) -> dict | None:
    command = [
        ffprobe,
        "-hide_banner",
        "-v",
        "error",
        "-show_entries",
        "format=format_name",
        "-show_entries",
        "stream=codec_type,codec_name,pix_fmt,height,profile",
        "-of",
        "json",
        str(media),
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **hidden_subprocess_kwargs(),
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def is_hud_compatible(info: dict, max_height: int | None) -> bool:
    """True when the file is already H.264 + AAC in MP4 and within the cap.

    Profile and sample rate are not required to match the sample. A 10-bit
    picture or a taller frame is recoded, because car HUDs usually reject both.
    """
    format_name = str((info.get("format") or {}).get("format_name") or "")
    if not _is_mp4_container(format_name):
        return False
    streams = info.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    if not video or not audio:
        return False
    if video.get("codec_name") != "h264" or audio.get("codec_name") != "aac":
        return False
    pix_fmt = video.get("pix_fmt")
    if pix_fmt and pix_fmt != "yuv420p":
        return False
    height = video.get("height")
    if max_height is not None and isinstance(height, int) and height > max_height:
        return False
    return True


def _is_mp4_container(format_name: str) -> bool:
    names = {part.strip() for part in format_name.split(",")}
    return "mp4" in names or "mov" in names


def _dir_has_ffmpeg(path: Path) -> bool:
    return (path / "ffmpeg.exe").is_file() or (path / "ffmpeg").is_file()


def _as_ffmpeg_dir(value: str) -> str | None:
    path = Path(value).expanduser()
    if path.is_dir() and _dir_has_ffmpeg(path):
        return str(path)
    if path.is_file() and path.name.lower() in {"ffmpeg", "ffmpeg.exe"}:
        return str(path.parent)
    return None


def hidden_subprocess_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}
