import unittest

from gui_app.core.view_model import (
    HISTORY_LIMIT,
    build_result_view_model,
    add_search_history,
    parse_window_size,
    resolve_sentence_limit,
)


class GuiCoreViewModelTests(unittest.TestCase):
    def test_resolve_sentence_limit_uses_load_all_cap(self):
        config = {"sentence_limit": 4, "gui": {"load_all_sentence_limit": 25}}

        self.assertEqual(
            25,
            resolve_sentence_limit(config, compact_mode=False, load_all=True),
        )

    def test_add_search_history_deduplicates_and_caps_results(self):
        history = []
        for index in range(HISTORY_LIMIT + 2):
            history = add_search_history(history, "word" + str(index), limit=HISTORY_LIMIT)

        history = add_search_history(history, "  word7  ", limit=HISTORY_LIMIT)

        self.assertEqual("word7", history[0])
        self.assertEqual(HISTORY_LIMIT, len(history))
        self.assertEqual(1, history.count("word7"))

    def test_build_result_view_model_orders_sections_for_rendering(self):
        view_model = build_result_view_model(
            {
                "query": "mengatakan",
                "definitions": ["say", "tell"],
                "red_book_definitions": [
                    {
                        "headword": "mengatakan",
                        "definition": "to say",
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

    def test_parse_window_size_enforces_minimums(self):
        self.assertEqual((520, 420), parse_window_size("300x200"))


if __name__ == "__main__":
    unittest.main()
