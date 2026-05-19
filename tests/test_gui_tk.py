import threading
import unittest
from unittest import mock


def _create_root(test_case):
    import tkinter as tk

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        test_case.skipTest("Tk display unavailable: " + str(exc))
    root.withdraw()
    test_case.addCleanup(root.destroy)
    return root


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


class _BackendStub:
    def __init__(self, *, config=None, indexes_ready=True, search_results=None):
        self._config = config or {}
        self._indexes_ready = indexes_ready
        self._search_results = search_results or {}
        self.search_calls = []

    def load_config(self):
        return self._config

    def indexes_are_ready(self):
        return self._indexes_ready

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


def _run_search_immediately(task_runner, *, token, kind, target):
    try:
        result = target(threading.Event(), lambda _value: None)
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
            new=_run_search_immediately,
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
            new=_run_search_immediately,
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


if __name__ == "__main__":
    unittest.main()
