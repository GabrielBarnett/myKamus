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


class TkLoadingViewTests(unittest.TestCase):
    def test_loading_view_updates_percent_and_status(self):
        from gui_app.tk.loading_view import LoadingView

        root = _create_root(self)
        view = LoadingView(root)

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


class TkWidgetsTests(unittest.TestCase):
    def test_selectable_text_renders_inserted_text(self):
        from gui_app.tk.widgets import SelectableText

        root = _create_root(self)
        widget = SelectableText(root, height=4, width=24)
        widget.pack()

        widget.set_text("Halo dunia")

        self.assertEqual("Halo dunia", widget.get("1.0", "end-1c"))


if __name__ == "__main__":
    unittest.main()
