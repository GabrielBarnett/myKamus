"""Reusable Tk widgets for shared GUI layout patterns."""

import tkinter as tk
from tkinter import ttk

from gui_app.tk.theme import resolve_style_color


class ScrollableFrame(ttk.Frame):
    def __init__(self, master, **kwargs):
        frame_style = kwargs.get("style", "TFrame")
        super().__init__(master, **kwargs)
        background = resolve_style_color(self, frame_style, "background")
        self.canvas = tk.Canvas(
            self,
            highlightthickness=0,
            borderwidth=0,
            background=background,
        )
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self, style=frame_style)

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


class SelectableText(ttk.Frame):
    def __init__(self, master, text="", **kwargs):
        frame_style = kwargs.pop("style", "App.TFrame")
        text_options = {
            "height": kwargs.pop("height", 4),
            "width": kwargs.pop("width", 40),
            "wrap": kwargs.pop("wrap", "word"),
        }
        super().__init__(master, style=frame_style, **kwargs)
        background = resolve_style_color(self, frame_style, "background")
        foreground = resolve_style_color(self, "TLabel", "foreground")

        self.text_widget = tk.Text(
            self,
            background=background,
            foreground=foreground,
            insertbackground=foreground,
            borderwidth=0,
            highlightthickness=0,
            undo=False,
            relief="flat",
            **text_options,
        )
        self.text_widget.pack(fill="both", expand=True)
        self.set_text(text)

    def set_text(self, text):
        self.text_widget.configure(state="normal")
        self.text_widget.delete("1.0", "end")
        self.text_widget.insert("1.0", text)
        self.text_widget.configure(state="disabled")


class SectionHeader(ttk.Frame):
    def __init__(self, master, title, subtitle=None, **kwargs):
        kwargs.setdefault("style", "App.TFrame")
        super().__init__(master, **kwargs)
        self.columnconfigure(0, weight=1)

        self.title_label = ttk.Label(self, text=title, style="SectionTitle.TLabel")
        self.title_label.grid(row=0, column=0, sticky="w")

        self.subtitle_label = None
        if subtitle:
            self.subtitle_label = ttk.Label(self, text=subtitle, style="Muted.TLabel")
            self.subtitle_label.grid(row=1, column=0, sticky="w", pady=(2, 0))
