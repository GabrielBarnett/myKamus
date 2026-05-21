import json
import os
import sqlite3
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

    def test_corrupt_sentence_dataset_returns_user_facing_result_message(self):
        (self.dataset_dir / "sentence_index.sqlite").write_text(
            "not a sqlite database",
            encoding="utf-8",
        )

        self.assertFalse(sf.is_sentence_index_valid())

        result = sf.search_for_word_data("people")

        self.assertEqual([], result["sentences"])
        self.assertEqual(
            "Example sentences are unavailable right now.",
            result["sentence_message"],
        )

    def test_logically_broken_sentence_dataset_returns_unavailable_message(self):
        conn = sqlite3.connect(self.dataset_dir / "sentence_index.sqlite")
        try:
            conn.execute(
                """
                UPDATE sentence_terms
                SET term = 'persons'
                WHERE sentence_id = 1 AND term = 'people'
                """
            )
            conn.commit()
        finally:
            conn.close()

        result = sf.search_for_word_data("people", sentence_limit=None)

        self.assertEqual([], result["sentences"])
        self.assertEqual(
            "Example sentences are unavailable right now.",
            result["sentence_message"],
        )

    def test_malformed_manifest_structure_returns_unavailable_message(self):
        manifest_path = self.dataset_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        del manifest["shards"][0]["first_sentence_id"]
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

        result = sf.search_for_word_data("people", sentence_limit=None)

        self.assertEqual([], result["sentences"])
        self.assertEqual(
            "Example sentences are unavailable right now.",
            result["sentence_message"],
        )

    def test_legacy_sentences_config_derives_sentence_data_dir(self):
        legacy_temp_dir = tempfile.TemporaryDirectory()
        legacy_temp_path = Path(legacy_temp_dir.name)
        try:
            dictionary_path = legacy_temp_path / "dict.txt"
            legacy_sentences_path = legacy_temp_path / "sentences.txt"
            legacy_dataset_dir = legacy_temp_path / "data" / "sentences"
            config_path = legacy_temp_path / "legacy_config.json"

            dictionary_path.write_text("\t.\tPEOPLE\tRAKYAT\t.\t.\n", encoding="utf-8")
            legacy_sentences_path.write_text(
                "People.\n"
                "Rakyat?\n",
                encoding="utf-8",
            )
            build_sentence_dataset(legacy_sentences_path, legacy_dataset_dir)
            config_path.write_text(
                json.dumps(
                    {
                        "dictionary_path": str(dictionary_path),
                        "sentences_path": str(legacy_sentences_path),
                        "cache_path": str(legacy_temp_path / "search.sqlite"),
                        "red_book_enabled": False,
                    }
                ),
                encoding="utf-8",
            )

            old_config = os.environ.get(sf.CONFIG_ENV_VAR)
            os.environ[sf.CONFIG_ENV_VAR] = str(config_path)
            self.reset_search_state()
            try:
                self.assertEqual(legacy_dataset_dir, sf.sentence_data_dir())
                result = sf.search_for_word_data("people", sentence_limit=None)
            finally:
                if old_config is None:
                    os.environ.pop(sf.CONFIG_ENV_VAR, None)
                else:
                    os.environ[sf.CONFIG_ENV_VAR] = old_config
                self.reset_search_state()

            self.assertEqual("People.", result["sentences"][0]["match"])
            self.assertEqual("Rakyat?", result["sentences"][0]["translation"])
        finally:
            legacy_temp_dir.cleanup()

    def test_mid_iteration_failure_returns_unavailable_message_without_partial_sentences(self):
        def broken_sentence_iter(query, limit):
            yield {
                "match": "People.",
                "translation": "Rakyat?",
                "matched_language": "english",
                "english": "People.",
                "indonesian": "Rakyat?",
            }
            raise sf.search_index.IndexUnavailableError("broken during iteration")

        with mock.patch(
            "search_functions.iter_matching_indexed_sentence_pairs",
            side_effect=broken_sentence_iter,
        ):
            result = sf.search_for_word_data("people", sentence_limit=None)

        rendered = sf.render_search_result(result)

        self.assertEqual([], result["sentences"])
        self.assertFalse(result["sentences_truncated"])
        self.assertEqual(
            "Example sentences are unavailable right now.",
            result["sentence_message"],
        )
        self.assertIn("Example sentences are unavailable right now.", rendered)
        self.assertNotIn("Match: People.", rendered)

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

    def test_load_all_sentences_mid_iteration_failure_hides_partial_output(self):
        def broken_sentence_iter(query, limit):
            yield {
                "match": "People.",
                "translation": "Rakyat?",
                "matched_language": "english",
                "english": "People.",
                "indonesian": "Rakyat?",
            }
            raise sf.search_index.IndexUnavailableError("broken during iteration")

        with mock.patch(
            "search_functions.iter_matching_indexed_sentence_pairs",
            side_effect=broken_sentence_iter,
        ), mock.patch("builtins.print") as print_mock:
            sf.load_all_sentences("people", sentence_limit=None)

        printed_values = {
            args[0]
            for args, _kwargs in print_mock.call_args_list
            if args
        }
        self.assertIn("Example sentences are unavailable right now.", printed_values)
        self.assertNotIn("1:\nMatch: People.\nTranslation: Rakyat?", printed_values)
        self.assertNotIn("", printed_values)


if __name__ == "__main__":
    unittest.main()
