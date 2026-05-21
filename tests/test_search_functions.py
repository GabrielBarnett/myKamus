import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from sentence_data.builder import build_sentence_dataset
import search_functions as sf


class SearchFunctionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        dictionary_path = self.temp_path / "dict.txt"
        self.sentences_path = self.temp_path / "sentences.txt"
        self.dataset_dir = self.temp_path / "sentence_data"
        config_path = self.temp_path / "config.json"

        dictionary_path.write_text(
            "\t.\tPEOPLE\tRAKYAT\t.\t.\n\n"
            "\t.\tTHAT BRAT\tBOCAH ITU\t.\t.\n\n"
            "\t.\tA BIT\tSEDIKIT\t.\t.\n",
            encoding="utf-8",
        )
        self.sentences_path.write_text(
            "People.\n"
            "Rakyat?\n\n"
            "That brat.\n"
            "Bocah itu.\n\n"
            "We have come a bit late.\n"
            "Kami datang sedikit terlambat.\n\n"
            "That brat.\n"
            "Bocah itu.\n\n"
            "Many people know.\n"
            "Banyak orang tahu.\n",
            encoding="utf-8",
        )
        build_sentence_dataset(self.sentences_path, self.dataset_dir)
        config_path.write_text(
            json.dumps(
                {
                    "dictionary_path": str(dictionary_path),
                    "sentence_data_dir": str(self.dataset_dir),
                    "red_book_enabled": False,
                    "sentence_limit": 4,
                }
            ),
            encoding="utf-8",
        )

        self.old_config = os.environ.get(sf.CONFIG_ENV_VAR)
        os.environ[sf.CONFIG_ENV_VAR] = str(config_path)
        self.reset_search_state()

    def tearDown(self):
        if self.old_config is None:
            os.environ.pop(sf.CONFIG_ENV_VAR, None)
        else:
            os.environ[sf.CONFIG_ENV_VAR] = self.old_config
        self.reset_search_state()
        self.temp_dir.cleanup()

    def reset_search_state(self):
        sf._CONFIG = None
        sf.dictionary = None
        sf.dictionary_index = None

    def test_indonesian_query_returns_english_translation(self):
        self.sentences_path.unlink()

        result = sf.search_for_word_data("rakyat")

        self.assertEqual("Rakyat?", result["sentences"][0]["match"])
        self.assertEqual("People.", result["sentences"][0]["translation"])
        self.assertEqual("indonesian", result["sentences"][0]["matched_language"])

    def test_english_query_returns_indonesian_translation(self):
        result = sf.search_for_word_data("people", sentence_limit=1)

        self.assertEqual("People.", result["sentences"][0]["match"])
        self.assertEqual("Rakyat?", result["sentences"][0]["translation"])
        self.assertEqual("english", result["sentences"][0]["matched_language"])

    def test_phrase_query_uses_sentence_pairs(self):
        result = sf.search_for_word_data("that brat", sentence_limit=None)

        self.assertEqual("That brat.", result["sentences"][0]["match"])
        self.assertEqual("Bocah itu.", result["sentences"][0]["translation"])

    def test_empty_query_returns_message(self):
        result = sf.search_for_word_data("   ")

        self.assertEqual("No word provided. Please enter a word or phrase.", result["message"])
        self.assertEqual([], result["sentences"])

    def test_no_results_are_empty(self):
        result = sf.search_for_word_data("not-present")

        self.assertEqual([], result["definitions"])
        self.assertEqual([], result["sentences"])
        self.assertFalse(result["sentences_truncated"])

    def test_duplicate_sentence_pairs_are_emitted_once(self):
        result = sf.search_for_word_data("bocah", sentence_limit=None)

        self.assertEqual(1, len(result["sentences"]))
        self.assertEqual("Bocah itu.", result["sentences"][0]["match"])

    def test_sentence_limit_marks_truncated_results(self):
        result = sf.search_for_word_data("people", sentence_limit=1)

        self.assertEqual(1, len(result["sentences"]))
        self.assertTrue(result["sentences_truncated"])
        self.assertEqual(1, result["sentence_limit"])

    def test_indexed_search_matches_streaming_shape(self):
        sf.ensure_sentence_index()

        result = sf.search_for_word_data("people", sentence_limit=1)

        self.assertEqual("People.", result["sentences"][0]["match"])
        self.assertEqual("Rakyat?", result["sentences"][0]["translation"])
        self.assertEqual("english", result["sentences"][0]["matched_language"])
        self.assertTrue(result["sentences_truncated"])

    def test_missing_sentence_dataset_returns_user_facing_result_message(self):
        for path in self.dataset_dir.rglob("*"):
            if path.is_file():
                path.unlink()
        for path in sorted((p for p in self.dataset_dir.rglob("*") if p.is_dir()), reverse=True):
            path.rmdir()
        self.dataset_dir.rmdir()

        result = sf.search_for_word_data("people")

        self.assertEqual([], result["sentences"])
        self.assertEqual(
            "Example sentences are unavailable right now.",
            result["sentence_message"],
        )

    def test_load_all_sentences_handles_missing_sentence_dataset(self):
        with mock.patch("builtins.print") as print_mock:
            for path in self.dataset_dir.rglob("*"):
                if path.is_file():
                    path.unlink()
            for path in sorted((p for p in self.dataset_dir.rglob("*") if p.is_dir()), reverse=True):
                path.rmdir()
            self.dataset_dir.rmdir()

            sf.load_all_sentences("people")

        print_mock.assert_any_call("Example sentences are unavailable right now.")


if __name__ == "__main__":
    unittest.main()
