import os
import unittest
from unittest import mock

from gui_app import app as gui_app


class GuiSearchAdapterTests(unittest.TestCase):
    def test_load_all_uses_gui_cap(self):
        config = {"sentence_limit": 4, "gui": {"load_all_sentence_limit": 25}}

        self.assertEqual(25, gui_app.resolve_sentence_limit(config, compact_mode=False, load_all=True))

    def test_compact_mode_uses_single_sentence(self):
        config = {"sentence_limit": 4, "gui": {"load_all_sentence_limit": 25}}

        self.assertEqual(1, gui_app.resolve_sentence_limit(config, compact_mode=True, load_all=False))

    def test_default_search_uses_configured_limit(self):
        config = {"sentence_limit": 4, "gui": {"load_all_sentence_limit": 25}}

        self.assertEqual(4, gui_app.resolve_sentence_limit(config, compact_mode=False, load_all=False))

    def test_manual_origins_refocus_search(self):
        self.assertTrue(gui_app.should_refocus_search("manual"))
        self.assertTrue(gui_app.should_refocus_search("button"))
        self.assertTrue(gui_app.should_refocus_search("load_all"))
        self.assertTrue(gui_app.should_refocus_search("history"))
        self.assertFalse(gui_app.should_refocus_search("clipboard"))
        self.assertFalse(gui_app.should_refocus_search("startup"))

    def test_format_bytes_uses_readable_units(self):
        self.assertEqual("100 bytes", gui_app.format_bytes(100))
        self.assertEqual("2.0 KB", gui_app.format_bytes(2048))
        self.assertEqual("3.0 MB", gui_app.format_bytes(3 * 1024 * 1024))

    def test_narrow_layout_breakpoint(self):
        self.assertTrue(gui_app.should_use_narrow_layout(600))
        self.assertFalse(gui_app.should_use_narrow_layout(gui_app.NARROW_LAYOUT_WIDTH))

    def test_window_size_parser_allows_smaller_responsive_window(self):
        self.assertEqual((520, 420), gui_app.parse_window_size("300x200"))

    def test_search_history_deduplicates_and_caps_results(self):
        history = []
        for index in range(14):
            history = gui_app.add_search_history(history, "word" + str(index), limit=12)
        history = gui_app.add_search_history(history, "word7", limit=12)

        self.assertEqual("word7", history[0])
        self.assertEqual(12, len(history))
        self.assertEqual(1, history.count("word7"))

    def test_result_view_model_orders_sections_for_rendering(self):
        view_model = gui_app.build_result_view_model(
            {
                "query": "mengatakan",
                "definitions": ["· mengatakan say · ·"],
                "red_book_definitions": [
                    {
                        "headword": "mengatakan",
                        "definition": "1 to say s.t. 2 to tell, inform, assert, mention.",
                        "page": 475,
                    }
                ],
                "red_book_results": [],
                "sentences": [
                    {
                        "index": 1,
                        "match": "Saya mengatakan hal itu.",
                        "translation": "I said that.",
                    }
                ],
                "message": None,
                "sentence_limit": 1,
                "sentences_truncated": False,
            }
        )

        self.assertEqual(
            ["red_book", "definitions", "sentences"],
            [section["kind"] for section in view_model["sections"]],
        )
        self.assertEqual(1, view_model["counts"]["red_book"])
        self.assertEqual("red_book_definition", view_model["sections"][0]["items"][0]["kind"])

    def test_status_text_summarizes_counts(self):
        view_model = {
            "message": None,
            "counts": {"red_book": 1, "definitions": 2, "sentences": 3},
            "sentences_truncated": False,
            "sentence_limit": 4,
        }

        self.assertEqual(
            "Found 1 Red Book results, 2 dictionary entries, and 3 sentence pairs.",
            gui_app.status_text_for_result(view_model),
        )

    def test_dependency_guard_is_clear_without_pyside(self):
        if gui_app.QT_AVAILABLE:
            self.skipTest("PySide6 is available in this environment.")

        with self.assertRaisesRegex(RuntimeError, "PySide6 is required"):
            gui_app.require_qt()


@unittest.skipUnless(gui_app.QT_AVAILABLE, "PySide6 is not installed")
class QtSmokeTests(unittest.TestCase):
    class FakeRunningWorker:
        def __init__(self):
            self.interruption_requested = False
            self.quit_requested = False
            self.wait_timeout = None

        def isRunning(self):
            return True

        def requestInterruption(self):
            self.interruption_requested = True

        def quit(self):
            self.quit_requested = True

        def wait(self, timeout):
            self.wait_timeout = timeout
            return True

    def _create_window(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        qt_app = gui_app.QApplication.instance() or gui_app.QApplication([])
        gui_app.apply_theme(qt_app)
        config = {
            "sentence_limit": 4,
            "poll_interval": 0.1,
            "gui": {
                "always_on_top": False,
                "compact_mode": False,
                "window_size": "900x700",
                "window_position": "+100+100",
                "load_all_sentence_limit": 25,
                "search_status_delay_ms": 200,
            },
        }
        with mock.patch.object(gui_app, "indexes_are_ready", return_value=True), \
                mock.patch.object(gui_app, "load_config", return_value=config), \
                mock.patch.object(gui_app.MyKamusGUI, "_run_search", return_value=None):
            window = gui_app.MyKamusGUI()
        window._write_window_config = lambda: None
        return qt_app, window

    def test_main_window_can_be_instantiated_offscreen(self):
        qt_app, window = self._create_window()
        window.show()
        qt_app.processEvents()

        self.assertIsNotNone(qt_app)
        self.assertEqual("myKamus", window.windowTitle())
        self.assertEqual(
            "#17201b",
            qt_app.palette().color(gui_app.QPalette.ColorRole.Text).name(),
        )
        self.assertFalse(window.narrow_layout)

        window.resize(600, 500)
        qt_app.processEvents()

        self.assertTrue(window.narrow_layout)
        self.assertEqual(gui_app.Qt.Vertical, window.splitter.orientation())
        self.assertFalse(window.history_list.isVisible())
        self.assertGreaterEqual(window.pause_button.height(), 30)
        with mock.patch.object(window, "_write_window_config", return_value=None):
            window.close()

    def test_shutdown_workers_stops_index_and_search_workers(self):
        _qt_app, window = self._create_window()
        index_worker = self.FakeRunningWorker()
        search_worker = self.FakeRunningWorker()
        window.index_worker = index_worker
        window.search_workers = {7: search_worker}

        window._shutdown_workers()

        self.assertTrue(index_worker.interruption_requested)
        self.assertTrue(index_worker.quit_requested)
        self.assertIsNotNone(index_worker.wait_timeout)
        self.assertTrue(search_worker.interruption_requested)
        self.assertTrue(search_worker.quit_requested)
        self.assertIsNotNone(search_worker.wait_timeout)
        self.assertIsNone(window.index_worker)
        self.assertEqual({}, window.search_workers)

    def test_close_event_shuts_down_workers(self):
        _qt_app, window = self._create_window()
        called = []
        window._shutdown_workers = lambda: called.append(True)

        with mock.patch.object(window, "_write_window_config", return_value=None):
            window.close()

        self.assertEqual([True], called)


if __name__ == "__main__":
    unittest.main()
