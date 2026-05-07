import unittest

from gui_app.app import MyKamusGUI, format_bytes, resolve_sentence_limit, should_refocus_search


class GuiSearchAdapterTests(unittest.TestCase):
    def test_load_all_uses_gui_cap(self):
        config = {"sentence_limit": 4, "gui": {"load_all_sentence_limit": 25}}

        self.assertEqual(25, resolve_sentence_limit(config, compact_mode=False, load_all=True))

    def test_compact_mode_uses_single_sentence(self):
        config = {"sentence_limit": 4, "gui": {"load_all_sentence_limit": 25}}

        self.assertEqual(1, resolve_sentence_limit(config, compact_mode=True, load_all=False))

    def test_default_search_uses_configured_limit(self):
        config = {"sentence_limit": 4, "gui": {"load_all_sentence_limit": 25}}

        self.assertEqual(4, resolve_sentence_limit(config, compact_mode=False, load_all=False))

    def test_only_manual_origins_refocus_search(self):
        self.assertTrue(should_refocus_search("manual"))
        self.assertTrue(should_refocus_search("load_all"))
        self.assertFalse(should_refocus_search("clipboard"))
        self.assertFalse(should_refocus_search("startup"))

    def test_format_bytes_uses_readable_units(self):
        self.assertEqual("100 bytes", format_bytes(100))
        self.assertEqual("2.0 KB", format_bytes(2048))
        self.assertEqual("3.0 MB", format_bytes(3 * 1024 * 1024))

    def test_focus_helper_selects_existing_search_text(self):
        class FakeEntry:
            def __init__(self):
                self.focused = False
                self.selection = None
                self.cursor = None

            def focus_set(self):
                self.focused = True

            def selection_range(self, start, end):
                self.selection = (start, end)

            def icursor(self, index):
                self.cursor = index

        gui = object.__new__(MyKamusGUI)
        gui.main_ui_ready = True
        gui.search_entry = FakeEntry()

        gui._focus_search_entry(select_text=True)

        self.assertTrue(gui.search_entry.focused)
        self.assertEqual((0, "end"), gui.search_entry.selection)
        self.assertEqual("end", gui.search_entry.cursor)

    def test_render_results_places_red_book_before_corpus_examples(self):
        class FakeText:
            def __init__(self):
                self.content = ""

            def configure(self, **kwargs):
                pass

            def delete(self, start, end):
                self.content = ""

            def insert(self, end, text):
                self.content += text

        class FakeStatus:
            def configure(self, **kwargs):
                pass

        gui = object.__new__(MyKamusGUI)
        gui.results_text = FakeText()
        gui.status_label = FakeStatus()

        gui._render_results(
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
                "red_book_results": [
                    {
                        "headword": "mengatakan",
                        "indonesian": "Saya mengatakan hal itu.",
                        "english": "I said that.",
                        "page": 475,
                    }
                ],
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

        content = gui.results_text.content
        self.assertLess(
            content.index("Word translations"),
            content.index("Red Book Results"),
        )
        self.assertIn(
            "Definition: 1 to say s.t. 2 to tell, inform, assert, mention.",
            content,
        )
        self.assertLess(
            content.index("Red Book Results"),
            content.index("Example sentences"),
        )


if __name__ == "__main__":
    unittest.main()
