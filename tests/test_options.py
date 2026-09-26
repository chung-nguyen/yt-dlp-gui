import os
import tempfile
import unittest
from pathlib import Path

from ytdlp_gui.options import (
    FORMAT_HUD,
    FORMAT_M4A,
    FORMAT_MKV,
    FORMAT_MP3,
    FORMAT_MP4,
    FORMAT_WEBM,
    PLAYLIST_ALL,
    PRESET_BEST,
    DownloadRequest,
    build_plan,
    normalize_filename,
    parse_urls,
    preset_defaults,
)
from ytdlp_gui.settings import default_output_dir, load_settings, save_settings


HUD_480 = (
    "bv*[vcodec^=avc][height<=480]+ba[acodec^=mp4a]"
    "/b[ext=mp4][height<=480]"
    "/bv*[height<=480]+ba/b"
)


class OptionsTests(unittest.TestCase):
    def test_default_car_hud_is_480p_h264_aac(self):
        plan = build_plan(
            DownloadRequest(urls=["https://example.com/watch"], output_dir=r"D:\Downloads\done")
        )
        self.assertEqual(plan.ydl_opts["format"], HUD_480)
        self.assertEqual(plan.ydl_opts["format_sort"], ["res:480", "vcodec:h264", "acodec:aac"])
        self.assertEqual(plan.ydl_opts["merge_output_format"], "mp4")
        self.assertEqual(plan.ydl_opts["outtmpl"]["default"], "%(title)s.%(ext)s")
        self.assertTrue(plan.ydl_opts["paths"]["home"].replace("\\", "/").endswith("Downloads/done"))
        self.assertTrue(plan.hud_recode)
        self.assertEqual(plan.max_height, 480)
        self.assertFalse(plan.ydl_opts["restrictfilenames"])
        self.assertTrue(plan.ydl_opts["noplaylist"])
        self.assertEqual(plan.ydl_opts["windowsfilenames"], os.name == "nt")
        args = plan.recode_args
        for flag in ("libx264", "main", "yuv420p", "aac", "128k", "44100", "+faststart", "mp4"):
            self.assertIn(flag, args)
        self.assertIn("scale=-2:'min(480,ih)'", args)
        self.assertIn("height<=480", plan.command_preview)
        self.assertIn("--merge-output-format mp4", plan.command_preview)
        self.assertIn("--no-playlist", plan.command_preview)
        self.assertIn("%(title)s.%(ext)s", plan.command_preview)
        self.assertIn("libx264", plan.command_preview)

    def test_quality_cap_changes_hud_filter_and_scale(self):
        plan = build_plan(
            DownloadRequest(
                urls=["https://example.com/v"],
                output_dir="/videos",
                container=FORMAT_HUD,
                quality="720p",
            )
        )
        self.assertIn("[height<=720]", plan.ydl_opts["format"])
        self.assertEqual(plan.ydl_opts["format_sort"][0], "res:720")
        self.assertIn("scale=-2:'min(720,ih)'", plan.recode_args)
        self.assertEqual(plan.max_height, 720)

    def test_best_quality_remux_has_no_height_cap_or_recode(self):
        plan = build_plan(
            DownloadRequest(
                urls=["https://example.com/v"],
                output_dir="/videos",
                preset=PRESET_BEST,
                quality="Best",
                container=FORMAT_MP4,
            )
        )
        self.assertEqual(plan.ydl_opts["format"], "bv*+ba/b")
        self.assertEqual(plan.ydl_opts["merge_output_format"], "mp4")
        self.assertNotIn("format_sort", plan.ydl_opts)
        self.assertFalse(plan.hud_recode)
        self.assertEqual(plan.recode_args, [])
        self.assertNotIn("libx264", plan.command_preview)

    def test_1080p_mp4_remux_matches_generator_style_selector(self):
        plan = build_plan(
            DownloadRequest(
                urls=["https://example.com/v"],
                output_dir="/videos",
                quality="1080p",
                container=FORMAT_MP4,
            )
        )
        self.assertEqual(plan.ydl_opts["format"], "bv*[height<=1080]+ba/b[height<=1080]")
        self.assertFalse(plan.hud_recode)

    def test_mkv_webm_and_audio(self):
        mkv = build_plan(
            DownloadRequest(
                urls=["https://example.com/v"],
                output_dir="/videos",
                quality="360p",
                container=FORMAT_MKV,
            )
        )
        self.assertEqual(mkv.ydl_opts["merge_output_format"], "mkv")
        self.assertEqual(mkv.ydl_opts["format"], "bv*[height<=360]+ba/b[height<=360]")

        webm = build_plan(
            DownloadRequest(
                urls=["https://example.com/v"],
                output_dir="/videos",
                quality="Best",
                container=FORMAT_WEBM,
            )
        )
        self.assertEqual(webm.ydl_opts["merge_output_format"], "webm")
        self.assertIn("[ext=webm]", webm.ydl_opts["format"])
        self.assertNotIn("height<=", webm.ydl_opts["format"])

        mp3 = build_plan(
            DownloadRequest(
                urls=["https://example.com/v"],
                output_dir="/videos",
                container=FORMAT_MP3,
                quality="1080p",
            )
        )
        self.assertEqual(mp3.ydl_opts["format"], "ba/b")
        self.assertEqual(mp3.ydl_opts["postprocessors"][0]["preferredcodec"], "mp3")
        self.assertNotIn("merge_output_format", mp3.ydl_opts)
        self.assertFalse(mp3.hud_recode)
        self.assertIsNone(mp3.max_height)
        self.assertIn("-x", mp3.command_preview)
        self.assertIn("mp3", mp3.command_preview)

        m4a = build_plan(
            DownloadRequest(
                urls=["https://example.com/v"],
                output_dir="/videos",
                container=FORMAT_M4A,
            )
        )
        self.assertEqual(m4a.ydl_opts["postprocessors"][0]["preferredcodec"], "m4a")

    def test_playlist_cookies_overwrite_and_resume(self):
        plan = build_plan(
            DownloadRequest(
                urls=["https://example.com/a", "https://example.com/b"],
                output_dir="/videos",
                container=FORMAT_MP4,
                quality="480p",
                playlist=PLAYLIST_ALL,
                cookies_browser="Firefox",
                overwrite=True,
                resume=False,
                ffmpeg_location=r"F:\tools\ffmpeg-8.1-full_build\bin",
            )
        )
        self.assertFalse(plan.ydl_opts["noplaylist"])
        self.assertEqual(plan.ydl_opts["cookiesfrombrowser"], ("firefox",))
        self.assertTrue(plan.ydl_opts["overwrites"])
        self.assertFalse(plan.ydl_opts["continuedl"])
        preview = plan.command_preview
        self.assertIn("--yes-playlist", preview)
        self.assertIn("--cookies-from-browser", preview)
        self.assertIn("firefox", preview)
        self.assertIn("--force-overwrites", preview)
        self.assertIn("--no-continue", preview)
        self.assertIn("--ffmpeg-location", preview)
        self.assertIn("https://example.com/a", preview)
        self.assertIn("https://example.com/b", preview)

    def test_parse_urls_skips_blanks_and_comments(self):
        self.assertEqual(
            parse_urls("\n https://example.com/a \n# skip\n\nhttps://example.com/b\n"),
            ["https://example.com/a", "https://example.com/b"],
        )

    def test_preset_defaults(self):
        self.assertEqual(preset_defaults("Car HUD XL7"), ("480p", FORMAT_HUD))
        self.assertEqual(preset_defaults("Best quality"), ("Best", FORMAT_MP4))
        self.assertEqual(preset_defaults("1080p MP4 remux"), ("1080p", FORMAT_MP4))
        self.assertEqual(preset_defaults("Audio MP3"), ("Best", FORMAT_MP3))

    def test_empty_preview_uses_url_placeholder(self):
        plan = build_plan(DownloadRequest(urls=[], output_dir="/videos"))
        self.assertIn("URL", plan.command_preview.splitlines()[0])

    def test_normalize_filename_drops_diacritics_and_symbols(self):
        self.assertEqual(normalize_filename("Bài hát [Nghệ sĩ].mp4"), "Bai hat Nghe si.mp4")
        self.assertEqual(normalize_filename("Đêm mưa.mp3"), "Dem mua.mp3")
        self.assertEqual(normalize_filename("Café: Live! #1.mkv"), "Cafe Live 1.mkv")
        self.assertEqual(normalize_filename("Don't Stop.mp4"), "Dont Stop.mp4")
        self.assertEqual(normalize_filename("A  &  B.webm"), "A B.webm")
        self.assertEqual(normalize_filename("東京.mp4"), "東京.mp4")
        self.assertEqual(normalize_filename("!!!.mp4"), "download.mp4")
        self.assertEqual(normalize_filename("CON.mp4"), "CON file.mp4")

    def test_normalize_names_is_on_by_default(self):
        plan = build_plan(DownloadRequest(urls=["https://example.com/v"], output_dir="/videos"))
        self.assertTrue(plan.normalize_filenames)
        self.assertIn("drop diacritics and symbols", plan.command_preview)
        plain = build_plan(
            DownloadRequest(
                urls=["https://example.com/v"],
                output_dir="/videos",
                normalize_filenames=False,
            )
        )
        self.assertNotIn("drop diacritics", plain.command_preview)


class SettingsTests(unittest.TestCase):
    def test_default_output_dir_prefers_existing_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preferred = root / "done"
            preferred.mkdir()
            fallback = root / "Downloads"
            self.assertEqual(default_output_dir(preferred, fallback), str(preferred))
            missing = root / "missing"
            self.assertEqual(default_output_dir(missing, fallback), str(fallback))

    def test_settings_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            save_settings({"output_dir": str(Path(tmp)), "quality": "360p", "resume": False}, path)
            loaded = load_settings(path)
            self.assertEqual(loaded["quality"], "360p")
            self.assertFalse(loaded["resume"])
            self.assertEqual(loaded["output_dir"], str(Path(tmp)))
            self.assertEqual(loaded["preset"], "Car HUD XL7")
            self.assertTrue(loaded["normalize_filenames"])
            save_settings({"normalize_filenames": False}, path)
            self.assertFalse(load_settings(path)["normalize_filenames"])


if __name__ == "__main__":
    unittest.main()
