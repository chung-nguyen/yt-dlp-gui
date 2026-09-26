"""CustomTkinter window for the downloader."""

from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from ytdlp_gui.downloader import UiMessage, run_download
from ytdlp_gui.ffmpeg_setup import (
    FfmpegDownloadCancelled,
    FfmpegDownloadError,
    download_latest_ffmpeg,
)
from ytdlp_gui.ffmpeg_util import find_ffmpeg, install_dir
from ytdlp_gui.options import (
    BROWSERS,
    FORMAT_M4A,
    FORMAT_MP3,
    FORMATS,
    PLAYLISTS,
    PRESETS,
    QUALITIES,
    DownloadRequest,
    build_plan,
    parse_urls,
    preset_defaults,
)
from ytdlp_gui.settings import load_settings, save_settings


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("yt-dlp GUI")
        self.geometry("980x780")
        self.minsize(860, 680)

        self._events: queue.Queue[UiMessage] = queue.Queue()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._ffmpeg_thread: threading.Thread | None = None
        self._loading = True
        self._pulsing = False

        self.output_var = tk.StringVar()
        self.ffmpeg_var = tk.StringVar()
        self.preset_var = tk.StringVar(value=PRESETS[0])
        self.quality_var = tk.StringVar(value="480p")
        self.format_var = tk.StringVar(value=FORMATS[0])
        self.playlist_var = tk.StringVar(value=PLAYLISTS[0])
        self.cookies_var = tk.StringVar(value=BROWSERS[0])
        self.overwrite_var = tk.BooleanVar(value=False)
        self.resume_var = tk.BooleanVar(value=True)
        self.normalize_var = tk.BooleanVar(value=True)

        self._build()
        self._load_form()
        for variable in (
            self.output_var,
            self.ffmpeg_var,
            self.quality_var,
            self.format_var,
            self.playlist_var,
            self.cookies_var,
        ):
            variable.trace_add("write", self._on_form_change)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll)

    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(12, weight=1)
        mono = _mono_font()

        header = ctk.CTkLabel(self, text="yt-dlp GUI", font=ctk.CTkFont(size=20, weight="bold"))
        header.grid(row=0, column=0, sticky="w", padx=16, pady=(14, 4))

        ctk.CTkLabel(self, text="URL (one per line)").grid(row=1, column=0, sticky="w", padx=16)
        self.url_box = ctk.CTkTextbox(self, height=88)
        self.url_box.grid(row=2, column=0, sticky="ew", padx=16, pady=(2, 8))
        self.url_box.bind("<KeyRelease>", self._on_form_change)

        self._path_row(3, "Output folder", self.output_var, self._browse_folder)
        self.get_ffmpeg_button = self._path_row(
            4,
            "ffmpeg",
            self.ffmpeg_var,
            self._browse_ffmpeg,
            ("Download ffmpeg", self._download_ffmpeg),
        )
        self.ffmpeg_status = ctk.CTkLabel(self, text="", anchor="w")
        self.ffmpeg_status.grid(row=5, column=0, sticky="w", padx=16, pady=(0, 6))

        options = ctk.CTkFrame(self, fg_color="transparent")
        options.grid(row=6, column=0, sticky="ew", padx=16, pady=4)
        for column in range(3):
            options.grid_columnconfigure(column, weight=1)
        self.preset_combo = self._combo(options, 0, 0, "Preset", self.preset_var, PRESETS, self._on_preset)
        self.quality_combo = self._combo(options, 0, 1, "Quality", self.quality_var, QUALITIES, self._on_option)
        self.format_combo = self._combo(options, 0, 2, "Format", self.format_var, FORMATS, self._on_option)

        extras = ctk.CTkFrame(self, fg_color="transparent")
        extras.grid(row=7, column=0, sticky="ew", padx=16, pady=4)
        for column in range(4):
            extras.grid_columnconfigure(column, weight=1)
        self._combo(extras, 0, 0, "Playlist", self.playlist_var, PLAYLISTS, self._on_option)
        self._combo(extras, 0, 1, "Cookies", self.cookies_var, BROWSERS, self._on_option)
        checks = ctk.CTkFrame(extras, fg_color="transparent")
        checks.grid(row=0, column=2, columnspan=2, sticky="sw", padx=6, pady=(18, 0))
        ctk.CTkCheckBox(
            checks, text="Overwrite", variable=self.overwrite_var, command=self._on_option
        ).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(
            checks, text="Resume", variable=self.resume_var, command=self._on_option
        ).pack(side="left", padx=(0, 16))
        ctk.CTkCheckBox(
            checks, text="Normalize names", variable=self.normalize_var, command=self._on_option
        ).pack(side="left")

        ctk.CTkLabel(self, text="Command").grid(row=8, column=0, sticky="w", padx=16, pady=(8, 0))
        self.command_box = ctk.CTkTextbox(self, height=108, font=mono)
        self.command_box.grid(row=9, column=0, sticky="ew", padx=16, pady=(2, 8))
        _keep_readonly(self.command_box)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(row=10, column=0, sticky="ew", padx=16, pady=4)
        actions.grid_columnconfigure(0, weight=1)
        self.progress = ctk.CTkProgressBar(actions)
        self.progress.set(0)
        self.progress.grid(row=0, column=0, sticky="ew", padx=(0, 12))
        self.download_button = ctk.CTkButton(actions, text="Download", width=110, command=self._start)
        self.download_button.grid(row=0, column=1, padx=(0, 8))
        self.cancel_button = ctk.CTkButton(
            actions, text="Cancel", width=90, state="disabled", command=self._cancel_download
        )
        self.cancel_button.grid(row=0, column=2)
        self.progress_label = ctk.CTkLabel(actions, text="Idle", anchor="w")
        self.progress_label.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))

        ctk.CTkLabel(self, text="Console").grid(row=11, column=0, sticky="w", padx=16, pady=(8, 0))
        self.console = ctk.CTkTextbox(self, font=mono)
        self.console.grid(row=12, column=0, sticky="nsew", padx=16, pady=(2, 16))
        _keep_readonly(self.console)

    def _path_row(self, row: int, label: str, variable: tk.StringVar, browse, extra=None):
        frame = ctk.CTkFrame(self, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", padx=16, pady=3)
        frame.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(frame, text=label, width=110, anchor="w").grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(frame, textvariable=variable).grid(row=0, column=1, sticky="ew", padx=8)
        ctk.CTkButton(frame, text="Browse", width=90, command=browse).grid(row=0, column=2)
        if extra is None:
            return None
        text, command = extra
        button = ctk.CTkButton(frame, text=text, width=150, command=command)
        button.grid(row=0, column=3, padx=(8, 0))
        return button

    def _combo(self, parent, row: int, column: int, label: str, variable, values, command):
        cell = ctk.CTkFrame(parent, fg_color="transparent")
        cell.grid(row=row, column=column, sticky="ew", padx=4)
        cell.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(cell, text=label, anchor="w").grid(row=0, column=0, sticky="w")
        combo = ctk.CTkComboBox(cell, variable=variable, values=values, command=command, state="readonly")
        combo.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        return combo

    def _load_form(self) -> None:
        settings = load_settings()
        self._loading = True
        self.output_var.set(str(settings.get("output_dir") or ""))
        ffmpeg = str(settings.get("ffmpeg_location") or "")
        self.ffmpeg_var.set(ffmpeg or find_ffmpeg(None) or "")
        self._set_choice(self.preset_var, settings.get("preset"), PRESETS)
        self._set_choice(self.quality_var, settings.get("quality"), QUALITIES)
        self._set_choice(self.format_var, settings.get("container"), FORMATS)
        self._set_choice(self.playlist_var, settings.get("playlist"), PLAYLISTS)
        self._set_choice(self.cookies_var, settings.get("cookies_browser"), BROWSERS)
        self.overwrite_var.set(bool(settings.get("overwrite")))
        self.resume_var.set(bool(settings.get("resume", True)))
        self.normalize_var.set(bool(settings.get("normalize_filenames", True)))
        self._loading = False
        self._sync_quality_state()
        self._refresh_ffmpeg_status()
        self._refresh_preview()

    def _set_choice(self, variable: tk.StringVar, value, choices: list[str]) -> None:
        variable.set(value if value in choices else choices[0])

    def _request(self) -> DownloadRequest:
        typed = self.ffmpeg_var.get().strip()
        return DownloadRequest(
            urls=parse_urls(self.url_box.get("1.0", "end")),
            output_dir=self.output_var.get().strip(),
            preset=self.preset_var.get(),
            quality=self.quality_var.get(),
            container=self.format_var.get(),
            playlist=self.playlist_var.get(),
            cookies_browser=self.cookies_var.get(),
            overwrite=bool(self.overwrite_var.get()),
            resume=bool(self.resume_var.get()),
            normalize_filenames=bool(self.normalize_var.get()),
            ffmpeg_location=find_ffmpeg(typed or None),
        )

    def _on_preset(self, value: str) -> None:
        if self._loading:
            return
        quality, container = preset_defaults(value)
        self._loading = True
        try:
            self.quality_var.set(quality)
            self.format_var.set(container)
        finally:
            self._loading = False
        self._sync_quality_state()
        self._refresh_preview()

    def _on_option(self, *_args) -> None:
        self._on_form_change()

    def _on_form_change(self, *_args) -> None:
        if self._loading:
            return
        self._sync_quality_state()
        self._refresh_ffmpeg_status()
        self._refresh_preview()

    def _sync_quality_state(self) -> None:
        audio = self.format_var.get() in (FORMAT_MP3, FORMAT_M4A)
        state = "disabled" if audio else "readonly"
        # CustomTkinter writes a readonly combobox by briefly enabling the entry.
        # Applying the same state again during that write locks it and drops the value.
        if self.quality_combo.cget("state") != state:
            self.quality_combo.configure(state=state)

    def _refresh_ffmpeg_status(self) -> None:
        found = find_ffmpeg(self.ffmpeg_var.get().strip() or None)
        if found:
            self.ffmpeg_status.configure(text=f"ffmpeg found: {found}", text_color="#8bd17c")
        else:
            self.ffmpeg_status.configure(
                text="ffmpeg not found — Car HUD recode will be skipped",
                text_color="#e6a23c",
            )

    def _refresh_preview(self) -> None:
        try:
            text = build_plan(self._request()).command_preview
        except ValueError as exc:
            text = str(exc)
        self.command_box.delete("1.0", "end")
        self.command_box.insert("1.0", text)

    def _browse_folder(self) -> None:
        current = self.output_var.get().strip()
        initial = current if current and Path(current).is_dir() else str(Path.home())
        chosen = filedialog.askdirectory(initialdir=initial)
        if chosen:
            self.output_var.set(chosen)

    def _browse_ffmpeg(self) -> None:
        chosen = filedialog.askopenfilename(
            filetypes=[("ffmpeg", "ffmpeg.exe"), ("ffmpeg", "ffmpeg"), ("All files", "*.*")]
        )
        if chosen:
            self.ffmpeg_var.set(chosen)

    def _download_ffmpeg(self) -> None:
        if self._busy():
            self._append_log("Wait for the current download to finish.")
            return
        self._cancel.clear()
        self._set_running(True)
        self.progress.set(0)
        self.progress_label.configure(text="Downloading ffmpeg...")
        folder = install_dir() / "ffmpeg"
        self._append_log(f"Downloading the latest ffmpeg release into {folder}")
        self._ffmpeg_thread = threading.Thread(target=self._run_ffmpeg_download, daemon=True)
        self._ffmpeg_thread.start()

    def _run_ffmpeg_download(self) -> None:
        def report(message: str, percent: float | None) -> None:
            self._events.put(UiMessage("progress", message, percent=percent))

        try:
            folder = download_latest_ffmpeg(
                install_dir(),
                report=report,
                cancelled=self._cancel.is_set,
            )
        except FfmpegDownloadCancelled:
            self._events.put(UiMessage("log", "ffmpeg download cancelled."))
            self._events.put(UiMessage("done", "Cancelled", ok=False))
            return
        except FfmpegDownloadError as exc:
            self._events.put(UiMessage("log", f"ERROR: {exc}"))
            self._events.put(UiMessage("done", str(exc), ok=False))
            return
        except Exception as exc:
            self._events.put(UiMessage("log", f"ERROR: {exc}"))
            self._events.put(UiMessage("done", str(exc), ok=False))
            return
        self._events.put(UiMessage("ffmpeg", str(folder)))
        self._events.put(UiMessage("log", f"ffmpeg installed: {folder}"))
        self._events.put(UiMessage("done", "ffmpeg installed", ok=True))

    def _use_installed_ffmpeg(self, folder: str) -> None:
        self._loading = True
        try:
            self.ffmpeg_var.set(folder)
        finally:
            self._loading = False
        self._save_form()
        self._refresh_ffmpeg_status()
        self._refresh_preview()

    def _busy(self) -> bool:
        return bool(
            (self._thread and self._thread.is_alive())
            or (self._ffmpeg_thread and self._ffmpeg_thread.is_alive())
        )

    def _start(self) -> None:
        if self._busy():
            return
        request = self._request()
        if not request.urls:
            self._append_log("Enter at least one URL.")
            return
        if not request.output_dir:
            self._append_log("Choose an output folder.")
            return
        try:
            plan = build_plan(request)
        except ValueError as exc:
            self._append_log(str(exc))
            return
        self._save_form()
        self._cancel.clear()
        self._set_running(True)
        self.progress.set(0)
        self.progress_label.configure(text="Starting...")
        self._thread = threading.Thread(target=self._run_job, args=(plan,), daemon=True)
        self._thread.start()

    def _run_job(self, plan) -> None:
        try:
            run_download(plan, self._events.put, self._cancel)
        except Exception as exc:
            self._events.put(UiMessage("log", f"ERROR: {exc}"))
            self._events.put(UiMessage("done", str(exc), ok=False))

    def _cancel_download(self) -> None:
        self._cancel.set()
        self._append_log("Cancelling...")
        self.cancel_button.configure(state="disabled")

    def _poll(self) -> None:
        try:
            while True:
                self._handle(self._events.get_nowait())
        except queue.Empty:
            pass
        if self.winfo_exists():
            self.after(100, self._poll)

    def _handle(self, message: UiMessage) -> None:
        if message.kind == "log":
            self._append_log(message.text)
            return
        if message.kind == "ffmpeg":
            self._use_installed_ffmpeg(message.text)
            return
        if message.kind == "progress":
            self.progress_label.configure(text=message.text)
            if message.percent is None:
                if not self._pulsing:
                    self.progress.configure(mode="indeterminate")
                    self.progress.start()
                    self._pulsing = True
            else:
                self._stop_pulse()
                self.progress.set(max(0.0, min(1.0, message.percent)))
            return
        if message.kind == "done":
            self._stop_pulse()
            if message.ok:
                self.progress.set(1)
            self.progress_label.configure(text=message.text or ("Finished" if message.ok else "Stopped"))
            self._set_running(False)

    def _stop_pulse(self) -> None:
        if not self._pulsing:
            return
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self._pulsing = False

    def _set_running(self, running: bool) -> None:
        self.download_button.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")
        self.get_ffmpeg_button.configure(state="disabled" if running else "normal")

    def _append_log(self, text: str) -> None:
        if not text:
            return
        if not text.endswith("\n"):
            text += "\n"
        self.console.insert("end", text)
        self.console.see("end")

    def _form_settings(self) -> dict:
        return {
            "output_dir": self.output_var.get().strip(),
            "ffmpeg_location": self.ffmpeg_var.get().strip(),
            "preset": self.preset_var.get(),
            "quality": self.quality_var.get(),
            "container": self.format_var.get(),
            "playlist": self.playlist_var.get(),
            "cookies_browser": self.cookies_var.get(),
            "overwrite": bool(self.overwrite_var.get()),
            "resume": bool(self.resume_var.get()),
            "normalize_filenames": bool(self.normalize_var.get()),
        }

    def _save_form(self) -> None:
        save_settings(self._form_settings())

    def _on_close(self) -> None:
        self._cancel.set()
        self._save_form()
        self.destroy()


def _keep_readonly(widget) -> None:
    """Allow selection and copy, and ignore typing."""

    def on_key(event):
        ctrl = (event.state & 0x4) != 0
        if ctrl and event.keysym.lower() in {"c", "a", "insert"}:
            return None
        if event.keysym in {
            "Left",
            "Right",
            "Up",
            "Down",
            "Home",
            "End",
            "Prior",
            "Next",
            "Shift_L",
            "Shift_R",
            "Control_L",
            "Control_R",
        }:
            return None
        return "break"

    widget.bind("<Key>", on_key)
    widget.bind("<<Paste>>", lambda _event: "break")
    widget.bind("<<Cut>>", lambda _event: "break")


def _mono_font() -> ctk.CTkFont:
    if sys.platform == "win32":
        family = "Consolas"
    elif sys.platform == "darwin":
        family = "Menlo"
    else:
        family = "DejaVu Sans Mono"
    return ctk.CTkFont(family=family, size=12)


def main() -> None:
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    app = App()
    app.mainloop()
