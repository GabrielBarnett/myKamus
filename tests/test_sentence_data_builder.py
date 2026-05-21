import sqlite3
import tempfile
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main()
