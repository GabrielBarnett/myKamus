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

    def test_validate_dataset_accepts_valid_dataset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset_dir = Path(temp_dir) / "data" / "sentences"
            shards_dir = dataset_dir / "shards"
            shards_dir.mkdir(parents=True)
            (dataset_dir / "sentence_index.sqlite").write_bytes(b"index")
            shard_path = shards_dir / "sentences_0001.sqlite"
            shard_path.write_bytes(b"ok")
            (dataset_dir / "manifest.json").write_text(
                json.dumps(
                    {
                        "schema_version": layout.SCHEMA_VERSION,
                        "index_file": "sentence_index.sqlite",
                        "shards": [
                            {
                                "file": "sentences_0001.sqlite",
                                "first_sentence_id": 1,
                                "last_sentence_id": 1,
                                "size_bytes": 2,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            result = layout.validate_dataset(dataset_dir)

        self.assertEqual(dataset_dir, result["paths"].root)
        self.assertEqual("sentences_0001.sqlite", result["manifest"]["shards"][0]["file"])

    def test_validate_dataset_rejects_malformed_shard_entries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset_dir = Path(temp_dir) / "data" / "sentences"
            shards_dir = dataset_dir / "shards"
            shards_dir.mkdir(parents=True)
            (dataset_dir / "sentence_index.sqlite").write_bytes(b"index")
            (shards_dir / "sentences_0001.sqlite").write_bytes(b"ok")

            malformed_manifests = [
                {
                    "schema_version": layout.SCHEMA_VERSION,
                    "index_file": "sentence_index.sqlite",
                    "shards": [
                        {
                            "first_sentence_id": 1,
                            "last_sentence_id": 1,
                            "size_bytes": 2,
                        }
                    ],
                },
                {
                    "schema_version": layout.SCHEMA_VERSION,
                    "index_file": "sentence_index.sqlite",
                    "shards": [
                        {
                            "file": "sentences_0001.sqlite",
                            "first_sentence_id": 1,
                            "last_sentence_id": 1,
                            "size_bytes": "not-a-number",
                        }
                    ],
                },
            ]

            for manifest_data in malformed_manifests:
                (dataset_dir / "manifest.json").write_text(
                    json.dumps(manifest_data),
                    encoding="utf-8",
                )

                with self.subTest(manifest_data=manifest_data):
                    with self.assertRaises(layout.SentenceDataValidationError):
                        layout.validate_dataset(dataset_dir)

    def test_validate_dataset_rejects_non_object_manifest_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset_dir = Path(temp_dir) / "data" / "sentences"
            shards_dir = dataset_dir / "shards"
            shards_dir.mkdir(parents=True)
            (dataset_dir / "sentence_index.sqlite").write_bytes(b"index")
            (dataset_dir / "manifest.json").write_text(
                json.dumps([]),
                encoding="utf-8",
            )

            with self.assertRaises(layout.SentenceDataValidationError):
                layout.validate_dataset(dataset_dir)


if __name__ == "__main__":
    unittest.main()