import threading
import time
import unittest
from unittest import mock


def _create_root(test_case):
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        test_case.skipTest("Tk display unavailable: " + str(exc))
    root.withdraw()
    def cleanup():
        try:
            root.destroy()
        except tk.TclError:
            pass

    test_case.addCleanup(cleanup)
    return root


def _wait_for(predicate, timeout=1.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _wait_for_tk(root, predicate, timeout=1.5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        root.update()
        if predicate():
            return True
        time.sleep(0.01)
    root.update()
    return predicate()


def _read_selectable_texts(container):
    from gui_app.tk.widgets import SelectableText

    return [
        child.text_widget.get("1.0", "end-1c")
        for child in container.winfo_children()
        if isinstance(child, SelectableText)
    ]


class TkThemeTests(unittest.TestCase):
    def test_apply_theme_returns_style_object(self):
        from gui_app.tk import theme

        root = _create_root(self)

        style = theme.apply_theme(root)

        self.assertIsNotNone(style)
        self.assertEqual(root, style.master)
        self.assertEqual("#f5f7fa", style.lookup("App.TFrame", "background"))
        self.assertEqual("#1f2933", style.lookup("SectionTitle.TLabel", "foreground"))
        self.assertEqual("#3b82f6", style.lookup("Primary.TButton", "background"))
        self.assertEqual("#ffffff", style.lookup("Tool.TButton", "background"))


class TkLoadingViewTests(unittest.TestCase):
    def test_loading_view_updates_percent_and_status(self):
        from gui_app.tk import theme
        from gui_app.tk.loading_view import LoadingView

        root = _create_root(self)
        style = theme.apply_theme(root)
        view = LoadingView(root, style="Surface.TFrame")

        view.update_progress(
            {
                "percent": 42.4,
                "processed_bytes": 1536,
                "total_bytes": 4096,
                "title": "Building search index...",
                "status": "Still working...",
            }
        )

        self.assertEqual("42%", view.percent_var.get())
        self.assertEqual("Building search index...", view.title_var.get())
        self.assertEqual("Processed 1.5 KB of 4.0 KB", view.detail_var.get())
        self.assertEqual("Still working...", view.status_var.get())
        self.assertEqual(
            style.lookup("Surface.TFrame", "background"),
            str(view.title_label.cget("background")),
        )

    def test_loading_view_handles_partial_bytes_and_state_transitions(self):
        from gui_app.tk.loading_view import LoadingView

        root = _create_root(self)
        view = LoadingView(root)

        view.update_progress(
            {
                "percent": 5,
                "processed_bytes": None,
                "total_bytes": None,
            }
        )
        view.show_error()
        self.assertEqual(
            "Index build failed. Searches will use fallback mode.",
            view.status_var.get(),
        )

        view.show_ready()
        self.assertEqual("100%", view.percent_var.get())
        self.assertEqual("Search index ready.", view.status_var.get())
        self.assertEqual("Processed 0 bytes of 0 bytes", view.detail_var.get())


class TkWidgetsTests(unittest.TestCase):
    def test_section_header_renders_zero_subtitle_and_surface_background(self):
        from gui_app.tk import theme
        from gui_app.tk.widgets import SectionHeader

        root = _create_root(self)
        style = theme.apply_theme(root)
        widget = SectionHeader(root, title="Results", subtitle=0, style="Surface.TFrame")
        widget.pack()

        self.assertIsNotNone(widget.subtitle_label)
        self.assertEqual("0", str(widget.subtitle_label.cget("text")))
        self.assertEqual(
            style.lookup("Surface.TFrame", "background"),
            str(widget.title_label.cget("background")),
        )

    def test_selectable_text_accepts_text_initializer_and_is_read_only(self):
        from gui_app.tk import theme
        from gui_app.tk.widgets import SelectableText

        root = _create_root(self)
        style = theme.apply_theme(root)
        widget = SelectableText(root, text="Halo dunia", height=4, width=24, style="Surface.TFrame")
        widget.pack()

        self.assertEqual("Halo dunia", widget.text_widget.get("1.0", "end-1c"))
        self.assertEqual("disabled", str(widget.text_widget.cget("state")))
        self.assertEqual(
            style.lookup("Surface.TFrame", "background"),
            str(widget.text_widget.cget("background")),
        )

    def test_scrollable_frame_canvas_uses_themed_background(self):
        from gui_app.tk import theme
        from gui_app.tk.widgets import ScrollableFrame

        root = _create_root(self)
        style = theme.apply_theme(root)
        widget = ScrollableFrame(root, style="Surface.TFrame")
        widget.pack()

        self.assertEqual(
            style.lookup("Surface.TFrame", "background"),
            str(widget.canvas.cget("background")),
        )

    def test_selectable_text_shows_scrollbar_for_long_wrapped_content(self):
        from gui_app.tk import theme
        from gui_app.tk.widgets import SelectableText

        root = _create_root(self)
        theme.apply_theme(root)
        long_text = " ".join(["panjang"] * 160)
        widget = SelectableText(root, text=long_text, height=4, width=18, style="Surface.TFrame")
        widget.pack(fill="both", expand=True)
        root.update_idletasks()

        self.assertEqual("pack", widget.scrollbar.winfo_manager())
        self.assertLess(float(widget.text_widget.yview()[1]), 1.0)


class _BackendStub:
    def __init__(
        self,
        *,
        config=None,
        indexes_ready=True,
        search_results=None,
        build_indexes_callback=None,
        config_path=None,
    ):
        self._config = config or {}
        self._indexes_ready = indexes_ready
        self._search_results = search_results or {}
        self._build_indexes_callback = build_indexes_callback or (lambda progress_callback: None)
        self.config_path = config_path
        self.search_calls = []

    def load_config(self):
        return self._config

    def indexes_are_ready(self):
        return self._indexes_ready

    def build_indexes(self, progress_callback):
        return self._build_indexes_callback(progress_callback)

    def search(self, query, sentence_limit):
        self.search_calls.append((query, sentence_limit))
        template = self._search_results.get(query)
        if template is None:
            template = {
                "query": query,
                "message": None,
                "definitions": [query.upper()] if query else [],
                "red_book_definitions": [],
                "sentences": [
                    {
                        "index": 1,
                        "match": query,
                        "translation": query.upper(),
                        "matched_language": "id",
                    }
                ]
                if query
                else [],
                "sentences_truncated": False,
            }
        result = dict(template)
        result.setdefault("query", query)
        result.setdefault("message", None)
        result.setdefault("definitions", [])
        result.setdefault("red_book_definitions", [])
        result.setdefault("sentences", [])
        result.setdefault("sentences_truncated", False)
        result["sentence_limit"] = sentence_limit
        return result


class _BlockingSearchBackend(_BackendStub):
    def __init__(self, *, config=None):
        super().__init__(config=config, indexes_ready=True)
        self.first_started = threading.Event()
        self.release_first = threading.Event()

    def search(self, query, sentence_limit):
        self.search_calls.append((query, sentence_limit))
        if query == "":
            return {
                "query": query,
                "message": None,
                "definitions": [],
                "red_book_definitions": [],
                "sentences": [],
                "sentences_truncated": False,
                "sentence_limit": sentence_limit,
            }
        if query == "first":
            self.first_started.set()
            self.release_first.wait(1.5)
        return {
            "query": query,
            "message": None,
            "definitions": [query.upper()],
            "red_book_definitions": [],
            "sentences": [],
            "sentences_truncated": False,
            "sentence_limit": sentence_limit,
        }


class _BlockingIndexBackend(_BackendStub):
    def __init__(self, *, config=None):
        super().__init__(config=config, indexes_ready=False)
        self.build_started = threading.Event()
        self.build_completed = threading.Event()
        self.progress_count = 0

    def build_indexes(self, progress_callback):
        self.build_started.set()
        for step in range(80):
            self.progress_count += 1
            progress_callback(
                {
                    "title": "Building sentence search index...",
                    "percent": min(100.0, float(step + 1)),
                    "processed_pages": step + 1,
                    "total_pages": 80,
                }
            )
            time.sleep(0.005)
        self.build_completed.set()


def _run_task_immediately(task_runner, *, token, kind, target):
    def emit_progress(value):
        task_runner.message_queue.put(
            {
                "token": token,
                "kind": kind,
                "event": "progress",
                "payload": value,
            }
        )

    try:
        result = target(threading.Event(), emit_progress)
    except Exception as exc:
        task_runner.message_queue.put(
            {
                "token": token,
                "kind": kind,
                "event": "error",
                "payload": {"error": str(exc)},
            }
        )
    else:
        task_runner.message_queue.put(
            {
                "token": token,
                "kind": kind,
                "event": "result",
                "payload": result,
            }
        )


class TkMainWindowTests(unittest.TestCase):
    def test_main_window_builds_search_first_layout_and_sets_title(self):
        from gui_app.tk.main_window import MyKamusTkWindow
        from gui_app.runtime.tasks import BackgroundTaskRunner
        from gui_app.tk.widgets import ScrollableFrame

        root = _create_root(self)
        backend = _BackendStub(
            config={"gui": {"window_size": "840x620", "window_position": "+44+55"}},
            indexes_ready=True,
        )

        window = MyKamusTkWindow(root, backend)
        root.update_idletasks()

        self.assertEqual("myKamus", root.title())
        self.assertIsNotNone(window.message_queue)
        self.assertIsInstance(window.task_runner, BackgroundTaskRunner)
        self.assertIs(window.message_queue, window.task_runner.message_queue)
        self.assertEqual("840x620+44+55", root.geometry().split(" ", 1)[0])
        self.assertIsNotNone(window.command_frame)
        self.assertEqual(window.command_frame, window.search_entry.master)
        self.assertEqual(window.command_frame, window.search_button.master)
        self.assertEqual(window.command_frame, window.tools_button.master)
        self.assertIs(window.status_label.master, window)
        self.assertIsNotNone(window.recent_row_frame)
        self.assertIs(window.body_frame.master, window)
        self.assertIs(window.tools_panel.master, window.body_frame)
        self.assertIsInstance(window.results_frame, ScrollableFrame)
        self.assertIs(window.results_frame.master, window.body_frame)

    def test_tools_panel_visibility_toggles(self):
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(indexes_ready=True)

        window = MyKamusTkWindow(root, backend)
        root.update_idletasks()

        self.assertFalse(window.tools_visible)
        self.assertEqual("", window.tools_panel.winfo_manager())

        window.toggle_tools()
        root.update_idletasks()

        self.assertTrue(window.tools_visible)
        self.assertEqual("grid", window.tools_panel.winfo_manager())

        window.toggle_tools()
        root.update_idletasks()

        self.assertFalse(window.tools_visible)
        self.assertEqual("", window.tools_panel.winfo_manager())

    def test_main_window_shows_loading_view_until_indexes_are_ready(self):
        from gui_app.tk.loading_view import LoadingView
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(indexes_ready=False)

        with mock.patch(
            "gui_app.runtime.tasks.BackgroundTaskRunner.start",
            return_value=None,
        ):
            window = MyKamusTkWindow(root, backend)
            root.update_idletasks()

        self.assertIsInstance(window.loading_view, LoadingView)
        self.assertEqual("pack", window.loading_view.winfo_manager())
        self.assertIsNone(window.command_frame)
        self.assertIsNone(window.status_label)
        self.assertIsNone(window.recent_row_frame)
        self.assertIsNone(window.body_frame)
        self.assertIsNone(window.tools_panel)
        self.assertIsNone(window.results_frame)

    def test_manual_search_updates_recent_history_and_status(self):
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(config={"sentence_limit": 4}, indexes_ready=True)

        with mock.patch.object(
            MyKamusTkWindow,
            "read_clipboard",
            return_value="",
            create=True,
        ), mock.patch(
            "gui_app.runtime.tasks.BackgroundTaskRunner.start",
            new=_run_task_immediately,
        ):
            window = MyKamusTkWindow(root, backend)
            window.drain_messages()
            window.search_history = []
            window.status_var.set("Ready.")

            window.search_entry.insert(0, "halo")
            window.on_manual_search()
            window.drain_messages()

        self.assertEqual(["halo"], window.search_history)
        self.assertEqual(
            "Found 0 Red Book results, 1 dictionary entries, and 1 sentence pairs.",
            window.status_var.get(),
        )
        self.assertEqual(("halo", 4), backend.search_calls[-1])

    def test_inline_recent_row_is_capped_when_history_grows(self):
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(indexes_ready=True)
        window = MyKamusTkWindow(root, backend)
        window.search_history = [
            "query satu",
            "query dua yang cukup panjang",
            "query tiga",
            "query empat",
            "query lima",
        ]

        window._render_history()
        root.update_idletasks()

        inline_buttons = window.recent_row_frame.winfo_children()
        self.assertLess(len(inline_buttons), len(window.search_history))

    def test_tools_panel_exposes_full_recent_history_list(self):
        import tkinter as tk

        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(indexes_ready=True)
        window = MyKamusTkWindow(root, backend)
        window.search_history = [
            "query satu",
            "query dua yang cukup panjang",
            "query tiga",
            "query empat",
            "query lima",
        ]

        window._render_history()
        root.update_idletasks()

        self.assertIsInstance(window.tools_history_listbox, tk.Listbox)
        self.assertEqual(len(window.search_history), window.tools_history_listbox.size())
        self.assertEqual(tuple(window.search_history), window.tools_history_listbox.get(0, "end"))

    def test_selecting_tools_panel_history_item_reruns_that_query(self):
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(config={"sentence_limit": 4}, indexes_ready=True)

        with mock.patch.object(
            MyKamusTkWindow,
            "read_clipboard",
            return_value="",
            create=True,
        ), mock.patch(
            "gui_app.runtime.tasks.BackgroundTaskRunner.start",
            new=_run_task_immediately,
        ):
            window = MyKamusTkWindow(root, backend)
            window.drain_messages()
            window.search_history = [
                "query satu",
                "query dua yang cukup panjang",
                "query tiga",
            ]
            window._render_history()
            root.update_idletasks()

            window.tools_history_listbox.selection_clear(0, "end")
            window.tools_history_listbox.selection_set(1)
            window.tools_history_listbox.activate(1)
            window._on_tools_history_click()
            window.drain_messages()

        self.assertEqual("query dua yang cukup panjang", window.search_entry.get())
        self.assertEqual(("query dua yang cukup panjang", 4), backend.search_calls[-1])

    def test_blank_space_click_in_tools_history_does_not_rerun_query(self):
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(indexes_ready=True)
        window = MyKamusTkWindow(root, backend)
        window.search_history = [
            "query satu",
            "query dua",
            "query tiga",
        ]
        window._render_history()
        root.update_idletasks()
        window.tools_history_listbox.selection_set(1)

        event = mock.Mock()
        event.x = 120
        event.y = 40

        with mock.patch.object(window.tools_history_listbox, "nearest", return_value=1), mock.patch.object(
            window.tools_history_listbox,
            "bbox",
            return_value=(0, 0, 80, 20),
        ), mock.patch.object(window, "_run_history_search") as run_history_search:
            result = window._on_tools_history_click(event)

        self.assertEqual("break", result)
        run_history_search.assert_not_called()

    def test_clipboard_poll_triggers_search_when_value_changes(self):
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(config={"sentence_limit": 2}, indexes_ready=True)

        with mock.patch.object(
            MyKamusTkWindow,
            "read_clipboard",
            side_effect=["awal", "berubah"],
            create=True,
        ), mock.patch(
            "gui_app.runtime.tasks.BackgroundTaskRunner.start",
            new=_run_task_immediately,
        ):
            window = MyKamusTkWindow(root, backend)
            window.drain_messages()
            window.search_history = []
            window.status_var.set("Ready.")

            window.poll_clipboard()
            window.drain_messages()

        self.assertEqual("berubah", window.clipboard_value)
        self.assertEqual([], window.search_history)
        self.assertEqual(("berubah", 2), backend.search_calls[-1])
        self.assertEqual(
            "Found 0 Red Book results, 1 dictionary entries, and 1 sentence pairs.",
            window.status_var.get(),
        )

    def test_superseded_searches_are_coalesced_while_async_search_is_in_flight(self):
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BlockingSearchBackend(config={"sentence_limit": 3})

        with mock.patch.object(
            MyKamusTkWindow,
            "read_clipboard",
            return_value="",
            create=True,
        ):
            window = MyKamusTkWindow(root, backend)
            self.assertTrue(_wait_for(lambda: len(backend.search_calls) >= 1))
            window.drain_messages()

            window.run_search("first", origin="manual")
            self.assertTrue(backend.first_started.wait(1.0))

            window.run_search("second", origin="manual")
            window.run_search("third", origin="manual")
            time.sleep(0.1)

            self.assertEqual(
                ["", "first"],
                [query for query, _limit in backend.search_calls[:2]],
            )
            self.assertNotIn("second", [query for query, _limit in backend.search_calls])
            self.assertNotIn("third", [query for query, _limit in backend.search_calls])

            backend.release_first.set()
            self.assertTrue(
                _wait_for_tk(root, lambda: "third" in [query for query, _limit in backend.search_calls])
            )
            self.assertTrue(_wait_for_tk(root, lambda: window.status_var.get().startswith("Found ")))

        self.assertEqual(
            ["", "first", "third"],
            [query for query, _limit in backend.search_calls if query in {"", "first", "third"}],
        )
        self.assertNotIn("second", [query for query, _limit in backend.search_calls])
        self.assertEqual(["third"], window.search_history)

    def test_index_build_path_swaps_loading_view_for_main_ui(self):
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(
            config={"sentence_limit": 4, "poll_interval": 0.1, "gui": {}},
            indexes_ready=False,
            build_indexes_callback=lambda progress_callback: progress_callback(
                {
                    "title": "Building sentence search index...",
                    "percent": 100.0,
                    "processed_pages": 1,
                    "total_pages": 1,
                }
            ),
        )

        with mock.patch.object(
            MyKamusTkWindow,
            "read_clipboard",
            return_value="",
            create=True,
        ), mock.patch(
            "gui_app.runtime.tasks.BackgroundTaskRunner.start",
            new=_run_task_immediately,
        ):
            window = MyKamusTkWindow(root, backend)
            window.drain_messages()
            root.update_idletasks()

        self.assertIsNone(window.loading_view)
        self.assertIsNotNone(window.command_frame)
        self.assertIsNotNone(window.results_frame)

    def test_resize_sets_narrow_layout_flag(self):
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(
            config={"sentence_limit": 4, "poll_interval": 0.1, "gui": {}},
            indexes_ready=True,
        )

        window = MyKamusTkWindow(root, backend)
        event = mock.Mock()
        event.widget = root
        event.width = 600

        window.on_resize(event)

        self.assertTrue(window.narrow_layout)

    def test_close_cancels_background_tasks_and_writes_config(self):
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(
            config={"sentence_limit": 4, "poll_interval": 0.1, "gui": {}},
            indexes_ready=True,
        )
        window = MyKamusTkWindow(root, backend)
        calls = []
        window.runner.cancel_all = lambda: calls.append("cancel")
        window.runner.join_all = lambda timeout=2: calls.append("join")
        window.write_window_config = lambda: calls.append("write")

        window.on_close()

        self.assertEqual(["cancel", "join", "write"], calls)

    def test_destroyed_root_cleans_up_ready_window_without_on_close(self):
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(
            config={"sentence_limit": 4, "poll_interval": 0.1, "gui": {}},
            indexes_ready=True,
        )
        window = MyKamusTkWindow(root, backend)
        calls = []
        window.runner.cancel_all = lambda: calls.append("cancel")
        window.runner.join_all = lambda timeout=2: calls.append(("join", timeout))

        root.destroy()

        self.assertEqual(["cancel", ("join", 2)], calls)
        self.assertIsNone(window.status_var)
        self.assertIsNone(window.compact_mode_var)
        self.assertIsNone(window.always_on_top_var)

    def test_destroyed_root_cleans_up_loading_view_without_on_close(self):
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(indexes_ready=False)

        with mock.patch(
            "gui_app.runtime.tasks.BackgroundTaskRunner.start",
            return_value=None,
        ):
            window = MyKamusTkWindow(root, backend)

        calls = []
        window.runner.cancel_all = lambda: calls.append("cancel")
        window.runner.join_all = lambda timeout=2: calls.append(("join", timeout))

        root.destroy()

        self.assertEqual(["cancel", ("join", 2)], calls)
        self.assertIsNone(window.loading_view)

    def test_startup_index_build_is_interrupted_on_close(self):
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BlockingIndexBackend(
            config={"sentence_limit": 4, "poll_interval": 0.1, "gui": {}},
        )

        with mock.patch("gui_app.tk.main_window.write_config"):
            window = MyKamusTkWindow(root, backend)
            self.assertTrue(backend.build_started.wait(1.0))
            self.assertGreater(backend.progress_count, 0)

            window.on_close()

        self.assertFalse(backend.build_completed.is_set())
        self.assertIsNone(window.command_frame)

    def test_tools_panel_reflows_between_narrow_and_wide_layouts(self):
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(
            config={"sentence_limit": 4, "poll_interval": 0.1, "gui": {}},
            indexes_ready=True,
        )
        window = MyKamusTkWindow(root, backend)
        window.toggle_tools()
        root.update_idletasks()

        narrow_event = mock.Mock()
        narrow_event.widget = root
        narrow_event.width = 600
        window.on_resize(narrow_event)
        narrow_grid = window.tools_panel.grid_info()

        wide_event = mock.Mock()
        wide_event.widget = root
        wide_event.width = 900
        window.on_resize(wide_event)
        wide_grid = window.tools_panel.grid_info()

        self.assertEqual("1", str(narrow_grid["row"]))
        self.assertEqual("2", str(narrow_grid["columnspan"]))
        self.assertEqual("ew", str(narrow_grid["sticky"]))
        self.assertEqual("0", str(wide_grid["row"]))
        self.assertEqual("nsw", str(wide_grid["sticky"]))

    def test_tools_panel_controls_have_live_runtime_effects(self):
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(
            config={
                "sentence_limit": 4,
                "poll_interval": 0.1,
                "gui": {"always_on_top": False, "compact_mode": False},
            },
            indexes_ready=True,
        )

        with mock.patch.object(
            MyKamusTkWindow,
            "read_clipboard",
            return_value="",
            create=True,
        ), mock.patch(
            "gui_app.runtime.tasks.BackgroundTaskRunner.start",
            new=_run_task_immediately,
        ):
            window = MyKamusTkWindow(root, backend)
            window.drain_messages()
            window.toggle_tools()
            root.update_idletasks()

            self.assertIsNotNone(window.always_on_top_button)
            self.assertIsNotNone(window.compact_mode_button)
            self.assertIsNotNone(window.load_all_button)

            always_on_top_calls = []
            window.set_always_on_top = lambda enabled: always_on_top_calls.append(enabled)

            window.always_on_top_button.invoke()
            self.assertTrue(window.always_on_top_var.get())
            self.assertEqual([True], always_on_top_calls)

            window.search_entry.insert(0, "halo")
            window.on_manual_search()
            window.drain_messages()

            window.compact_mode_button.invoke()
            window.drain_messages()

        self.assertTrue(window.compact_mode_var.get())
        self.assertEqual(("halo", 1), backend.search_calls[-1])

    def test_tools_panel_load_all_button_reaches_full_sentence_search(self):
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(
            config={
                "sentence_limit": 4,
                "poll_interval": 0.1,
                "gui": {"load_all_sentence_limit": 25},
            },
            indexes_ready=True,
        )

        with mock.patch.object(
            MyKamusTkWindow,
            "read_clipboard",
            return_value="",
            create=True,
        ), mock.patch(
            "gui_app.runtime.tasks.BackgroundTaskRunner.start",
            new=_run_task_immediately,
        ):
            window = MyKamusTkWindow(root, backend)
            window.drain_messages()
            window.toggle_tools()
            root.update_idletasks()
            window.search_entry.insert(0, "halo")

            window.load_all_button.invoke()
            window.drain_messages()

        self.assertEqual(("halo", 25), backend.search_calls[-1])
        self.assertEqual("Loaded 1 matching sentence pairs.", window.status_var.get())

    def test_red_book_page_numbers_are_in_rendered_results(self):
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(
            config={"sentence_limit": 4, "poll_interval": 0.1, "gui": {}},
            indexes_ready=True,
            search_results={
                "merah": {
                    "query": "merah",
                    "message": None,
                    "definitions": [],
                    "red_book_definitions": [
                        {
                            "headword": "merah",
                            "definition": "red",
                            "page": 123,
                        }
                    ],
                    "sentences": [],
                    "sentences_truncated": False,
                }
            },
        )

        with mock.patch.object(
            MyKamusTkWindow,
            "read_clipboard",
            return_value="",
            create=True,
        ), mock.patch(
            "gui_app.runtime.tasks.BackgroundTaskRunner.start",
            new=_run_task_immediately,
        ):
            window = MyKamusTkWindow(root, backend)
            window.drain_messages()
            window.search_entry.insert(0, "merah")
            window.on_manual_search()
            window.drain_messages()

        rendered_texts = _read_selectable_texts(window.results_content)

        self.assertTrue(any("Page 123" in text for text in rendered_texts))
        self.assertTrue(any("merah" in text and "red" in text for text in rendered_texts))

    def test_write_window_config_uses_default_config_path_when_backend_omits_one(self):
        from gui_app.tk import main_window
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(
            config={"sentence_limit": 4, "poll_interval": 0.1, "gui": {}},
            indexes_ready=True,
            config_path=None,
        )
        window = MyKamusTkWindow(root, backend)

        with mock.patch.object(main_window, "write_config") as write_config_mock:
            window.write_window_config()

        write_config_mock.assert_called_once()
        self.assertEqual("config.json", write_config_mock.call_args.args[0])

    def test_write_window_config_persists_geometry_and_toggle_values(self):
        from gui_app.tk import main_window
        from gui_app.tk.main_window import MyKamusTkWindow

        root = _create_root(self)
        backend = _BackendStub(
            config={"sentence_limit": 4, "poll_interval": 0.1, "gui": {"load_all_sentence_limit": 25}},
            indexes_ready=True,
            config_path="custom-config.json",
        )
        window = MyKamusTkWindow(root, backend)
        window.always_on_top_var.set(False)
        window.compact_mode_var.set(True)
        root.winfo_width = lambda: 777
        root.winfo_height = lambda: 555
        root.winfo_x = lambda: 33
        root.winfo_y = lambda: 44

        with mock.patch.object(main_window, "write_config") as write_config_mock:
            window.write_window_config()

        write_config_mock.assert_called_once()
        self.assertEqual("custom-config.json", write_config_mock.call_args.args[0])
        self.assertEqual(
            {
                "sentence_limit": 4,
                "poll_interval": 0.1,
                "gui": {
                    "load_all_sentence_limit": 25,
                    "always_on_top": False,
                    "compact_mode": True,
                    "window_size": "777x555",
                    "window_position": "+33+44",
                },
            },
            write_config_mock.call_args.args[1],
        )


if __name__ == "__main__":
    unittest.main()
