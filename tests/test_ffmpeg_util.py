import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ytdlp_gui.ffmpeg_util import find_ffmpeg, install_dir, is_hud_compatible


def _media(codec_video="h264", codec_audio="aac", height=360, pix_fmt="yuv420p", container="mov,mp4,m4a,3gp,3g2,mj2"):
    return {
        "format": {"format_name": container},
        "streams": [
            {
                "codec_type": "video",
                "codec_name": codec_video,
                "pix_fmt": pix_fmt,
                "height": height,
                "profile": "Main",
            },
            {"codec_type": "audio", "codec_name": codec_audio, "profile": "LC"},
        ],
    }


class FfmpegUtilTests(unittest.TestCase):
    def test_sample_shape_is_hud_compatible_at_480p(self):
        info = _media(height=360)
        self.assertTrue(is_hud_compatible(info, 480))
        self.assertTrue(is_hud_compatible(info, 360))
        self.assertFalse(is_hud_compatible(_media(height=720), 480))

    def test_incompatible_codecs_and_containers(self):
        self.assertFalse(is_hud_compatible(_media(codec_video="vp9"), 480))
        self.assertFalse(is_hud_compatible(_media(codec_audio="opus"), 480))
        self.assertFalse(is_hud_compatible(_media(container="matroska,webm"), 480))
        self.assertFalse(is_hud_compatible(_media(pix_fmt="yuv420p10le"), 480))

    def test_explicit_ffmpeg_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            (directory / "ffmpeg.exe").write_text("", encoding="utf-8")
            self.assertEqual(find_ffmpeg(str(directory / "ffmpeg.exe")), str(directory))
            self.assertEqual(find_ffmpeg(str(directory)), str(directory))

    def test_install_dir_follows_a_frozen_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            exe = Path(tmp) / "yt-dlp-gui.exe"
            exe.write_bytes(b"")
            with (
                patch.object(sys, "frozen", True, create=True),
                patch.object(sys, "executable", str(exe)),
            ):
                self.assertEqual(install_dir(), exe.parent.resolve())

    def test_folder_beside_the_app_is_used_when_settings_are_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            bundled = root / "ffmpeg"
            bundled.mkdir()
            (bundled / "ffmpeg.exe").write_bytes(b"")
            other = root / "other"
            other.mkdir()
            (other / "ffmpeg.exe").write_bytes(b"")
            with patch("ytdlp_gui.ffmpeg_util.install_dir", return_value=root):
                self.assertEqual(find_ffmpeg(None), str(bundled))
                self.assertEqual(find_ffmpeg(str(other)), str(other))
                self.assertEqual(find_ffmpeg(str(root / "missing")), str(bundled))


if __name__ == "__main__":
    unittest.main()
