"""Main Tk window shell for the myKamus desktop app."""

import queue
from tkinter import StringVar, ttk

from gui_app.core.view_model import parse_window_position, parse_window_size
from gui_app.runtime.tasks import BackgroundTaskRunner
from gui_app.tk.loading_view import LoadingView
from gui_app.tk.theme import apply_theme
from gui_app.tk.widgets import ScrollableFrame


class MyKamusTkWindow(ttk.Frame):
    def __init__(self, root, backend):
        self.root = root
        self.backend = backend
        self.config = backend.load_config() or {}
        self.message_queue = queue.Queue()
        self.task_runner = BackgroundTaskRunner(self.message_queue)
        self.style = apply_theme(root)
        self.tools_visible = False
        self.loading_view = None

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

        self._configure_window()

        super().__init__(root, style="App.TFrame", padding=16)
        self.columnconfigure(0, weight=1)
        self.pack(fill="both", expand=True)

        if self.backend.indexes_are_ready():
            self.build_main_ui()
        else:
            self.show_loading_view()

    def _configure_window(self):
        gui_config = self.config.get("gui", {})
        width, height = parse_window_size(gui_config.get("window_size"))
        x_pos, y_pos = parse_window_position(gui_config.get("window_position"))
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

    def toggle_tools(self):
        if self.tools_panel is None:
            return
        if self.tools_visible:
            self.tools_panel.grid_remove()
            self.tools_visible = False
        else:
            self.tools_panel.grid(row=0, column=0, sticky="nsw", padx=(0, 12))
            self.tools_visible = True
