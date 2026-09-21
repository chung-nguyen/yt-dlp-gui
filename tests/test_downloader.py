import tempfile
import threading
import unittest
from pathlib import Path

from ytdlp_gui.downloader import run_download
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


if __name__ == "__main__":
    unittest.main()
