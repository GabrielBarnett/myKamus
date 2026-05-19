"""Main Tk window shell for the myKamus desktop app."""

import queue
import tkinter as tk
from tkinter import StringVar, ttk

from gui_app.core.config_store import build_gui_config_update, write_config
from gui_app.core.view_model import (
    add_search_history,
    build_result_view_model,
    parse_window_position,
    parse_window_size,
    resolve_sentence_limit,
    should_refocus_search,
    should_use_narrow_layout,
    status_text_for_result,
)
from gui_app.runtime.tasks import BackgroundTaskRunner
from gui_app.tk.loading_view import LoadingView
from gui_app.tk.theme import apply_theme
from gui_app.tk.widgets import ScrollableFrame, SectionHeader, SelectableText


class MyKamusTkWindow(ttk.Frame):
    def __init__(self, root, backend):
        self.root = root
        self.backend = backend
        self.config = backend.load_config() or {}
        self.gui_config = self.config.get("gui", {})
        self.config_path = getattr(backend, "config_path", None)
        self.message_queue = queue.Queue()
        self.task_runner = BackgroundTaskRunner(self.message_queue)
        self.style = apply_theme(root)
        self.tools_visible = False
        self.loading_view = None
        self.search_generation = 0
        self.pending_searches = {}
        self.narrow_layout = None
        self._message_after_id = None
        self._clipboard_after_id = None

        self.command_frame = None
        self.search_entry = None
        self.search_button = None
        self.tools_button = None
        self.status_var = StringVar(value="Ready.")
        self.status_label = None
        self.recent_row_frame = None
        self.body_frame = None
        self.tools_panel = None
        self.results_frame = None
        self.results_content = None
        self.search_history = []
        self.clipboard_value = ""
        self.compact_mode_var = None
        self.always_on_top_var = None

        self._configure_window()

        super().__init__(root, style="App.TFrame", padding=16)
        self.columnconfigure(0, weight=1)
        self.pack(fill="both", expand=True)

        if self.backend.indexes_are_ready():
            self.build_main_ui()
        else:
            self.show_loading_view()

    def _configure_window(self):
        width, height = parse_window_size(self.gui_config.get("window_size"))
        x_pos, y_pos = parse_window_position(self.gui_config.get("window_position"))
        self.root.title("myKamus")
        self.root.minsize(520, 420)
        self.root.geometry(f"{width}x{height}+{x_pos}+{y_pos}")

    def show_loading_view(self):
        self.loading_view = LoadingView(self, style="App.TFrame")
        self.loading_view.pack(fill="both", expand=True)

    def build_main_ui(self):
        if self.loading_view is not None:
            self.loading_view.destroy()
            self.loading_view = None

        self.rowconfigure(3, weight=1)

        self.command_frame = ttk.Frame(self, style="App.TFrame")
        self.command_frame.grid(row=0, column=0, sticky="ew")
        self.command_frame.columnconfigure(0, weight=1)

        self.search_entry = ttk.Entry(self.command_frame)
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.search_button = ttk.Button(
            self.command_frame,
            text="Search",
            style="Primary.TButton",
        )
        self.search_button.grid(row=0, column=1, sticky="ew", padx=(0, 8))

        self.tools_button = ttk.Button(
            self.command_frame,
            text="Tools",
            style="Tool.TButton",
            command=self.toggle_tools,
        )
        self.tools_button.grid(row=0, column=2, sticky="ew")

        self.status_label = ttk.Label(
            self,
            textvariable=self.status_var,
            style="Muted.TLabel",
        )
        self.status_label.grid(row=1, column=0, sticky="w", pady=(10, 0))

        self.recent_row_frame = ttk.Frame(self, style="App.TFrame")
        self.recent_row_frame.grid(row=2, column=0, sticky="ew", pady=(12, 0))

        self.body_frame = ttk.Frame(self, style="App.TFrame")
        self.body_frame.grid(row=3, column=0, sticky="nsew", pady=(16, 0))
        self.body_frame.columnconfigure(1, weight=1)
        self.body_frame.rowconfigure(0, weight=1)

        self.tools_panel = ttk.Frame(self.body_frame, style="Surface.TFrame", padding=12)

        self.results_frame = ScrollableFrame(self.body_frame, style="Surface.TFrame")
        self.results_frame.grid(row=0, column=1, sticky="nsew")

        self.search_history = []
        self.clipboard_value = self.read_clipboard()
        self.compact_mode_var = tk.BooleanVar(value=self.gui_config.get("compact_mode", False))
        self.always_on_top_var = tk.BooleanVar(value=self.gui_config.get("always_on_top", True))
        self.results_content = self.results_frame.content
        self.results_content.columnconfigure(0, weight=1)
        self.search_button.configure(command=self.on_manual_search)
        self.root.bind("<Return>", self.on_manual_search)
        self.root.bind("<Escape>", self.clear_search)
        self.root.bind("<Control-l>", lambda event: self.focus_search(select_text=True))
        self.root.bind("<Control-L>", lambda event: self.focus_search(select_text=True))
        self.root.bind("<Control-f>", lambda event: self.focus_search(select_text=True))
        self.root.bind("<Control-F>", lambda event: self.focus_search(select_text=True))
        self.root.bind("<Configure>", self.on_resize)
        self.root.bind("<Destroy>", self._on_root_destroy, add="+")
        self.drain_messages()
        self._clipboard_after_id = self.root.after(
            max(100, int(float(self.config.get("poll_interval", 0.1)) * 1000)),
            self.poll_clipboard_loop,
        )
        self.apply_window_settings()
        self.run_search(self.clipboard_value, origin="startup")

    def toggle_tools(self):
        if self.tools_panel is None:
            return
        if self.tools_visible:
            self.tools_panel.grid_remove()
            self.tools_visible = False
        else:
            self.tools_panel.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
            self.tools_visible = True

    def read_clipboard(self):
        try:
            return self.root.clipboard_get()
        except tk.TclError:
            return ""

    def on_manual_search(self, _event=None):
        query = self.search_entry.get().strip()
        self.run_search(query, origin="manual")
        return "break"

    def clear_search(self, _event=None):
        self.search_entry.delete(0, "end")
        return self.focus_search(select_text=False)

    def focus_search(self, select_text=False):
        if self.search_entry is None:
            return "break"
        self.search_entry.focus_set()
        self.search_entry.icursor("end")
        if select_text and self.search_entry.get():
            self.search_entry.selection_range(0, "end")
        else:
            self.search_entry.selection_clear()
        return "break"

    def poll_clipboard_loop(self):
        self.poll_clipboard()
        self._clipboard_after_id = self.root.after(
            max(100, int(float(self.config.get("poll_interval", 0.1)) * 1000)),
            self.poll_clipboard_loop,
        )

    def poll_clipboard(self):
        current_value = self.read_clipboard()
        if current_value != self.clipboard_value:
            self.clipboard_value = current_value
            self.run_search(current_value, origin="clipboard")

    def run_search(self, query, load_all=False, origin="manual"):
        sentence_limit = resolve_sentence_limit(
            self.config,
            self.compact_mode_var.get(),
            load_all,
        )
        self.search_generation += 1
        token = self.search_generation
        self.pending_searches[token] = {
            "load_all": load_all,
            "origin": origin,
        }
        self.status_var.set("Searching...")

        def search_target(_cancel_event, _emit_progress):
            return self.backend.search(query, sentence_limit)

        self.task_runner.start(token=token, kind="search", target=search_target)
        self._schedule_drain_messages(idle=True)

    def _schedule_drain_messages(self, delay_ms=100, idle=False):
        if self._message_after_id is not None:
            try:
                self.root.after_cancel(self._message_after_id)
            except tk.TclError:
                pass
            self._message_after_id = None
        if idle:
            self._message_after_id = self.root.after_idle(self._drain_messages_callback)
        else:
            self._message_after_id = self.root.after(delay_ms, self._drain_messages_callback)

    def _drain_messages_callback(self):
        self._message_after_id = None
        self.drain_messages()

    def _on_root_destroy(self, event):
        if event.widget is not self.root:
            return
        if self._message_after_id is not None:
            try:
                self.root.after_cancel(self._message_after_id)
            except tk.TclError:
                pass
            self._message_after_id = None
        if self._clipboard_after_id is not None:
            try:
                self.root.after_cancel(self._clipboard_after_id)
            except tk.TclError:
                pass
            self._clipboard_after_id = None
        self.task_runner.cancel_all()

    def drain_messages(self):
        processed_any = False
        while True:
            try:
                message = self.message_queue.get_nowait()
            except queue.Empty:
                break

            processed_any = True
            if message.get("kind") != "search":
                continue

            token = message.get("token")
            search_options = self.pending_searches.pop(
                token,
                {"load_all": False, "origin": "manual"},
            )
            event = message.get("event")
            payload = message.get("payload") or {}
            if event == "result":
                self.finish_search(
                    token,
                    payload,
                    error=None,
                    load_all=search_options["load_all"],
                    origin=search_options["origin"],
                )
            elif event == "error":
                self.finish_search(
                    token,
                    None,
                    error=payload.get("error", "Search failed."),
                    load_all=search_options["load_all"],
                    origin=search_options["origin"],
                )

        if processed_any:
            self._schedule_drain_messages(idle=True)
        else:
            self._schedule_drain_messages()

    def finish_search(self, token, result, error=None, load_all=False, origin="manual"):
        if token != self.search_generation:
            return
        if error is not None:
            self.render_results(
                {
                    "message": "Search failed: " + str(error),
                    "sections": [],
                }
            )
            self.status_var.set("Search failed.")
            if should_refocus_search(origin):
                self.focus_search(select_text=True)
            return

        if origin in {"manual", "button", "load_all", "history"}:
            self.search_history = add_search_history(self.search_history, result["query"])
            self._render_history()

        view_model = build_result_view_model(result, load_all=load_all)
        self.render_results(view_model)
        self.status_var.set(status_text_for_result(view_model, load_all=load_all))
        if should_refocus_search(origin):
            self.focus_search(select_text=True)

    def _render_history(self):
        for child in self.recent_row_frame.winfo_children():
            child.destroy()

        for column_index, query in enumerate(self.search_history):
            history_button = ttk.Button(
                self.recent_row_frame,
                text=query,
                style="Tool.TButton",
                command=lambda value=query: self._run_history_search(value),
            )
            history_button.grid(row=0, column=column_index, sticky="w", padx=(0, 8))

    def _run_history_search(self, query):
        self.search_entry.delete(0, "end")
        self.search_entry.insert(0, query)
        self.run_search(query, origin="history")

    def render_results(self, model):
        for child in self.results_content.winfo_children():
            child.destroy()

        if model.get("message"):
            message_label = ttk.Label(
                self.results_content,
                text=model["message"],
                style="Muted.TLabel",
                wraplength=640,
                justify="left",
            )
            message_label.grid(row=0, column=0, sticky="w", padx=12, pady=12)
            return

        row_index = 0
        for section in model.get("sections", []):
            section_header = SectionHeader(
                self.results_content,
                title=section["title"],
                subtitle=len(section.get("items", [])),
                style="Surface.TFrame",
            )
            section_header.grid(row=row_index, column=0, sticky="ew", padx=12, pady=(12, 6))
            row_index += 1

            items = section.get("items", [])
            if not items:
                empty_label = ttk.Label(
                    self.results_content,
                    text=section.get("empty_text", ""),
                    style="Muted.TLabel",
                    wraplength=640,
                    justify="left",
                )
                empty_label.grid(row=row_index, column=0, sticky="w", padx=12, pady=(0, 10))
                row_index += 1
                continue

            for item in items:
                copy_text = item.get("copy_text") or item.get("text") or ""
                line_count = max(3, min(8, copy_text.count("\n") + 3))
                result_text = SelectableText(
                    self.results_content,
                    text=copy_text,
                    height=line_count,
                    style="Surface.TFrame",
                )
                result_text.grid(row=row_index, column=0, sticky="ew", padx=12, pady=(0, 10))
                row_index += 1

    def apply_window_settings(self):
        width, height = parse_window_size(self.gui_config.get("window_size", "900x700"))
        x_pos, y_pos = parse_window_position(self.gui_config.get("window_position", "+100+100"))
        self.root.geometry(f"{width}x{height}+{x_pos}+{y_pos}")
        if self.always_on_top_var is not None:
            self.root.attributes("-topmost", self.always_on_top_var.get())

    def _write_window_config(self):
        if not self.config_path:
            return
        next_config = build_gui_config_update(
            self.config,
            always_on_top=self.always_on_top_var.get(),
            compact_mode=self.compact_mode_var.get(),
            window_size=f"{self.root.winfo_width()}x{self.root.winfo_height()}",
            window_position=f"+{self.root.winfo_x()}+{self.root.winfo_y()}",
        )
        write_config(self.config_path, next_config)
        self.config = next_config
        self.gui_config = next_config.get("gui", {})

    def on_resize(self, event=None):
        if event is not None and event.widget is not self.root:
            return
        width = event.width if event is not None else self.root.winfo_width()
        self.narrow_layout = should_use_narrow_layout(width)
        self._write_window_config()
