import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from gui_app.core import backend, config_store
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

    def test_parse_window_size_enforces_minimums(self):
        self.assertEqual((520, 420), parse_window_size("300x200"))


class GuiCoreConfigStoreTests(unittest.TestCase):
    def test_build_gui_config_update_preserves_existing_gui_keys(self):
        config = {
            "sentence_limit": 4,
            "gui": {
                "theme": "dark",
                "search_status_delay_ms": 200,
                "always_on_top": False,
            },
        }

        updated = config_store.build_gui_config_update(
            config,
            always_on_top=True,
            compact_mode=False,
            window_size="900x700",
            window_position="+120+240",
        )

        self.assertEqual(
            {
                "theme": "dark",
                "search_status_delay_ms": 200,
                "always_on_top": True,
                "compact_mode": False,
                "window_size": "900x700",
                "window_position": "+120+240",
            },
            updated["gui"],
        )
        self.assertEqual(4, updated["sentence_limit"])

    def test_write_config_persists_trailing_newline(self):
        config = {"gui": {"always_on_top": True}}

        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"

            config_store.write_config(path, config)

            self.assertTrue(path.read_text(encoding="utf-8").endswith("\n"))


class GuiBackendTests(unittest.TestCase):
    def test_indexes_are_ready_requires_sentence_dataset_and_red_book_index(self):
        wrapped_backend = backend.GuiBackend(
            is_sentence_index_valid_func=mock.Mock(return_value=True),
            is_red_book_index_valid_func=mock.Mock(return_value=False),
        )

        self.assertFalse(wrapped_backend.indexes_are_ready())

    def test_build_indexes_validates_sentence_dataset_before_red_book_build(self):
        events = []
        wrapped_backend = backend.GuiBackend(
            ensure_sentence_index_func=lambda progress_callback=None: events.append("sentence") or {"validated": True},
            ensure_red_book_index_func=lambda progress_callback=None: events.append("red-book") or {"rebuilt": False},
        )

        result = wrapped_backend.build_indexes(progress_callback=lambda _progress: None)

        self.assertEqual(["sentence", "red-book"], events)
        self.assertEqual(
            {
                "sentence_dataset": {"validated": True},
                "red_book_index": {"rebuilt": False},
            },
            result,
        )

    def test_search_delegates_to_wrapped_function(self):
        search_result = {"query": "kata", "sentences": []}
        search_func = mock.Mock(return_value=search_result)
        wrapped_backend = backend.GuiBackend(search_for_word_data_func=search_func)

        result = wrapped_backend.search("kata", 7)

        self.assertIs(search_result, result)
        search_func.assert_called_once_with("kata", sentence_limit=7)


if __name__ == "__main__":
    unittest.main()
