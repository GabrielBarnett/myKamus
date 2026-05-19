import unittest


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
    def __init__(self, *, config=None, indexes_ready=True):
        self._config = config or {}
        self._indexes_ready = indexes_ready

    def load_config(self):
        return self._config

    def indexes_are_ready(self):
        return self._indexes_ready


class TkMainWindowTests(unittest.TestCase):
    def test_main_window_builds_search_first_layout_and_sets_title(self):
        from gui_app.tk.main_window import MyKamusTkWindow
        from gui_app.tk.widgets import ScrollableFrame

        root = _create_root(self)
        backend = _BackendStub(indexes_ready=True)

        window = MyKamusTkWindow(root, backend)
        root.update_idletasks()

        self.assertEqual("myKamus", root.title())
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

        self.assertTrue(window.tools_visible)
        self.assertEqual("grid", window.tools_panel.winfo_manager())

        window.toggle_tools()
        root.update_idletasks()

        self.assertFalse(window.tools_visible)
        self.assertEqual("", window.tools_panel.winfo_manager())

        window.toggle_tools()
        root.update_idletasks()

        self.assertTrue(window.tools_visible)
        self.assertEqual("grid", window.tools_panel.winfo_manager())


if __name__ == "__main__":
    unittest.main()
