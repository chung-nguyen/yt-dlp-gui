import queue
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import customtkinter as ctk

from ytdlp_gui.app import App
from ytdlp_gui.options import FORMAT_MP4, PRESET_CAR_HUD


class QualitySelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        ctk.set_appearance_mode("dark")
        self.app = App()
        self.app.update()
        self.app._loading = True
        self.app.preset_var.set(PRESET_CAR_HUD)
        self.app.quality_var.set("480p")
        self.app.format_var.set(FORMAT_MP4)
        self.app._loading = False
        self.app._sync_quality_state()
        self.app._refresh_preview()

    def tearDown(self) -> None:
        pending = self.app.tk.call("after", "info")
        for after_id in self.app.tk.splitlist(pending):
            self.app.tk.call("after", "cancel", after_id)
        self.app.destroy()

    def test_quality_change_after_preset_updates_preview(self):
        self.app.preset_combo._dropdown_callback("Best quality")
        self.app.update_idletasks()
        self.assertEqual(self.app.quality_var.get(), "Best")

        self.app.quality_combo._dropdown_callback("720p")
        self.app.update_idletasks()

        preview = self.app.command_box.get("1.0", "end")
        self.assertEqual(self.app.quality_var.get(), "720p")
        self.assertEqual(self.app.quality_combo.get(), "720p")
        self.assertNotIn("Unknown quality", preview)
        self.assertIn("height<=720", preview)

    def test_normalize_names_checkbox_updates_preview(self):
        self.app.normalize_var.set(True)
        self.app._on_option()
        self.assertIn("drop diacritics and symbols", self.app.command_box.get("1.0", "end"))
        self.app.normalize_var.set(False)
        self.app._on_option()
        self.assertNotIn("drop diacritics", self.app.command_box.get("1.0", "end"))

    def test_quality_change_without_preset_keeps_value(self):
        self.app.quality_combo._dropdown_callback("360p")
        self.app.update_idletasks()
        self.assertEqual(self.app.quality_var.get(), "360p")
        self.assertNotIn("Unknown quality", self.app.command_box.get("1.0", "end"))

    def test_audio_preset_disables_quality_until_a_video_preset(self):
        self.app.preset_combo._dropdown_callback("Audio MP3")
        self.app.update_idletasks()
        self.assertEqual(self.app.quality_combo.cget("state"), "disabled")

        self.app.preset_combo._dropdown_callback("1080p MP4 remux")
        self.app.update_idletasks()
        self.assertEqual(self.app.quality_combo.cget("state"), "readonly")
        self.app.quality_combo._dropdown_callback("480p")
        self.app.update_idletasks()
        self.assertEqual(self.app.quality_var.get(), "480p")
        self.assertIn("height<=480", self.app.command_box.get("1.0", "end"))

    def test_download_ffmpeg_saves_the_installed_folder(self):
        self.assertEqual(self.app.get_ffmpeg_button.cget("text"), "Download ffmpeg")
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "ffmpeg"
            folder.mkdir()
            (folder / "ffmpeg.exe").write_bytes(b"")

            def fake_download(_install_root, **_kwargs):
                return folder

            with (
                patch("ytdlp_gui.app.download_latest_ffmpeg", side_effect=fake_download),
                patch("ytdlp_gui.app.save_settings") as save,
            ):
                self.app._download_ffmpeg()
                self.app._ffmpeg_thread.join(timeout=5)
                self.assertFalse(self.app._ffmpeg_thread.is_alive())
                while True:
                    try:
                        self.app._handle(self.app._events.get_nowait())
                    except queue.Empty:
                        break

            self.assertEqual(self.app.ffmpeg_var.get(), str(folder))
            self.assertEqual(save.call_args.args[0]["ffmpeg_location"], str(folder))
            self.assertIn(str(folder), self.app.ffmpeg_status.cget("text"))
            self.assertIn("ffmpeg installed", self.app.progress_label.cget("text"))
            self.assertEqual(self.app.get_ffmpeg_button.cget("state"), "normal")
