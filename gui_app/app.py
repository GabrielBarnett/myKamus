import json
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pyperclip

from search_functions import (
    ensure_red_book_index,
    ensure_sentence_index,
    format_red_book_block,
    format_red_book_definition_block,
    format_sentence_block,
    is_red_book_index_valid,
    is_sentence_index_valid,
    load_config,
    search_for_word_data,
)


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"


def resolve_sentence_limit(config, compact_mode, load_all):
    if load_all:
        gui_config = config.get("gui", {})
        return gui_config.get("load_all_sentence_limit", 200)
    if compact_mode:
        return 1
    return config.get("sentence_limit")


def should_refocus_search(origin):
    return origin in {"manual", "load_all"}


def format_bytes(byte_count):
    if byte_count >= 1024 * 1024:
        return f"{byte_count / (1024 * 1024):.1f} MB"
    if byte_count >= 1024:
        return f"{byte_count / 1024:.1f} KB"
    return str(byte_count) + " bytes"


def indexes_are_ready():
    return is_sentence_index_valid() and is_red_book_index_valid()


class MyKamusGUI:
    def __init__(self, root):
        self.root = root
        self.config = load_config()
        self.gui_config = self.config.get("gui", {})
        self.clipboard_value = pyperclip.paste()
        self.paused = False
        self.closed = False
        self.main_ui_ready = False
        self.polling_started = False
        self.search_generation = 0
        self.search_status_after_id = None
        self.poll_interval_ms = int(self.config.get("poll_interval", 0.1) * 1000)

        self.root.title("myKamus GUI")
        self.root.minsize(700, 500)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        if indexes_are_ready():
            self._show_main_ui()
        else:
            self._build_loading_ui()
            self._start_index_build()

    def _show_main_ui(self):
        if self.closed:
            return
        if self.main_ui_ready:
            return
        if hasattr(self, "loading_frame") and self.loading_frame is not None:
            self.loading_frame.destroy()
            self.loading_frame = None
        self._build_ui()
        self._apply_window_settings()
        self.main_ui_ready = True
        self._update_clipboard_label(self.clipboard_value)
        self._run_search(self.clipboard_value, origin="startup")
        self._focus_search_entry(select_text=True)
        if not self.polling_started:
            self.polling_started = True
            self._poll_clipboard()

    def _build_loading_ui(self):
        self.loading_frame = ttk.Frame(self.root, padding=24)
        self.loading_frame.grid(row=0, column=0, sticky="nsew")
        self.loading_frame.columnconfigure(0, weight=1)

        self.loading_title_var = tk.StringVar(value="Building search index...")
        ttk.Label(
            self.loading_frame,
            textvariable=self.loading_title_var,
            font=("Segoe UI", 14, "bold"),
        ).grid(row=0, column=0, sticky="w")

        self.loading_percent_var = tk.StringVar(value="0%")
        self.loading_detail_var = tk.StringVar(value="Preparing sentence corpus...")
        self.loading_status_var = tk.StringVar(value="This only happens when the corpus changes.")
        self.loading_progress_var = tk.DoubleVar(value=0.0)

        ttk.Label(self.loading_frame, textvariable=self.loading_percent_var).grid(
            row=1,
            column=0,
            sticky="w",
            pady=(16, 4),
        )
        ttk.Progressbar(
            self.loading_frame,
            orient="horizontal",
            mode="determinate",
            maximum=100,
            variable=self.loading_progress_var,
        ).grid(row=2, column=0, sticky="ew")
        ttk.Label(self.loading_frame, textvariable=self.loading_detail_var).grid(
            row=3,
            column=0,
            sticky="w",
            pady=(8, 0),
        )
        ttk.Label(self.loading_frame, textvariable=self.loading_status_var).grid(
            row=4,
            column=0,
            sticky="w",
            pady=(4, 0),
        )

    def _start_index_build(self):
        thread = threading.Thread(target=self._index_worker, daemon=True)
        thread.start()

    def _index_worker(self):
        def progress_callback(progress):
            try:
                self.root.after(0, lambda p=progress: self._update_index_progress(p))
            except tk.TclError:
                pass

        try:
            ensure_sentence_index(
                progress_callback=lambda progress: progress_callback(
                    {
                        **progress,
                        "title": "Building sentence search index...",
                    }
                )
            )
            ensure_red_book_index(
                progress_callback=lambda progress: progress_callback(
                    {
                        **progress,
                        "title": "Building Red Book index...",
                    }
                )
            )
            error = None
        except Exception as exc:  # pragma: no cover - defensive UI boundary
            error = exc

        try:
            self.root.after(0, lambda: self._finish_index_build(error))
        except tk.TclError:
            pass

    def _update_index_progress(self, progress):
        if self.closed or self.main_ui_ready:
            return
        percent = progress.get("percent", 0.0)
        processed_bytes = progress.get("processed_bytes", 0)
        total_bytes = progress.get("total_bytes", 0)
        processed_pages = progress.get("processed_pages")
        total_pages = progress.get("total_pages")
        if progress.get("title"):
            self.loading_title_var.set(progress["title"])
        self.loading_progress_var.set(percent)
        self.loading_percent_var.set(f"{percent:.0f}%")
        if processed_pages is not None and total_pages is not None:
            self.loading_detail_var.set(
                "Processed page "
                + str(processed_pages)
                + " of "
                + str(total_pages)
            )
        else:
            self.loading_detail_var.set(
                "Processed "
                + format_bytes(processed_bytes)
                + " of "
                + format_bytes(total_bytes)
            )

    def _finish_index_build(self, error):
        if self.closed or self.main_ui_ready:
            return
        if error is not None:
            self.loading_status_var.set(
                "Index build failed. Searches will use the slower fallback."
            )
            self.root.after(1500, self._show_main_ui)
            return
        self.loading_progress_var.set(100)
        self.loading_percent_var.set("100%")
        self.loading_status_var.set("Search index ready.")
        self.root.after(250, self._show_main_ui)

    def _build_ui(self):
        container = ttk.Frame(self.root, padding=12)
        container.grid(row=0, column=0, sticky="nsew")

        top_frame = ttk.Frame(container)
        top_frame.grid(row=0, column=0, sticky="ew")
        top_frame.columnconfigure(1, weight=1)

        ttk.Label(top_frame, text="Clipboard term:").grid(row=0, column=0, sticky="w")
        self.clipboard_label = ttk.Label(top_frame, text="", font=("Segoe UI", 11, "bold"))
        self.clipboard_label.grid(row=0, column=1, sticky="w", padx=(8, 0))

        controls_frame = ttk.Frame(container)
        controls_frame.grid(row=1, column=0, sticky="ew", pady=(12, 6))
        controls_frame.columnconfigure(1, weight=1)

        ttk.Label(controls_frame, text="Manual search:").grid(row=0, column=0, sticky="w")
        self.search_entry = ttk.Entry(controls_frame)
        self.search_entry.grid(row=0, column=1, sticky="ew", padx=(8, 8))
        self.search_entry.bind("<Return>", self._on_manual_search)

        self.search_button = ttk.Button(
            controls_frame,
            text="Search",
            command=self._on_manual_search,
        )
        self.search_button.grid(row=0, column=2, sticky="ew")

        buttons_frame = ttk.Frame(container)
        buttons_frame.grid(row=2, column=0, sticky="ew", pady=(6, 6))

        self.pause_button = ttk.Button(
            buttons_frame,
            text="Pause monitoring",
            command=self._toggle_pause,
        )
        self.pause_button.grid(row=0, column=0, padx=(0, 8))

        self.load_all_button = ttk.Button(
            buttons_frame,
            text="Load all sentences",
            command=self._on_load_all,
        )
        self.load_all_button.grid(row=0, column=1, padx=(0, 8))

        self.always_on_top_var = tk.BooleanVar(value=self.gui_config.get("always_on_top", True))
        self.compact_mode_var = tk.BooleanVar(value=self.gui_config.get("compact_mode", False))

        ttk.Checkbutton(
            buttons_frame,
            text="Always on top",
            variable=self.always_on_top_var,
            command=self._toggle_always_on_top,
        ).grid(row=0, column=2, padx=(0, 8))

        ttk.Checkbutton(
            buttons_frame,
            text="Compact mode",
            variable=self.compact_mode_var,
            command=self._on_compact_mode,
        ).grid(row=0, column=3, padx=(0, 8))

        results_frame = ttk.Frame(container)
        results_frame.grid(row=3, column=0, sticky="nsew")
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        container.rowconfigure(3, weight=1)

        self.results_text = tk.Text(
            results_frame,
            wrap="word",
            font=("Segoe UI", 10),
            height=20,
        )
        self.results_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.results_text.configure(yscrollcommand=scrollbar.set)

        self.status_label = ttk.Label(container, text="", anchor="w")
        self.status_label.grid(row=4, column=0, sticky="ew", pady=(6, 0))

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_window_settings(self):
        window_size = self.gui_config.get("window_size", "900x700")
        window_position = self.gui_config.get("window_position", "+100+100")
        self.root.geometry(f"{window_size}{window_position}")
        self.root.attributes("-topmost", self.always_on_top_var.get())

    def _toggle_always_on_top(self):
        self.root.attributes("-topmost", self.always_on_top_var.get())
        self._set_status("Always on top: " + ("on" if self.always_on_top_var.get() else "off"))

    def _toggle_pause(self):
        self.paused = not self.paused
        self.pause_button.configure(
            text="Resume monitoring" if self.paused else "Pause monitoring"
        )
        self._set_status("Monitoring paused." if self.paused else "Monitoring resumed.")

    def _on_compact_mode(self):
        self._set_status("Compact mode: " + ("on" if self.compact_mode_var.get() else "off"))
        self._run_search(self.clipboard_value, origin="control")

    def _on_manual_search(self, event=None):
        query = self.search_entry.get().strip()
        self._update_clipboard_label(query or self.clipboard_value)
        self._run_search(query, origin="manual")

    def _on_load_all(self):
        query = self.search_entry.get().strip() or self.clipboard_value
        self._update_clipboard_label(query)
        self._run_search(query, load_all=True, origin="load_all")

    def _update_clipboard_label(self, text):
        display = text.strip() if text else "(empty)"
        self.clipboard_label.configure(text=display)

    def _poll_clipboard(self):
        if not self.paused:
            current = pyperclip.paste()
            if current != self.clipboard_value:
                self.clipboard_value = current
                self._update_clipboard_label(current)
                self._run_search(current, origin="clipboard")
        self.root.after(self.poll_interval_ms, self._poll_clipboard)

    def _run_search(self, query, load_all=False, origin="manual"):
        sentence_limit = resolve_sentence_limit(
            self.config,
            self.compact_mode_var.get(),
            load_all,
        )
        self.search_generation += 1
        generation = self.search_generation
        self._schedule_searching_status(generation)
        thread = threading.Thread(
            target=self._search_worker,
            args=(generation, query, sentence_limit, load_all, origin),
            daemon=True,
        )
        thread.start()

    def _schedule_searching_status(self, generation):
        if self.search_status_after_id is not None:
            self.root.after_cancel(self.search_status_after_id)
            self.search_status_after_id = None
        delay_ms = int(self.gui_config.get("search_status_delay_ms", 200))
        if delay_ms <= 0:
            self._show_searching_status(generation)
            return
        self.search_status_after_id = self.root.after(
            delay_ms,
            lambda: self._show_searching_status(generation),
        )

    def _show_searching_status(self, generation):
        if self.closed or generation != self.search_generation:
            return
        self.search_status_after_id = None
        self._set_status("Searching...")

    def _cancel_searching_status(self):
        if self.search_status_after_id is not None:
            self.root.after_cancel(self.search_status_after_id)
            self.search_status_after_id = None

    def _search_worker(self, generation, query, sentence_limit, load_all, origin):
        try:
            result = search_for_word_data(query, sentence_limit=sentence_limit)
            error = None
        except Exception as exc:  # pragma: no cover - defensive UI boundary
            result = None
            error = exc

        def finish():
            self._finish_search(generation, result, error, load_all, origin)

        try:
            self.root.after(0, finish)
        except tk.TclError:
            pass

    def _finish_search(self, generation, result, error, load_all, origin):
        if self.closed or generation != self.search_generation:
            return
        self._cancel_searching_status()
        if error is not None:
            self.results_text.configure(state="normal")
            self.results_text.delete("1.0", tk.END)
            self.results_text.insert(tk.END, "Search failed: " + str(error) + "\n")
            self.results_text.configure(state="disabled")
            self._set_status("Search failed.")
            self._restore_search_entry_focus(origin)
            return
        self._render_results(result, load_all=load_all)
        self._restore_search_entry_focus(origin)

    def _render_results(self, result, load_all=False):
        self.results_text.configure(state="normal")
        self.results_text.delete("1.0", tk.END)

        if result["message"]:
            self.results_text.insert(tk.END, result["message"] + "\n")
            self.results_text.configure(state="disabled")
            self._set_status(result["message"])
            return

        query = result["query"].casefold()
        self.results_text.insert(tk.END, f"Word translations for {query}:\n")
        if result["definitions"]:
            for index, line in enumerate(result["definitions"], start=1):
                self.results_text.insert(tk.END, f"{index}: {line}\n")
        else:
            self.results_text.insert(tk.END, "No dictionary entries found.\n")

        if result.get("red_book_definitions") or result.get("red_book_results"):
            self.results_text.insert(tk.END, "\nRed Book Results:\n")
            next_index = 1
            for index, red_book_definition in enumerate(
                result.get("red_book_definitions", []),
                start=next_index,
            ):
                block = format_red_book_definition_block(index, red_book_definition)
                self.results_text.insert(tk.END, block + "\n\n")
                next_index = index + 1
            for index, red_book_result in enumerate(
                result["red_book_results"],
                start=next_index,
            ):
                block = format_red_book_block(index, red_book_result)
                self.results_text.insert(tk.END, block + "\n\n")

        self.results_text.insert(tk.END, "\n")
        header = "All example sentences" if load_all else "Example sentences"
        self.results_text.insert(tk.END, f"{header} for {query}:\n")
        if result["sentences"]:
            for sentence in result["sentences"]:
                block = format_sentence_block(
                    sentence["index"],
                    sentence["match"],
                    sentence["translation"],
                )
                self.results_text.insert(tk.END, block + "\n\n")
        else:
            self.results_text.insert(tk.END, "No example sentences found.\n")

        self.results_text.configure(state="disabled")
        if result["sentences_truncated"]:
            self._set_status(
                "Showing the first "
                + str(result["sentence_limit"])
                + " matching sentence pairs. Narrow the query for fewer results."
            )
        elif load_all:
            self._set_status(
                "Loaded " + str(len(result["sentences"])) + " matching sentence pairs."
            )
        else:
            self._set_status(
                "Found "
                + str(len(result["definitions"]))
                + " dictionary entries and "
                + str(
                    len(result.get("red_book_definitions", []))
                    + len(result.get("red_book_results", []))
                )
                + " Red Book results and "
                + str(len(result["sentences"]))
                + " sentence pairs."
            )

    def _set_status(self, message):
        self.status_label.configure(text=message)

    def _focus_search_entry(self, select_text=False):
        if not self.main_ui_ready:
            return
        self.search_entry.focus_set()
        if select_text:
            self.search_entry.selection_range(0, tk.END)
            self.search_entry.icursor(tk.END)

    def _restore_search_entry_focus(self, origin):
        if not should_refocus_search(origin):
            return
        self.root.after_idle(lambda: self._focus_search_entry(select_text=True))

    def _on_close(self):
        self.closed = True
        self._cancel_searching_status()
        if not self.main_ui_ready:
            self.root.destroy()
            return
        window_size = f"{self.root.winfo_width()}x{self.root.winfo_height()}"
        window_position = f"+{self.root.winfo_x()}+{self.root.winfo_y()}"
        config = dict(self.config)
        gui_config = dict(self.config.get("gui", {}))
        gui_config.update({
            "always_on_top": self.always_on_top_var.get(),
            "compact_mode": self.compact_mode_var.get(),
            "window_size": window_size,
            "window_position": window_position,
        })
        config["gui"] = gui_config
        with CONFIG_PATH.open("w", encoding="utf-8") as config_file:
            json.dump(config, config_file, indent=2)
            config_file.write("\n")
        self.root.destroy()


def main():
    root = tk.Tk()
    ttk.Style().theme_use("clam")
    MyKamusGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
