import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from sentence_data import builder, layout


class SentenceDataBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.source_path = self.temp_path / "sentences.txt"
        self.dataset_dir = self.temp_path / "data" / "sentences"
        self.source_path.write_text(
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

    def test_build_sentence_dataset_writes_manifest_index_and_shards(self):
        result = builder.build_sentence_dataset(
            self.source_path,
            self.dataset_dir,
            target_shard_bytes=300,
        )

        self.assertEqual(layout.SCHEMA_VERSION, result["manifest"]["schema_version"])
        self.assertTrue((self.dataset_dir / "manifest.json").is_file())
        self.assertTrue((self.dataset_dir / "sentence_index.sqlite").is_file())
        self.assertGreaterEqual(len(result["manifest"]["shards"]), 2)

    def test_verify_sentence_dataset_confirms_index_rows_have_shard_rows(self):
        builder.build_sentence_dataset(self.source_path, self.dataset_dir, target_shard_bytes=300)

        verification = builder.verify_sentence_dataset(self.dataset_dir)

        self.assertEqual(3, verification["sentence_count"])
        self.assertEqual(verification["sentence_count"], verification["lookup_count"])

    def test_builder_assigns_deterministic_sentence_ids(self):
        first = builder.build_sentence_dataset(self.source_path, self.dataset_dir, target_shard_bytes=300)
        second_dir = self.temp_path / "second" / "data" / "sentences"
        second = builder.build_sentence_dataset(self.source_path, second_dir, target_shard_bytes=300)

        self.assertEqual(first["manifest"]["shards"], second["manifest"]["shards"])
        self.assertEqual(first["sentence_count"], second["sentence_count"])

    def test_failed_rebuild_leaves_existing_dataset_intact(self):
        original = builder.build_sentence_dataset(self.source_path, self.dataset_dir, target_shard_bytes=300)
        self.source_path.write_text(
            "People.\n"
            "Rakyat?\n\n"
            "Unmatched trailing line.\n",
            encoding="utf-8",
        )

        with self.assertRaises(layout.SentenceDataValidationError):
            builder.build_sentence_dataset(self.source_path, self.dataset_dir, target_shard_bytes=300)

        verification = builder.verify_sentence_dataset(self.dataset_dir)
        manifest = layout.validate_dataset(self.dataset_dir)["manifest"]
        self.assertEqual(original["manifest"], manifest)
        self.assertEqual(original["sentence_count"], verification["sentence_count"])

    def test_verify_sentence_dataset_rejects_missing_or_inconsistent_sentence_terms(self):
        builder.build_sentence_dataset(self.source_path, self.dataset_dir, target_shard_bytes=300)

        conn = sqlite3.connect(self.dataset_dir / "sentence_index.sqlite")
        try:
            conn.execute("DELETE FROM sentence_terms WHERE term = ? AND sentence_id = ?", ("people", 1))
            conn.commit()
        finally:
            conn.close()

        with self.assertRaises(layout.SentenceDataValidationError):
            builder.verify_sentence_dataset(self.dataset_dir)

    def test_failed_swap_restores_original_dataset(self):
        original = builder.build_sentence_dataset(self.source_path, self.dataset_dir, target_shard_bytes=300)
        self.source_path.write_text(
            "Updated people.\n"
            "Rakyat baru?\n\n"
            "Another pair.\n"
            "Pasangan lain.\n",
            encoding="utf-8",
        )
        real_replace = builder.os.replace
        replace_calls = []

        def flaky_replace(source, destination):
            replace_calls.append((Path(source).name, Path(destination).name))
            if len(replace_calls) == 2:
                raise OSError("swap failed")
            return real_replace(source, destination)

        with mock.patch("sentence_data.builder.os.replace", side_effect=flaky_replace):
            with self.assertRaises(OSError):
                builder.build_sentence_dataset(self.source_path, self.dataset_dir, target_shard_bytes=300)

        verification = builder.verify_sentence_dataset(self.dataset_dir)
        manifest = layout.validate_dataset(self.dataset_dir)["manifest"]
        self.assertEqual(original["manifest"], manifest)
        self.assertEqual(original["sentence_count"], verification["sentence_count"])
        self.assertEqual(
            [
                ("sentences", "sentences.bak"),
                (replace_calls[1][0], "sentences"),
                ("sentences.bak", "sentences"),
            ],
            replace_calls,
        )
        self.assertFalse(self.dataset_dir.with_name("sentences.bak").exists())


if __name__ == "__main__":
    unittest.main()
