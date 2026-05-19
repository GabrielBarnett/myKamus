"""Tk loading screen for background indexing work."""

from tkinter import StringVar, ttk

from gui_app.core.view_model import format_bytes


class LoadingView(ttk.Frame):
    def __init__(self, master, **kwargs):
        kwargs.setdefault("style", "App.TFrame")
        super().__init__(master, padding=24, **kwargs)
        self.columnconfigure(0, weight=1)

        self.title_var = StringVar(value="Building search index...")
        self.percent_var = StringVar(value="0%")
        self.detail_var = StringVar(value="Preparing corpus...")
        self.status_var = StringVar(value="This only happens when the data changes.")

        self.title_label = ttk.Label(self, textvariable=self.title_var, style="SectionTitle.TLabel")
        self.percent_label = ttk.Label(self, textvariable=self.percent_var)
        self.progress_bar = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.detail_label = ttk.Label(self, textvariable=self.detail_var, style="Muted.TLabel")
        self.status_label = ttk.Label(self, textvariable=self.status_var, style="Muted.TLabel")

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

        processed_bytes = int(progress.get("processed_bytes", 0))
        total_bytes = int(progress.get("total_bytes", 0))
        return "Processed " + format_bytes(processed_bytes) + " of " + format_bytes(total_bytes)
