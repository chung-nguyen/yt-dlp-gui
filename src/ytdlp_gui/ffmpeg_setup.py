"""Download the latest ffmpeg release into a folder beside the app."""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import tarfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable, Protocol

USER_AGENT = "yt-dlp-gui"
RELEASE_API = "https://api.github.com/repos/yt-dlp/FFmpeg-Builds/releases/latest"
MACOS_FFMPEG = "https://evermeet.cx/ffmpeg/getrelease/zip"
MACOS_FFPROBE = "https://evermeet.cx/ffprobe/getrelease/zip"

Progress = Callable[[str, float | None], None]
Cancelled = Callable[[], bool]


class FfmpegDownloadError(Exception):
    """The ffmpeg release could not be installed."""


class FfmpegDownloadCancelled(FfmpegDownloadError):
    """The user cancelled the ffmpeg download."""


class ReleaseSource(Protocol):
    def latest_assets(self) -> list[tuple[str, str]]:
        """Return (file name, download URL) pairs for the latest release."""

    def download(self, url: str, dest: Path, report: Progress, cancelled: Cancelled) -> None:
        """Save url to dest, reporting progress and honouring cancellation."""


def github_asset_name(system: str, machine: str) -> str:
    """Static GPL archive published by yt-dlp's FFmpeg builds for this machine."""
    os_name = system.lower()
    cpu = machine.lower().replace("_", "")
    if os_name == "windows":
        if cpu in {"arm64", "aarch64"}:
            arch = "winarm64"
        elif cpu in {"x86", "i386", "i686"}:
            arch = "win32"
        else:
            arch = "win64"
        return f"ffmpeg-master-latest-{arch}-gpl.zip"
    if os_name == "linux":
        if cpu in {"arm64", "aarch64"}:
            arch = "linuxarm64"
        elif cpu in {"x8664", "amd64"}:
            arch = "linux64"
        else:
            raise FfmpegDownloadError(f"No ffmpeg build is published for Linux {machine}.")
        return f"ffmpeg-master-latest-{arch}-gpl.tar.xz"
    raise FfmpegDownloadError(f"No ffmpeg build is published for {system} {machine}.")


def download_latest_ffmpeg(
    install_root: Path,
    *,
    report: Progress | None = None,
    cancelled: Cancelled | None = None,
    system: str | None = None,
    machine: str | None = None,
    source: ReleaseSource | None = None,
) -> Path:
    """Install the latest ffmpeg into install_root/ffmpeg and return that folder."""
    report = report or (lambda _message, _percent: None)
    cancelled = cancelled or (lambda: False)
    system = platform.system() if system is None else system
    machine = platform.machine() if machine is None else machine
    source = UrllibReleaseSource() if source is None else source
    work = install_root / ".ffmpeg-download"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    try:
        _check_cancelled(cancelled)
        archives = _download_archives(work, system, machine, source, report, cancelled)
        _check_cancelled(cancelled)
        tree = work / "tree"
        tree.mkdir()
        report("Extracting ffmpeg", 1.0)
        for archive in archives:
            _extract(archive, tree)
        staged = work / "staged"
        _stage_binaries(tree, staged)
        _check_cancelled(cancelled)
        final = install_root / "ffmpeg"
        _replace_tree(staged, final)
        _mark_executable(final)
        return final.resolve()
    except FfmpegDownloadCancelled:
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)


