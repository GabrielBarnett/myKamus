"""Tk loading screen for background indexing work."""

import tkinter as tk
from tkinter import StringVar, ttk

from gui_app.core.view_model import format_bytes
from gui_app.tk.theme import resolve_style_color


class LoadingView(ttk.Frame):
    def __init__(self, master, **kwargs):
        frame_style = kwargs.setdefault("style", "App.TFrame")
        super().__init__(master, padding=24, **kwargs)
        self.columnconfigure(0, weight=1)
        background = resolve_style_color(self, frame_style, "background")
        foreground = resolve_style_color(self, "TLabel", "foreground")
        muted_foreground = resolve_style_color(self, "Muted.TLabel", "foreground")
        title_foreground = resolve_style_color(self, "SectionTitle.TLabel", "foreground")
        title_font = ttk.Style(self).lookup("SectionTitle.TLabel", "font") or ("TkDefaultFont", 11, "bold")

        self.title_var = StringVar(value="Building search index...")
        self.percent_var = StringVar(value="0%")
        self.detail_var = StringVar(value="Preparing corpus...")
        self.status_var = StringVar(value="This only happens when the data changes.")

        self.title_label = tk.Label(
            self,
            textvariable=self.title_var,
            background=background,
            foreground=title_foreground,
            font=title_font,
            anchor="w",
        )
        self.percent_label = tk.Label(
            self,
            textvariable=self.percent_var,
            background=background,
            foreground=foreground,
            anchor="w",
        )
        self.progress_bar = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.detail_label = tk.Label(
            self,
            textvariable=self.detail_var,
            background=background,
            foreground=muted_foreground,
            anchor="w",
        )
        self.status_label = tk.Label(
            self,
            textvariable=self.status_var,
            background=background,
            foreground=muted_foreground,
            anchor="w",
        )

        self.title_label.grid(row=0, column=0, sticky="w")
        self.percent_label.grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.progress_bar.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.detail_label.grid(row=3, column=0, sticky="w", pady=(8, 0))
        self.status_label.grid(row=4, column=0, sticky="w", pady=(4, 0))

    def update_progress(self, progress):
        percent = max(0.0, min(100.0, float(progress.get("percent", 0.0))))
        self.title_var.set(progress.get("title", "Building search index..."))
        self.percent_var.set(f"{percent:.0f}%")
        self.progress_bar.configure(value=int(round(percent)))
        self.detail_var.set(self._build_detail_text(progress))
        self.status_var.set(progress.get("status", self.status_var.get()))

    def show_error(self):
        self.status_var.set("Index build failed. Searches will use fallback mode.")

    def show_ready(self):
        self.percent_var.set("100%")
        self.progress_bar.configure(value=100)
        self.status_var.set("Search index ready.")

    def _build_detail_text(self, progress):
        processed_pages = progress.get("processed_pages")
        total_pages = progress.get("total_pages")
        if processed_pages is not None and total_pages is not None:
            return "Processed page " + str(processed_pages) + " of " + str(total_pages)

        processed_bytes = self._coerce_byte_count(progress.get("processed_bytes"))
        total_bytes = self._coerce_byte_count(progress.get("total_bytes"))
        return "Processed " + format_bytes(processed_bytes) + " of " + format_bytes(total_bytes)

    def _coerce_byte_count(self, value):
        if value is None:
            return 0
        return int(value)
