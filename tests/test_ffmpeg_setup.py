import hashlib
import io
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from ytdlp_gui.ffmpeg_setup import (
    MACOS_FFMPEG,
    MACOS_FFPROBE,
    FfmpegDownloadCancelled,
    FfmpegDownloadError,
    download_latest_ffmpeg,
    github_asset_name,
    parse_checksums,
)


class MemorySource:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.downloads: list[str] = []

    def latest_assets(self) -> list[tuple[str, str]]:
        return [(url.removeprefix("mem:"), url) for url in self.files]

    def download(self, url: str, dest: Path, report, cancelled) -> None:
        if cancelled():
            raise FfmpegDownloadCancelled()
        self.downloads.append(url)
        data = self.files[url]
        dest.write_bytes(data)
        report("Downloading ffmpeg", 1.0)


def _zip_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as package:
        for name, data in files.items():
            package.writestr(name, data)
    return buffer.getvalue()


def _tar_xz_bytes(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:xz") as package:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            package.addfile(info, io.BytesIO(data))
    return buffer.getvalue()


def _release(archive_name: str, archive: bytes) -> MemorySource:
    digest = hashlib.sha256(archive).hexdigest()
    checksums = f"{digest}  {archive_name}\n".encode()
    return MemorySource(
        {
            "mem:checksums.sha256": checksums,
            f"mem:{archive_name}": archive,
        }
    )


class FfmpegSetupTests(unittest.TestCase):
    def test_asset_names_match_published_builds(self):
        self.assertEqual(github_asset_name("Windows", "AMD64"), "ffmpeg-master-latest-win64-gpl.zip")
        self.assertEqual(github_asset_name("Windows", "ARM64"), "ffmpeg-master-latest-winarm64-gpl.zip")
        self.assertEqual(github_asset_name("Linux", "x86_64"), "ffmpeg-master-latest-linux64-gpl.tar.xz")
        self.assertEqual(github_asset_name("Linux", "aarch64"), "ffmpeg-master-latest-linuxarm64-gpl.tar.xz")
        with self.assertRaises(FfmpegDownloadError):
            github_asset_name("Linux", "riscv64")

    def test_parse_checksums(self):
        text = "abc  ffmpeg-master-latest-win64-gpl.zip\n# comment\ndef *other.tar.xz\n"
        self.assertEqual(
            parse_checksums(text),
            {
                "ffmpeg-master-latest-win64-gpl.zip": "abc",
                "other.tar.xz": "def",
            },
        )

    def test_windows_release_is_installed_beside_the_app(self):
        archive_name = github_asset_name("Windows", "AMD64")
        archive = _zip_bytes(
            {
                "ffmpeg-master-latest-win64-gpl/bin/ffmpeg.exe": b"video",
                "ffmpeg-master-latest-win64-gpl/bin/ffprobe.exe": b"probe",
                "ffmpeg-master-latest-win64-gpl/doc/readme.txt": b"docs",
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            previous = root / "ffmpeg"
            previous.mkdir()
            (previous / "old.txt").write_text("old", encoding="utf-8")
            installed = download_latest_ffmpeg(
                root,
                system="Windows",
                machine="AMD64",
                source=_release(archive_name, archive),
            )
            self.assertEqual(installed, (root / "ffmpeg").resolve())
            self.assertEqual((installed / "ffmpeg.exe").read_bytes(), b"video")
            self.assertEqual((installed / "ffprobe.exe").read_bytes(), b"probe")
            self.assertFalse((installed / "old.txt").exists())
            self.assertFalse((installed / "doc").exists())
            self.assertFalse((root / ".ffmpeg-download").exists())
            self.assertFalse((root / "ffmpeg.previous").exists())

    def test_linux_archive_installs_binaries_in_the_ffmpeg_folder(self):
        archive_name = github_asset_name("Linux", "x86_64")
        archive = _tar_xz_bytes(
            {
                "ffmpeg-master-latest-linux64-gpl/bin/ffmpeg": b"video",
                "ffmpeg-master-latest-linux64-gpl/bin/ffprobe": b"probe",
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            installed = download_latest_ffmpeg(
                root,
                system="Linux",
                machine="x86_64",
                source=_release(archive_name, archive),
            )
            self.assertEqual((installed / "ffmpeg").read_bytes(), b"video")
            self.assertEqual((installed / "ffprobe").read_bytes(), b"probe")

    def test_macos_release_downloads_ffmpeg_and_ffprobe(self):
        source = MemorySource(
            {
                MACOS_FFMPEG: _zip_bytes({"ffmpeg": b"video"}),
                MACOS_FFPROBE: _zip_bytes({"ffprobe": b"probe"}),
            }
        )
        with tempfile.TemporaryDirectory() as tmp:
            installed = download_latest_ffmpeg(
                Path(tmp),
                system="Darwin",
                machine="arm64",
                source=source,
            )
            self.assertEqual((installed / "ffmpeg").read_bytes(), b"video")
            self.assertEqual((installed / "ffprobe").read_bytes(), b"probe")
            self.assertEqual(source.downloads, [MACOS_FFMPEG, MACOS_FFPROBE])

    def test_checksum_mismatch_does_not_replace_an_existing_folder(self):
        archive_name = github_asset_name("Windows", "AMD64")
        archive = _zip_bytes({"bin/ffmpeg.exe": b"video", "bin/ffprobe.exe": b"probe"})
        source = _release(archive_name, archive)
        source.files["mem:checksums.sha256"] = b"0" * 64 + f"  {archive_name}\n".encode()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            keep = root / "ffmpeg" / "keep.txt"
            keep.parent.mkdir()
            keep.write_text("keep", encoding="utf-8")
            with self.assertRaises(FfmpegDownloadError):
                download_latest_ffmpeg(root, system="Windows", machine="AMD64", source=source)
            self.assertEqual(keep.read_text(encoding="utf-8"), "keep")
            self.assertFalse((root / ".ffmpeg-download").exists())

    def test_archive_paths_cannot_escape_the_install_folder(self):
        archive_name = github_asset_name("Windows", "AMD64")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as package:
            package.writestr(zipfile.ZipInfo("../outside.exe"), b"bad")
        source = _release(archive_name, buffer.getvalue())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(FfmpegDownloadError):
                download_latest_ffmpeg(root, system="Windows", machine="AMD64", source=source)
            self.assertEqual(list(root.rglob("outside.exe")), [])
            self.assertFalse((root / "ffmpeg").exists())

    def test_cancel_leaves_the_current_folder_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            marker = root / "ffmpeg" / "keep.txt"
            marker.parent.mkdir()
            marker.write_text("keep", encoding="utf-8")
            with self.assertRaises(FfmpegDownloadCancelled):
                download_latest_ffmpeg(
                    root,
                    cancelled=lambda: True,
                    system="Windows",
                    machine="AMD64",
                    source=MemorySource({}),
                )
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")
            self.assertFalse((root / ".ffmpeg-download").exists())
