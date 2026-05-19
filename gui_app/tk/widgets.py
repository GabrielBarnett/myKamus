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
        self._scrollbar_visible = False
        self._refresh_after_id = None

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
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.text_widget.yview)
        self.text_widget.configure(yscrollcommand=self._sync_scrollbar)
        self.text_widget.pack(side="left", fill="both", expand=True)
        self.text_widget.bind("<Configure>", self._queue_scrollbar_refresh)
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.set_text(text)

    def set_text(self, text):
        self.text_widget.configure(state="normal")
        self.text_widget.delete("1.0", "end")
        self.text_widget.insert("1.0", text)
        self.text_widget.configure(state="disabled")
        self._queue_scrollbar_refresh()

    def _queue_scrollbar_refresh(self, _event=None):
        if self._refresh_after_id is not None:
            try:
                self.after_cancel(self._refresh_after_id)
            except tk.TclError:
                pass
        self._refresh_after_id = self.after_idle(self._refresh_scrollbar)

    def _refresh_scrollbar(self):
        self._refresh_after_id = None
        if not self.winfo_exists():
            return
        first, last = self.text_widget.yview()
        self._set_scrollbar_visibility(last < 1.0 or first > 0.0)

    def _sync_scrollbar(self, first, last):
        self.scrollbar.set(first, last)
        self._set_scrollbar_visibility(float(last) < 1.0 or float(first) > 0.0)

    def _set_scrollbar_visibility(self, visible):
        if visible and not self._scrollbar_visible:
            self.scrollbar.pack(side="right", fill="y")
            self._scrollbar_visible = True
        elif not visible and self._scrollbar_visible:
            self.scrollbar.pack_forget()
            self._scrollbar_visible = False

    def _on_destroy(self, event):
        if event.widget is not self:
            return
        if self._refresh_after_id is not None:
            try:
                self.after_cancel(self._refresh_after_id)
            except tk.TclError:
                pass
            self._refresh_after_id = None


class SectionHeader(ttk.Frame):
    def __init__(self, master, title, subtitle=None, **kwargs):
        frame_style = kwargs.setdefault("style", "App.TFrame")
        super().__init__(master, **kwargs)
        self.columnconfigure(0, weight=1)
        background = resolve_style_color(self, frame_style, "background")
        title_foreground = resolve_style_color(self, "SectionTitle.TLabel", "foreground")
        subtitle_foreground = resolve_style_color(self, "Muted.TLabel", "foreground")
        title_font = ttk.Style(self).lookup("SectionTitle.TLabel", "font") or ("TkDefaultFont", 11, "bold")

        self.title_label = tk.Label(
            self,
            text=title,
            background=background,
            foreground=title_foreground,
            font=title_font,
            anchor="w",
        )
        self.title_label.grid(row=0, column=0, sticky="w")

        self.subtitle_label = None
        if subtitle is not None:
            self.subtitle_label = tk.Label(
                self,
                text=str(subtitle),
                background=background,
                foreground=subtitle_foreground,
                anchor="w",
            )
            self.subtitle_label.grid(row=1, column=0, sticky="w", pady=(2, 0))
