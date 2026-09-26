"""Map the form to yt-dlp options and a command preview."""

from __future__ import annotations

import shlex
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

PRESET_CAR_HUD = "Car HUD XL7"
PRESET_BEST = "Best quality"
PRESET_1080_MP4 = "1080p MP4 remux"
PRESET_AUDIO_MP3 = "Audio MP3"
PRESETS = [PRESET_CAR_HUD, PRESET_BEST, PRESET_1080_MP4, PRESET_AUDIO_MP3]

QUALITIES = ["Best", "1080p", "720p", "480p", "360p"]
QUALITY_HEIGHT = {
    "Best": None,
    "1080p": 1080,
    "720p": 720,
    "480p": 480,
    "360p": 360,
}

FORMAT_HUD = "MP4 (HUD / H.264+AAC)"
FORMAT_MP4 = "MP4 remux only"
FORMAT_MKV = "MKV"
FORMAT_WEBM = "WebM"
FORMAT_MP3 = "MP3"
FORMAT_M4A = "M4A"
FORMATS = [FORMAT_HUD, FORMAT_MP4, FORMAT_MKV, FORMAT_WEBM, FORMAT_MP3, FORMAT_M4A]

PLAYLIST_VIDEO = "This video only"
PLAYLIST_ALL = "Whole playlist"
PLAYLISTS = [PLAYLIST_VIDEO, PLAYLIST_ALL]

BROWSERS = ["None", "Chrome", "Edge", "Firefox"]
BROWSER_IDS = {
    "Chrome": "chrome",
    "Edge": "edge",
    "Firefox": "firefox",
}

AUDIO_BITRATE = "192"


@dataclass
class DownloadRequest:
    urls: list[str]
    output_dir: str
    preset: str = PRESET_CAR_HUD
    quality: str = "480p"
    container: str = FORMAT_HUD
    playlist: str = PLAYLIST_VIDEO
    cookies_browser: str = "None"
    overwrite: bool = False
    resume: bool = True
    normalize_filenames: bool = True
    ffmpeg_location: str | None = None


@dataclass
class DownloadPlan:
    ydl_opts: dict
    urls: list[str]
    command_preview: str
    hud_recode: bool
    max_height: int | None
    output_dir: str
    normalize_filenames: bool = True
    recode_args: list[str] = field(default_factory=list)


def parse_urls(text: str) -> list[str]:
    urls: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            urls.append(line)
    return urls


def quality_height(quality: str) -> int | None:
    if quality not in QUALITY_HEIGHT:
        raise ValueError(f"Unknown quality: {quality}")
    return QUALITY_HEIGHT[quality]


def hud_recode_args(max_height: int | None) -> list[str]:
    """ffmpeg args that match the XL7 HUD sample: H.264 Main, yuv420p, AAC-LC stereo."""
    args = [
        "-c:v",
        "libx264",
        "-profile:v",
        "main",
        "-pix_fmt",
        "yuv420p",
    ]
    if max_height is not None:
        # Quotes are for the ffmpeg filter parser (the comma), not the shell.
        args.extend(["-vf", f"scale=-2:'min({max_height},ih)'"])
    args.extend(
        [
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ac",
            "2",
            "-ar",
            "44100",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
        ]
    )
    return args


def preset_defaults(preset: str) -> tuple[str, str]:
    """Quality and container a preset selects. The form can override them after."""
    if preset == PRESET_CAR_HUD:
        return "480p", FORMAT_HUD
    if preset == PRESET_BEST:
        return "Best", FORMAT_MP4
    if preset == PRESET_1080_MP4:
        return "1080p", FORMAT_MP4
    if preset == PRESET_AUDIO_MP3:
        return "Best", FORMAT_MP3
    raise ValueError(f"Unknown preset: {preset}")


def build_plan(request: DownloadRequest) -> DownloadPlan:
    if request.container not in FORMATS:
        raise ValueError(f"Unknown format: {request.container}")
    if request.playlist not in PLAYLISTS:
        raise ValueError(f"Unknown playlist mode: {request.playlist}")

    height = quality_height(request.quality)
    output_dir = str(Path(request.output_dir).expanduser()) if request.output_dir else ""
    hud_recode = request.container == FORMAT_HUD
    ydl_opts: dict = {
        "paths": {"home": output_dir},
        "outtmpl": {"default": "%(title)s.%(ext)s"},
        "noplaylist": request.playlist == PLAYLIST_VIDEO,
        "continuedl": request.resume,
        "overwrites": request.overwrite,
        "restrictfilenames": False,
        "windowsfilenames": _windows(),
        "noprogress": True,
        "quiet": False,
    }
    if request.ffmpeg_location:
        ydl_opts["ffmpeg_location"] = request.ffmpeg_location

    browser = BROWSER_IDS.get(request.cookies_browser)
    if browser:
        ydl_opts["cookiesfrombrowser"] = (browser,)

    if request.container in (FORMAT_MP3, FORMAT_M4A):
        codec = "mp3" if request.container == FORMAT_MP3 else "m4a"
        ydl_opts["format"] = "ba/b"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": codec,
                "preferredquality": AUDIO_BITRATE,
            }
        ]
        height = None
        hud_recode = False
    elif request.container == FORMAT_HUD:
        ydl_opts["format"] = _hud_format(height)
        ydl_opts["merge_output_format"] = "mp4"
        sort = ["vcodec:h264", "acodec:aac"]
        if height is not None:
            sort.insert(0, f"res:{height}")
        ydl_opts["format_sort"] = sort
    elif request.container == FORMAT_MP4:
        ydl_opts["format"] = _capped_format(height)
        ydl_opts["merge_output_format"] = "mp4"
    elif request.container == FORMAT_MKV:
        ydl_opts["format"] = _capped_format(height)
        ydl_opts["merge_output_format"] = "mkv"
    elif request.container == FORMAT_WEBM:
        ydl_opts["format"] = _capped_format(height, video_ext="webm", audio_ext="webm")
        ydl_opts["merge_output_format"] = "webm"

    recode_args = hud_recode_args(height) if hud_recode else []
    plan = DownloadPlan(
        ydl_opts=ydl_opts,
        urls=list(request.urls),
        command_preview="",
        hud_recode=hud_recode,
        max_height=height,
        output_dir=output_dir,
        normalize_filenames=request.normalize_filenames,
        recode_args=recode_args,
    )
    plan.command_preview = command_preview(plan)
    return plan


