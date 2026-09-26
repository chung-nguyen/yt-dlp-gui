"""Run yt-dlp off the UI thread, then recode when the car HUD preset needs it."""

from __future__ import annotations

import json
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from ytdlp_gui.ffmpeg_util import (
    ffprobe_path,
    hidden_subprocess_kwargs,
    is_hud_compatible,
    probe_media,
)
from ytdlp_gui.options import DownloadPlan, normalize_filename


@dataclass
class UiMessage:
    kind: str
    text: str = ""
    percent: float | None = None
    ok: bool | None = None


class QueueLogger:
    """Forward yt-dlp log lines. Debug dumps stay out of the console."""

    def __init__(self, emit) -> None:
        self._emit = emit

    def debug(self, message) -> None:
        text = str(message).rstrip()
        if not text or text.startswith("[debug]"):
            return
        self._emit(text)

    def info(self, message) -> None:
        text = str(message).rstrip()
        if text:
            self._emit(text)

    def warning(self, message) -> None:
        text = str(message).rstrip()
        if text:
            self._emit(f"WARNING: {text}")

    def error(self, message) -> None:
        text = str(message).rstrip()
        if text:
            self._emit(f"ERROR: {text}")


def run_download(plan: DownloadPlan, emit, cancel: threading.Event) -> None:
    """Download plan.urls. emit receives UiMessage. cancel aborts the job."""
    emit(UiMessage("log", plan.command_preview))
    emit(UiMessage("log", "Options:\n" + json.dumps(_public_opts(plan.ydl_opts), indent=2)))
    if not plan.urls:
        emit(UiMessage("log", "ERROR: No URL to download."))
        emit(UiMessage("done", "No URL to download.", ok=False))
        return

    try:
        Path(plan.output_dir).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        emit(UiMessage("log", f"ERROR: Could not create the output folder: {exc}"))
        emit(UiMessage("done", str(exc), ok=False))
        return

    if plan.hud_recode and not plan.ydl_opts.get("ffmpeg_location"):
        emit(
            UiMessage(
                "log",
                "WARNING: ffmpeg was not found. Downloading a compatible stream "
                "without recoding.",
            )
        )

    downloaded: dict[str, str] = {}
    processed: dict[str, str] = {}
    holder: dict = {}

    def emit_log(text: str) -> None:
        emit(UiMessage("log", text))

    def stop_if_cancelled() -> None:
        if not cancel.is_set():
            return
        ydl = holder.get("ydl")
        if ydl is not None:
            ydl._download_retcode = 1
        raise DownloadError("Download cancelled")

    def on_progress(data: dict) -> None:
        stop_if_cancelled()
        status = data.get("status")
        if status == "downloading":
            percent, text = _progress_text(data)
            emit(UiMessage("progress", text, percent))
        elif status == "finished":
            _remember(downloaded, data.get("info_dict"), data.get("filename"))
            name = Path(str(data.get("filename") or "")).name
            emit(UiMessage("progress", f"Downloaded {name}".strip(), 1.0))

    def on_postprocessor(data: dict) -> None:
        stop_if_cancelled()
        if data.get("status") != "finished":
            return
        _remember(processed, data.get("info_dict"), None)
        name = data.get("postprocessor") or "post-process"
        emit(UiMessage("log", f"{name} finished"))

    options = dict(plan.ydl_opts)
    options["logger"] = QueueLogger(emit_log)
    options["progress_hooks"] = [on_progress]
    options["postprocessor_hooks"] = [on_postprocessor]

    try:
        with YoutubeDL(options) as ydl:
            holder["ydl"] = ydl
            ydl.download(plan.urls)
        if cancel.is_set():
            emit(UiMessage("log", "Cancelled."))
            emit(UiMessage("done", "Cancelled", ok=False))
            return
        chosen = processed.values() if processed else downloaded.values()
        written: list[str] = []
        for raw in _unique(chosen):
            path = Path(raw)
            if not path.is_file():
                continue
            if plan.hud_recode:
                path = _ensure_hud(plan, path, emit, cancel)
            if plan.normalize_filenames:
                path = _normalize_saved(path, emit)
            written.append(str(path))
        if written:
            emit(UiMessage("log", "Saved:\n" + "\n".join(written)))
        else:
            emit(UiMessage("log", "Finished."))
        emit(UiMessage("done", "Finished", ok=True))
    except DownloadError as exc:
        if cancel.is_set() or "cancelled" in str(exc).lower():
            emit(UiMessage("log", "Cancelled."))
            emit(UiMessage("done", "Cancelled", ok=False))
            return
        emit(UiMessage("log", f"ERROR: {exc}"))
        emit(UiMessage("done", str(exc), ok=False))
    except Exception as exc:
        emit(UiMessage("log", f"ERROR: {exc}"))
        emit(UiMessage("done", str(exc), ok=False))


