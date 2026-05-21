import sqlite3
import json
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

    def test_binary_manifest_raises_index_unavailable(self):
        (self.dataset_dir / "manifest.json").write_bytes(b"\xff\xfe\x00\x01")

        with self.assertRaises(search_index.IndexUnavailableError):
            search_index.ensure_sentence_dataset(self.dataset_dir)

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

    def test_dataset_with_swapped_lookup_shards_is_not_valid(self):
        multi_source_path = self.temp_path / "swap_sentences.txt"
        multi_dataset_dir = self.temp_path / "swap_sentence_data"
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
        manifest = json.loads((multi_dataset_dir / "manifest.json").read_text(encoding="utf-8"))
        first_shard = manifest["shards"][0]
        second_shard = manifest["shards"][1]

        conn = sqlite3.connect(multi_dataset_dir / "sentence_index.sqlite")
        try:
            conn.execute(
                "UPDATE sentence_lookup SET shard_file = ? WHERE sentence_id = ?",
                (second_shard["file"], first_shard["last_sentence_id"]),
            )
            conn.execute(
                "UPDATE sentence_lookup SET shard_file = ? WHERE sentence_id = ?",
                (first_shard["file"], second_shard["first_sentence_id"]),
            )
            conn.commit()
        finally:
            conn.close()

        self.assertFalse(search_index.is_dataset_valid(multi_dataset_dir))

    def test_dataset_with_corrupt_sentence_terms_is_not_valid(self):
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

        self.assertFalse(search_index.is_dataset_valid(self.dataset_dir))

    def test_repeated_validation_and_search_reuse_cached_runtime_validation(self):
        with mock.patch(
            "search_index._validate_runtime_dataset_fresh",
            wraps=search_index._validate_runtime_dataset_fresh,
        ) as validate_fresh:
            self.assertTrue(search_index.is_dataset_valid(self.dataset_dir))
            self.assertTrue(search_index.is_dataset_valid(self.dataset_dir))
            result = list(search_index.search_sentence_index("people", 1, self.dataset_dir))

        self.assertEqual(1, validate_fresh.call_count)
        self.assertEqual("People.", result[0]["match"])

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
