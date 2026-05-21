import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from sentence_data.builder import build_sentence_dataset
import search_index


class SearchIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.source_path = self.temp_path / "sentences.txt"
        self.dataset_dir = self.temp_path / "sentences"
        self.source_path.write_text(
            "People.\n"
            "Rakyat?\n\n"
            "That brat.\n"
            "Bocah itu.\n\n"
            "Many people know.\n"
            "Banyak orang tahu.\n",
            encoding="utf-8",
        )
        build_sentence_dataset(self.source_path, self.dataset_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dataset_validates(self):
        self.assertTrue(search_index.is_dataset_valid(self.dataset_dir))

    def test_index_search_is_bidirectional(self):
        self.source_path.unlink()

        english_result = list(
            search_index.search_sentence_index(
                "people",
                1,
                self.dataset_dir,
            )
        )
        indonesian_result = list(
            search_index.search_sentence_index(
                "rakyat",
                1,
                self.dataset_dir,
            )
        )

        self.assertEqual("People.", english_result[0]["match"])
        self.assertEqual("Rakyat?", english_result[0]["translation"])
        self.assertEqual("Rakyat?", indonesian_result[0]["match"])
        self.assertEqual("People.", indonesian_result[0]["translation"])

    def test_search_routes_across_multiple_shards_in_sentence_id_order(self):
        multi_source_path = self.temp_path / "many_sentences.txt"
        multi_dataset_dir = self.temp_path / "many_sentence_data"
        multi_source_path.write_text(
            "Alpha people.\n"
            "Alpha rakyat.\n\n"
            "Beta people.\n"
            "Beta rakyat.\n\n"
            "Gamma people.\n"
            "Gamma rakyat.\n\n"
            "Delta people.\n"
            "Delta rakyat.\n",
            encoding="utf-8",
        )
        build_sentence_dataset(
            multi_source_path,
            multi_dataset_dir,
            target_shard_bytes=300,
        )
        multi_source_path.unlink()

        shard_files = sorted((multi_dataset_dir / "shards").glob("*.sqlite"))
        self.assertGreaterEqual(len(shard_files), 2)

        result = list(search_index.search_sentence_index("people", None, multi_dataset_dir))

        self.assertEqual(
            ["Alpha people.", "Beta people.", "Gamma people.", "Delta people."],
            [row["match"] for row in result],
        )
        self.assertEqual(
            ["Alpha rakyat.", "Beta rakyat.", "Gamma rakyat.", "Delta rakyat."],
            [row["translation"] for row in result],
        )

    def test_progress_reaches_one_hundred_percent(self):
        progress_values = []

        search_index.ensure_sentence_dataset(
            self.dataset_dir,
            progress_callback=lambda progress: progress_values.append(progress["percent"]),
        )

        self.assertGreaterEqual(len(progress_values), 1)
        self.assertEqual(100.0, progress_values[-1])
        self.assertEqual(progress_values, sorted(progress_values))

    def test_validation_failure_raises_index_unavailable(self):
        with mock.patch("search_index.validate_dataset", side_effect=search_index.SentenceDataValidationError("broken")):
            with self.assertRaises(search_index.IndexUnavailableError):
                list(search_index.search_sentence_index("people", 1, self.dataset_dir))

    def test_corrupt_index_database_raises_index_unavailable(self):
        (self.dataset_dir / "sentence_index.sqlite").write_text(
            "not a sqlite database",
            encoding="utf-8",
        )

        with self.assertRaises(search_index.IndexUnavailableError):
            list(search_index.search_sentence_index("people", 1, self.dataset_dir))

    def test_index_connection_open_failure_raises_index_unavailable(self):
        with mock.patch(
            "search_index._connect",
            side_effect=sqlite3.DatabaseError("cannot open database"),
        ):
            with self.assertRaises(search_index.IndexUnavailableError):
                list(search_index.search_sentence_index("people", 1, self.dataset_dir))

    def test_dataset_with_truncated_runtime_index_is_not_valid(self):
        conn = sqlite3.connect(self.dataset_dir / "sentence_index.sqlite")
        try:
            conn.execute("DELETE FROM sentence_lookup WHERE sentence_id = 1")
            conn.commit()
        finally:
            conn.close()

        self.assertFalse(search_index.is_dataset_valid(self.dataset_dir))

    def test_search_uses_dataset_without_fts_runtime_dependency(self):
        result = list(
            search_index.search_sentence_index(
                "that brat",
                1,
                self.dataset_dir,
            )
        )

        self.assertEqual("That brat.", result[0]["match"])
        self.assertEqual("Bocah itu.", result[0]["translation"])


if __name__ == "__main__":
    unittest.main()
