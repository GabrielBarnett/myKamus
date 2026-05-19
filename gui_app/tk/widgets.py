"""Reusable Tk widgets for shared GUI layout patterns."""

import tkinter as tk
from tkinter import ttk


class ScrollableFrame(ttk.Frame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self)

        self._content_window = self.canvas.create_window(
            (0, 0),
            window=self.content,
            anchor="nw",
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        self.content.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._resize_content_width)

    def _update_scroll_region(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_content_width(self, event):
        self.canvas.itemconfigure(self._content_window, width=event.width)


class SelectableText(tk.Text):
    def __init__(self, master, **kwargs):
        kwargs.setdefault("wrap", "word")
        kwargs.setdefault("borderwidth", 0)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("undo", False)
        super().__init__(master, **kwargs)

    def set_text(self, text):
        self.delete("1.0", "end")
        self.insert("1.0", text)


class SectionHeader(ttk.Frame):
    def __init__(self, master, title, subtitle=None, **kwargs):
        super().__init__(master, **kwargs)
        self.columnconfigure(0, weight=1)

        self.title_label = ttk.Label(self, text=title, style="SectionHeader.TLabel")
        self.title_label.grid(row=0, column=0, sticky="w")

        self.subtitle_label = None
        if subtitle:
            self.subtitle_label = ttk.Label(self, text=subtitle, style="Muted.TLabel")
            self.subtitle_label.grid(row=1, column=0, sticky="w", pady=(2, 0))
