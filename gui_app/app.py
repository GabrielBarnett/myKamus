import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import pyperclip

from search_functions import (
    format_sentence_block,
    load_config,
    load_data,
    search_for_word_data,
)


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"


class MyKamusGUI:
    def __init__(self, root):
        self.root = root
        self.config = load_config()
        self.gui_config = self.config.get("gui", {})
        self.clipboard_value = pyperclip.paste()
        self.paused = False
        # Convert seconds to milliseconds for tkinter's scheduling.
        self.poll_interval_ms = int(self.config.get("poll_interval", 0.1) * 1000)

        self._build_ui()
        self._apply_window_settings()
        load_data()
        self._update_clipboard_label(self.clipboard_value)
        self._run_search(self.clipboard_value)
        self._poll_clipboard()

    def _build_ui(self):
        self.root.title("myKamus GUI")
        self.root.minsize(700, 500)

        container = ttk.Frame(self.root, padding=12)
        container.grid(row=0, column=0, sticky="nsew")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

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
        self._run_search(self.clipboard_value)

    def _on_manual_search(self, event=None):
        query = self.search_entry.get().strip()
        self._update_clipboard_label(query or self.clipboard_value)
        self._run_search(query)

    def _on_load_all(self):
        query = self.search_entry.get().strip() or self.clipboard_value
        self._update_clipboard_label(query)
        self._run_search(query, load_all=True)

    def _update_clipboard_label(self, text):
        display = text.strip() if text else "(empty)"
        self.clipboard_label.configure(text=display)

    def _poll_clipboard(self):
        if not self.paused:
            current = pyperclip.paste()
            if current != self.clipboard_value:
                self.clipboard_value = current
                self._update_clipboard_label(current)
                self._run_search(current)
        # Schedule the next poll; tkinter uses a single-threaded event loop.
        self.root.after(self.poll_interval_ms, self._poll_clipboard)

    def _run_search(self, query, load_all=False):
        if self.compact_mode_var.get() and not load_all:
            # Compact mode caps results to keep the UI minimal.
            sentence_limit = 1
        else:
            sentence_limit = None if load_all else self.config.get("sentence_limit")
        result = search_for_word_data(query, sentence_limit=sentence_limit)
        self._render_results(result, load_all=load_all)

    def _render_results(self, result, load_all=False):
        self.results_text.configure(state="normal")
        self.results_text.delete("1.0", tk.END)

        if result["message"]:
            self.results_text.insert(tk.END, result["message"] + "\n")
            self.results_text.configure(state="disabled")
            return

        query = result["query"].casefold()
        self.results_text.insert(tk.END, f"Word translations for {query}:\n")
        if result["definitions"]:
            for index, line in enumerate(result["definitions"], start=1):
                self.results_text.insert(tk.END, f"{index}: {line}\n")
        else:
            self.results_text.insert(tk.END, "No dictionary entries found.\n")

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

    def _set_status(self, message):
        self.status_label.configure(text=message)

    def _on_close(self):
        window_size = f"{self.root.winfo_width()}x{self.root.winfo_height()}"
        window_position = f"+{self.root.winfo_x()}+{self.root.winfo_y()}"
        config = dict(self.config)
        config["gui"] = {
            "always_on_top": self.always_on_top_var.get(),
            "compact_mode": self.compact_mode_var.get(),
            "window_size": window_size,
            "window_position": window_position,
        }
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
