# yt-dlp GUI

A small desktop downloader for Windows, Ubuntu, and macOS. It builds yt-dlp options from a form, runs the download, and shows yt-dlp's log next to the saved files.

Python 3.11 or newer, [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter), and [yt-dlp](https://github.com/yt-dlp/yt-dlp). ffmpeg is **not** bundled. The app looks for it on `PATH` (and one known Windows tools path) so the download folder stays small.

## Run

```text
python -m venv .venv
```

Windows, if `python` is not Python 3:

```text
py -3 -m venv .venv
.venv\Scripts\activate
pip install -e .
python -m ytdlp_gui
```

Ubuntu / macOS:

```text
source .venv/bin/activate
pip install -e .
python -m ytdlp_gui
```

Install ffmpeg separately if you want merging or the car-HUD recode. On Windows the app also checks `F:\tools\ffmpeg-8.1-full_build\bin` when ffmpeg is not on `PATH`. You can browse to `ffmpeg` / `ffmpeg.exe` in the window.

## Car HUD preset (Suzuki XL7)

The default preset targets the same **codecs** as a file that already plays on the XL7 Android HUD:

- MP4 container
- H.264 (yuv420p), capped at 480p
- AAC-LC, stereo, 44.1 kHz, 128 kbps

If the site already offers H.264 + AAC inside MP4 at or below the quality cap, the file is kept as-is. Otherwise, when ffmpeg is available, it is recoded to that layout. Filenames stay human-readable (`Title [Artist].mp4`), including spaces and brackets.

Other presets (best quality, 1080p MP4 remux, audio-only) do not recode.

## Later: a small frozen build

PyInstaller or Nuitka can freeze this app without shipping ffmpeg or Qt. Expect roughly 20–35 MB per OS once yt-dlp and CustomTkinter are packed, and leave ffmpeg as an external tool.
