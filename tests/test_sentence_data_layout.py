import json
import tempfile
import unittest
from pathlib import Path

from sentence_data import layout


class SentenceDataLayoutTests(unittest.TestCase):
    def test_resolve_dataset_paths_uses_expected_file_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = layout.resolve_dataset_paths(Path(temp_dir) / "data" / "sentences")

        self.assertEqual("manifest.json", paths.manifest.name)
        self.assertEqual("sentence_index.sqlite", paths.index.name)
        self.assertEqual("shards", paths.shards_dir.name)

    def test_validate_dataset_rejects_missing_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset_dir = Path(temp_dir) / "data" / "sentences"
            dataset_dir.mkdir(parents=True)

            with self.assertRaises(layout.SentenceDataValidationError) as error:
                layout.validate_dataset(dataset_dir)

        self.assertIn("manifest.json", str(error.exception))

    def test_validate_dataset_rejects_oversized_shard(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset_dir = Path(temp_dir) / "data" / "sentences"
            shards_dir = dataset_dir / "shards"
            shards_dir.mkdir(parents=True)
            manifest_path = dataset_dir / "manifest.json"
            (dataset_dir / "sentence_index.sqlite").write_bytes(b"index")
            large_shard = shards_dir / "sentences_0001.sqlite"
            large_shard.write_bytes(b"0")
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": layout.SCHEMA_VERSION,
                        "index_file": "sentence_index.sqlite",
                        "shards": [
                            {
                                "file": "sentences_0001.sqlite",
                                "first_sentence_id": 1,
                                "last_sentence_id": 1,
                                "size_bytes": layout.MAX_SHARD_BYTES + 1,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(layout.SentenceDataValidationError) as error:
                layout.validate_dataset(dataset_dir)

        self.assertIn("80 MB", str(error.exception))


if __name__ == "__main__":
    unittest.main()
