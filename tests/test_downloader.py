import tempfile
import threading
import unittest
from pathlib import Path

from ytdlp_gui.downloader import normalize_downloaded_file, run_download
from ytdlp_gui.options import DownloadRequest, build_plan


class DownloaderTests(unittest.TestCase):
    def test_empty_url_list_does_not_start_yt_dlp(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_plan(DownloadRequest(urls=[], output_dir=tmp))
            messages = []
            run_download(plan, messages.append, threading.Event())
        self.assertTrue(any(message.kind == "log" and "No URL" in message.text for message in messages))
        done = [message for message in messages if message.kind == "done"]
        self.assertEqual(len(done), 1)
        self.assertFalse(done[0].ok)
        self.assertFalse(Path(tmp).joinpath("settings.json").exists())

    def test_normalize_renames_the_finished_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            source = folder / "Café Live!.mp4"
            source.write_bytes(b"media")
            renamed = normalize_downloaded_file(source)
            self.assertEqual(renamed.name, "Cafe Live.mp4")
            self.assertEqual(renamed.read_bytes(), b"media")
            self.assertFalse(source.exists())

    def test_normalize_adds_a_number_when_the_name_is_taken(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "Cafe Live.mp4").write_bytes(b"kept")
            source = folder / "Café Live!.mp4"
            source.write_bytes(b"new")
            renamed = normalize_downloaded_file(source)
            self.assertEqual(renamed.name, "Cafe Live 2.mp4")
            self.assertEqual((folder / "Cafe Live.mp4").read_bytes(), b"kept")
            self.assertEqual(renamed.read_bytes(), b"new")


if __name__ == "__main__":
    unittest.main()