def _ensure_hud(plan: DownloadPlan, source: Path, emit, cancel: threading.Event) -> Path:
    ffmpeg_dir = plan.ydl_opts.get("ffmpeg_location")
    ffmpeg_bin = _ffmpeg_binary(ffmpeg_dir)
    probe_bin = ffprobe_path(ffmpeg_dir)
    if not ffmpeg_bin or not probe_bin:
        emit(UiMessage("log", f"WARNING: ffmpeg not found. Kept {source.name}."))
        return source

    info = probe_media(probe_bin, source)
    if info is None:
        emit(UiMessage("log", f"WARNING: could not probe {source.name}. Left it unchanged."))
        return source
    if is_hud_compatible(info, plan.max_height):
        emit(UiMessage("log", f"Already H.264 + AAC MP4: {source.name}"))
        return source

    dest = source.with_suffix(".mp4")
    tmp = source.with_name(source.stem + ".hud-tmp.mp4")
    log_path = source.with_name(source.stem + ".hud-tmp.log")
    command = [ffmpeg_bin, "-y", "-i", str(source), *plan.recode_args, str(tmp)]
    emit(UiMessage("log", "Recoding for car HUD:\n" + " ".join(command)))
    emit(UiMessage("progress", "Recoding for car HUD...", None))
    try:
        with log_path.open("w", encoding="utf-8", errors="replace") as log_file:
            proc = subprocess.Popen(
                command,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                **hidden_subprocess_kwargs(),
            )
            while proc.poll() is None:
                if cancel.is_set():
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    tmp.unlink(missing_ok=True)
                    raise DownloadError("Download cancelled")
                time.sleep(0.2)
        if proc.returncode != 0:
            tail = _tail(log_path)
            emit(UiMessage("log", f"ERROR: HUD recode failed for {source.name}\n{tail}"))
            tmp.unlink(missing_ok=True)
            return source
        tmp.replace(dest)
        if source.resolve() != dest.resolve() and source.exists():
            source.unlink()
    finally:
        log_path.unlink(missing_ok=True)
    emit(UiMessage("log", f"Recoded {dest.name}"))
    return dest


def normalize_downloaded_file(source: Path) -> Path:
    """Rename source to its normalized name. Returns the file's new path."""
    dest_name = normalize_filename(source.name)
    if dest_name == source.name:
        return source
    dest = _available_path(source, source.with_name(dest_name))
    if _same_file(source, dest):
        bridge = _available_path(source, source.with_name(f"{source.stem}.rename-tmp{source.suffix}"))
        source.rename(bridge)
        bridge.rename(dest)
        return dest
    source.rename(dest)
    return dest


def _normalize_saved(path: Path, emit) -> Path:
    try:
        renamed = normalize_downloaded_file(path)
    except OSError as exc:
        emit(UiMessage("log", f"WARNING: Could not rename {path.name}: {exc}"))
        return path
    if renamed.name != path.name:
        emit(UiMessage("log", f"Renamed {path.name} -> {renamed.name}"))
    return renamed


def _available_path(source: Path, dest: Path) -> Path:
    if not dest.exists() or _same_file(source, dest):
        return dest
    number = 2
    while True:
        candidate = dest.with_name(f"{dest.stem} {number}{dest.suffix}")
        if not candidate.exists() or _same_file(source, candidate):
            return candidate
        number += 1


def _same_file(left: Path, right: Path) -> bool:
    if not left.exists() or not right.exists():
        return False
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return False


def _ffmpeg_binary(ffmpeg_dir: str | None) -> str | None:
    if not ffmpeg_dir:
        return None
    directory = Path(ffmpeg_dir)
    for name in ("ffmpeg.exe", "ffmpeg"):
        candidate = directory / name
        if candidate.is_file():
            return str(candidate)
    if directory.is_file() and directory.name.lower() in {"ffmpeg", "ffmpeg.exe"}:
        return str(directory)
    return None


def _remember(store: dict[str, str], info, fallback) -> None:
    info = info or {}
    path = info.get("filepath") or fallback
    if not path:
        return
    key = str(info.get("id") or path)
    store[key] = str(path)


def _unique(paths) -> list[str]:
    seen: list[str] = []
    for path in paths:
        if path not in seen:
            seen.append(path)
    return seen


def _progress_text(data: dict) -> tuple[float | None, str]:
    downloaded = data.get("downloaded_bytes") or 0
    total = data.get("total_bytes") or data.get("total_bytes_estimate") or 0
    percent = (downloaded / total) if total else None
    percent_text = str(data.get("_percent_str") or "").strip()
    if not percent_text:
        percent_text = "?" if percent is None else f"{percent * 100:.1f}%"
    parts = [percent_text]
    speed = str(data.get("_speed_str") or "").strip()
    eta = str(data.get("_eta_str") or "").strip()
    if speed:
        parts.append(speed)
    if eta:
        parts.append(f"ETA {eta}")
    return percent, " · ".join(parts)


def _public_opts(options: dict) -> dict:
    hidden = {"logger", "progress_hooks", "postprocessor_hooks"}
    public = {}
    for key, value in options.items():
        if key in hidden:
            continue
        public[key] = list(value) if isinstance(value, tuple) else value
    return public


def _tail(path: Path, limit: int = 2000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[-limit:]
