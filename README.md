# yt-dlp GUI

A small desktop downloader for Windows, Ubuntu, and macOS. It builds yt-dlp options from a form, runs the download, and shows yt-dlp's log next to the saved files.

Python 3.11 or newer, [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter), and [yt-dlp](https://github.com/yt-dlp/yt-dlp). ffmpeg is **not** bundled with the app.

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

Use **Download ffmpeg** to fetch the latest release into an `ffmpeg` folder next to the app. The ffmpeg field is set to that folder and saved. You can still browse to an existing `ffmpeg` / `ffmpeg.exe`. On Windows the app also checks `PATH` and `F:\tools\ffmpeg-8.1-full_build\bin`.

## Car HUD preset (Suzuki XL7)

The default preset targets the same **codecs** as a file that already plays on the XL7 Android HUD:

- MP4 container
- H.264 (yuv420p), capped at 480p
- AAC-LC, stereo, 44.1 kHz, 128 kbps

If the site already offers H.264 + AAC inside MP4 at or below the quality cap, the file is kept as-is. Otherwise, when ffmpeg is available, it is recoded to that layout. **Normalize names** is on by default: after download, diacritics and symbols are removed (`Bai hat Artist.mp4`) while spaces stay. Turn it off to keep the original title, including brackets.

Other presets (best quality, 1080p MP4 remux, audio-only) do not recode.

## Later: a small frozen build

PyInstaller or Nuitka can freeze this app without shipping ffmpeg or Qt. Expect roughly 20–35 MB per OS once yt-dlp and CustomTkinter are packed, and leave ffmpeg as an external tool.