def parse_checksums(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2 or parts[0].startswith("#"):
            continue
        found[parts[-1].lstrip("*")] = parts[0].lower()
    return found


class UrllibReleaseSource:
    def latest_assets(self) -> list[tuple[str, str]]:
        request = urllib.request.Request(
            RELEASE_API,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/vnd.github+json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise FfmpegDownloadError(f"Could not read the ffmpeg release ({exc.code}).") from exc
        except urllib.error.URLError as exc:
            raise FfmpegDownloadError(f"Could not reach the ffmpeg release: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise FfmpegDownloadError("The ffmpeg release list was not valid JSON.") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("assets"), list):
            message = payload.get("message") if isinstance(payload, dict) else None
            raise FfmpegDownloadError(str(message or "Unexpected ffmpeg release list."))
        assets: list[tuple[str, str]] = []
        for item in payload["assets"]:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            url = item.get("browser_download_url")
            if isinstance(name, str) and isinstance(url, str):
                assets.append((name, url))
        return assets

    def download(self, url: str, dest: Path, report: Progress, cancelled: Cancelled) -> None:
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            response = urllib.request.urlopen(request, timeout=120)
        except urllib.error.HTTPError as exc:
            raise FfmpegDownloadError(f"Download failed ({exc.code}).") from exc
        except urllib.error.URLError as exc:
            raise FfmpegDownloadError(f"Could not download ffmpeg: {exc.reason}") from exc
        with response:
            total = _content_length(response.headers.get("Content-Length"))
            done = 0
            last_report = -1
            with dest.open("wb") as handle:
                while True:
                    _check_cancelled(cancelled)
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)
                    done += len(chunk)
                    if _should_report(done, total, last_report):
                        last_report = done
                        report(_download_message(done, total), _percent(done, total))
            if total is not None and done != total:
                raise FfmpegDownloadError("The ffmpeg download ended early.")


def _download_archives(
    work: Path,
    system: str,
    machine: str,
    source: ReleaseSource,
    report: Progress,
    cancelled: Cancelled,
) -> list[Path]:
    if system.lower() == "darwin":
        planned = [("ffmpeg.zip", MACOS_FFMPEG), ("ffprobe.zip", MACOS_FFPROBE)]
        checksums: dict[str, str] = {}
    else:
        assets = dict(source.latest_assets())
        name = github_asset_name(system, machine)
        url = assets.get(name)
        checksum_url = assets.get("checksums.sha256")
        if not url or not checksum_url:
            raise FfmpegDownloadError(f"The latest ffmpeg release has no file named {name}.")
        planned = [(name, url)]
        checksum_path = work / "checksums.sha256"
        source.download(checksum_url, checksum_path, report, cancelled)
        checksums = parse_checksums(checksum_path.read_text(encoding="utf-8", errors="replace"))
    saved: list[Path] = []
    for name, url in planned:
        _check_cancelled(cancelled)
        dest = work / name
        report(f"Downloading {name}", 0.0)
        source.download(url, dest, report, cancelled)
        expected = checksums.get(name)
        if expected is not None:
            report("Checking ffmpeg download", 1.0)
            actual = _sha256(dest)
            if actual != expected:
                raise FfmpegDownloadError(f"Checksum mismatch for {name}.")
        elif checksums:
            raise FfmpegDownloadError(f"The latest ffmpeg release has no checksum for {name}.")
        saved.append(dest)
    return saved


def _stage_binaries(tree: Path, staged: Path) -> None:
    tool_dir = _find_tool_dir(tree)
    if tool_dir is None:
        raise FfmpegDownloadError("The archive did not contain ffmpeg and ffprobe.")
    staged.mkdir()
    for child in tool_dir.iterdir():
        target = staged / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        elif child.is_file() and not child.is_symlink():
            shutil.copy2(child, target)
    if _find_tool_dir(staged) != staged:
        raise FfmpegDownloadError("The archive did not contain ffmpeg and ffprobe.")


def _find_tool_dir(root: Path) -> Path | None:
    for directory in [root, *sorted(path for path in root.rglob("*") if path.is_dir())]:
        if _has_tool(directory, "ffmpeg") and _has_tool(directory, "ffprobe"):
            return directory
    return None


def _has_tool(directory: Path, tool: str) -> bool:
    for name in (tool, f"{tool}.exe"):
        candidate = directory / name
        if candidate.is_file() and not candidate.is_symlink():
            return True
    return False


def _extract(archive: Path, dest: Path) -> None:
    name = archive.name.lower()
    try:
        if name.endswith(".zip"):
            _extract_zip(archive, dest)
        elif name.endswith(".tar.xz") or name.endswith(".txz"):
            _extract_tar(archive, dest)
        else:
            raise FfmpegDownloadError(f"Unsupported ffmpeg archive: {archive.name}")
    except (zipfile.BadZipFile, tarfile.TarError) as exc:
        raise FfmpegDownloadError(f"Could not extract {archive.name}.") from exc


def _extract_zip(archive: Path, dest: Path) -> None:
    with zipfile.ZipFile(archive) as package:
        for info in package.infolist():
            if info.is_dir():
                _safe_destination(dest, info.filename).mkdir(parents=True, exist_ok=True)
                continue
            target = _safe_file_destination(dest, info.filename)
            target.parent.mkdir(parents=True, exist_ok=True)
            with package.open(info) as source, target.open("wb") as handle:
                shutil.copyfileobj(source, handle)


def _extract_tar(archive: Path, dest: Path) -> None:
    with tarfile.open(archive, "r:xz") as package:
        for member in package.getmembers():
            if member.issym() or member.islnk() or member.isdev():
                raise FfmpegDownloadError(f"Unsafe archive entry: {member.name}")
            if member.isdir():
                _safe_destination(dest, member.name).mkdir(parents=True, exist_ok=True)
                continue
            if not member.isfile():
                continue
            target = _safe_file_destination(dest, member.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            extracted = package.extractfile(member)
            if extracted is None:
                raise FfmpegDownloadError(f"Could not read {member.name} from the archive.")
            with extracted, target.open("wb") as handle:
                shutil.copyfileobj(extracted, handle)


def _safe_destination(root: Path, name: str) -> Path:
    cleaned = name.replace("\\", "/").lstrip("/")
    while cleaned.startswith("./"):
        cleaned = cleaned[2:]
    pure = Path(cleaned)
    if not cleaned:
        return root
    if pure.is_absolute() or ".." in pure.parts:
        raise FfmpegDownloadError(f"Unsafe archive path: {name}")
    destination = root / pure
    resolved = destination.resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise FfmpegDownloadError(f"Unsafe archive path: {name}")
    return destination


def _safe_file_destination(root: Path, name: str) -> Path:
    destination = _safe_destination(root, name)
    if destination.resolve() == root.resolve():
        raise FfmpegDownloadError(f"Unsafe archive path: {name}")
    return destination


def _replace_tree(staged: Path, final: Path) -> None:
    backup = final.with_name("ffmpeg.previous")
    try:
        if backup.exists():
            shutil.rmtree(backup)
        if final.exists():
            final.rename(backup)
        staged.rename(final)
    except OSError as exc:
        if backup.exists() and not final.exists():
            backup.rename(final)
        raise FfmpegDownloadError(f"Could not replace the ffmpeg folder: {exc}") from exc
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)


def _mark_executable(folder: Path) -> None:
    if os.name == "nt":
        return
    for name in ("ffmpeg", "ffprobe", "ffplay"):
        candidate = folder / name
        if candidate.is_file():
            candidate.chmod(candidate.stat().st_mode | 0o755)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _content_length(value: str | None) -> int | None:
    if value and value.isdigit():
        return int(value)
    return None


def _percent(done: int, total: int | None) -> float | None:
    if not total:
        return None
    return min(1.0, done / total)


def _download_message(done: int, total: int | None) -> str:
    downloaded = done // (1024 * 1024)
    if total:
        return f"Downloading ffmpeg {downloaded} / {total // (1024 * 1024)} MB"
    return f"Downloading ffmpeg {downloaded} MB"


def _should_report(done: int, total: int | None, last_report: int) -> bool:
    if done == 0 or (total is not None and done == total):
        return True
    return done - last_report >= 1024 * 1024


def _check_cancelled(cancelled: Cancelled) -> None:
    if cancelled():
        raise FfmpegDownloadCancelled()