def command_preview(plan: DownloadPlan) -> str:
    opts = plan.ydl_opts
    parts = ["yt-dlp"]
    if opts.get("format"):
        parts.extend(["-f", opts["format"]])
    if opts.get("format_sort"):
        parts.extend(["-S", ",".join(opts["format_sort"])])
    if opts.get("merge_output_format"):
        parts.extend(["--merge-output-format", opts["merge_output_format"]])
    for processor in opts.get("postprocessors") or []:
        if processor.get("key") == "FFmpegExtractAudio":
            parts.extend(["-x", "--audio-format", processor["preferredcodec"]])
            quality = processor.get("preferredquality")
            if quality:
                parts.extend(["--audio-quality", f"{quality}K"])
    home = (opts.get("paths") or {}).get("home")
    if home:
        parts.extend(["-P", home])
    outtmpl = opts.get("outtmpl")
    if isinstance(outtmpl, dict):
        outtmpl = outtmpl.get("default")
    if outtmpl:
        parts.extend(["-o", outtmpl])
    parts.append("--no-playlist" if opts.get("noplaylist") else "--yes-playlist")
    if opts.get("overwrites"):
        parts.append("--force-overwrites")
    parts.append("--continue" if opts.get("continuedl", True) else "--no-continue")
    browser = opts.get("cookiesfrombrowser")
    if browser:
        parts.extend(["--cookies-from-browser", browser[0]])
    if opts.get("ffmpeg_location"):
        parts.extend(["--ffmpeg-location", opts["ffmpeg_location"]])
    parts.extend(plan.urls or ["URL"])
    line = " ".join(_quote(part) for part in parts)
    if plan.hud_recode:
        recode = " ".join(plan.recode_args)
        line += (
            "\n# If the file is not H.264 + AAC in MP4, recode with:\n"
            f"# ffmpeg -y -i INPUT {recode} OUTPUT.mp4"
        )
    if plan.normalize_filenames:
        line += "\n# Then rename the file: drop diacritics and symbols"
    return line


# Letters that do not decompose under NFKD, but should still lose their mark.
_LETTER_FIXES = str.maketrans(
    {
        "Đ": "D",
        "đ": "d",
        "Ł": "L",
        "ł": "l",
        "Ø": "O",
        "ø": "o",
        "Æ": "AE",
        "æ": "ae",
        "Œ": "OE",
        "œ": "oe",
        "ß": "ss",
        "Þ": "Th",
        "þ": "th",
        "Ð": "D",
        "ð": "d",
        "ı": "i",
    }
)
# Apostrophes sit inside words. Drop them instead of splitting the word.
_APOSTROPHES = frozenset("'’ʼ`´")
_WINDOWS_RESERVED = frozenset(
    {"con", "prn", "aux", "nul", *(f"com{n}" for n in range(1, 10)), *(f"lpt{n}" for n in range(1, 10))}
)


def normalize_filename(name: str) -> str:
    """Keep letters, numbers, and spaces. Drop diacritics and symbols."""
    suffix = Path(name).suffix
    stem = name[: -len(suffix)] if suffix else name
    cleaned = _normalize_stem(stem)
    if not cleaned or cleaned.casefold() in _WINDOWS_RESERVED:
        cleaned = f"{cleaned} file".strip() if cleaned else "download"
    return f"{cleaned}{suffix}"


def _normalize_stem(stem: str) -> str:
    text = unicodedata.normalize("NFKD", stem.translate(_LETTER_FIXES))
    pieces: list[str] = []
    for char in text:
        if unicodedata.combining(char) or char in _APOSTROPHES:
            continue
        category = unicodedata.category(char)
        if category.startswith(("L", "N")):
            pieces.append(char)
        else:
            pieces.append(" ")
    cleaned = " ".join("".join(pieces).split()).strip(" .")
    if len(cleaned) > 180:
        cleaned = cleaned[:180].rstrip(" .")
    return cleaned


def _hud_format(height: int | None) -> str:
    limit = f"[height<={height}]" if height is not None else ""
    return (
        f"bv*[vcodec^=avc]{limit}+ba[acodec^=mp4a]"
        f"/b[ext=mp4]{limit}"
        f"/bv*{limit}+ba/b"
    )


def _capped_format(
    height: int | None,
    video_ext: str | None = None,
    audio_ext: str | None = None,
) -> str:
    limit = f"[height<={height}]" if height is not None else ""
    vext = f"[ext={video_ext}]" if video_ext else ""
    aext = f"[ext={audio_ext}]" if audio_ext else ""
    if video_ext:
        return f"bv*{vext}{limit}+ba{aext}/b{vext}{limit}/bv*{limit}+ba/b"
    if height is None:
        return "bv*+ba/b"
    return f"bv*{limit}+ba/b{limit}"


def _windows() -> bool:
    import os

    return os.name == "nt"


def _quote(value: str) -> str:
    if value.startswith("#"):
        return value
    return shlex.quote(value)
