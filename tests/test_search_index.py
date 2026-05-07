from pathlib import Path
import tempfile
import unittest
from unittest import mock

import search_index


class SearchIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.sentences_path = self.temp_path / "sentences.txt"
        self.cache_path = self.temp_path / "cache.sqlite"
        self.sentences_path.write_text(
            "People.\n"
            "Rakyat?\n\n"
            "That brat.\n"
            "Bocah itu.\n\n"
            "Many people know.\n"
            "Banyak orang tahu.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_index_builds_and_validates_metadata(self):
        search_index.ensure_sentence_index(self.sentences_path, self.cache_path)

        self.assertTrue(search_index.is_index_valid(self.sentences_path, self.cache_path))

    def test_stale_source_invalidates_index(self):
        search_index.ensure_sentence_index(self.sentences_path, self.cache_path)

        self.sentences_path.write_text(
            self.sentences_path.read_text(encoding="utf-8") + "New line.\nBaris baru.\n",
            encoding="utf-8",
        )

        self.assertFalse(search_index.is_index_valid(self.sentences_path, self.cache_path))

    def test_index_search_is_bidirectional(self):
        search_index.ensure_sentence_index(self.sentences_path, self.cache_path)

        english_result = list(
            search_index.search_sentence_index(
                "people",
                1,
                self.sentences_path,
                self.cache_path,
            )
        )
        indonesian_result = list(
            search_index.search_sentence_index(
                "rakyat",
                1,
                self.sentences_path,
                self.cache_path,
            )
        )

        self.assertEqual("People.", english_result[0]["match"])
        self.assertEqual("Rakyat?", english_result[0]["translation"])
        self.assertEqual("Rakyat?", indonesian_result[0]["match"])
        self.assertEqual("People.", indonesian_result[0]["translation"])

    def test_progress_reaches_one_hundred_percent(self):
        progress_values = []

        search_index.ensure_sentence_index(
            self.sentences_path,
            self.cache_path,
            progress_callback=lambda progress: progress_values.append(progress["percent"]),
        )

        self.assertGreaterEqual(len(progress_values), 2)
        self.assertEqual(0.0, progress_values[0])
        self.assertEqual(100.0, progress_values[-1])
        self.assertEqual(progress_values, sorted(progress_values))

    def test_like_fallback_searches_without_fts5(self):
        with mock.patch("search_index._has_fts5", return_value=False):
            search_index.ensure_sentence_index(self.sentences_path, self.cache_path)

        result = list(
            search_index.search_sentence_index(
                "that brat",
                1,
                self.sentences_path,
                self.cache_path,
            )
        )

        self.assertEqual("That brat.", result[0]["match"])
        self.assertEqual("Bocah itu.", result[0]["translation"])


if __name__ == "__main__":
    unittest.main()
