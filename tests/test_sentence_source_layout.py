import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from sentence_source import layout


class SentenceSourceLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "sentence_source"
        self.chunks_dir = self.root / "chunks"
        self.chunks_dir.mkdir(parents=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_chunk(self, name, text):
        path = self.chunks_dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def write_manifest(self, chunks):
        manifest = {
            "schema_version": layout.SCHEMA_VERSION,
            "source_format": layout.SOURCE_FORMAT,
            "chunks": chunks,
            "total_pair_count": sum(chunk["pair_count"] for chunk in chunks),
        }
        (self.root / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        return manifest

    def chunk_entry(self, path, pair_count=1):
        data = path.read_bytes()
        return {
            "file": path.name,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "pair_count": pair_count,
        }

    def test_valid_source_dataset_loads_paths_and_manifest(self):
        chunk = self.write_chunk("en-id_sentences_0001.txt", "People.\nRakyat?\n")
        manifest = self.write_manifest([self.chunk_entry(chunk)])

        validated = layout.validate_source_dataset(self.root)

        self.assertEqual(self.root, validated["paths"].root)
        self.assertEqual(manifest["total_pair_count"], validated["manifest"]["total_pair_count"])
        self.assertEqual(1, validated["total_pair_count"])

    def test_missing_manifest_reports_manifest_json(self):
        with self.assertRaisesRegex(layout.SentenceSourceValidationError, "manifest.json"):
            layout.validate_source_dataset(self.root)

    def test_manifest_must_be_json_object(self):
        (self.root / "manifest.json").write_text("[]", encoding="utf-8")

        with self.assertRaisesRegex(layout.SentenceSourceValidationError, "JSON object"):
            layout.validate_source_dataset(self.root)

    def test_rejects_missing_chunk(self):
        self.write_manifest(
            [
                {
                    "file": "en-id_sentences_0001.txt",
                    "size_bytes": 10,
                    "sha256": "0" * 64,
                    "pair_count": 1,
                }
            ]
        )

        with self.assertRaisesRegex(layout.SentenceSourceValidationError, "missing"):
            layout.validate_source_dataset(self.root)

    def test_rejects_oversized_chunk_from_manifest_or_disk(self):
        chunk = self.write_chunk("en-id_sentences_0001.txt", "People.\nRakyat?\n")
        entry = self.chunk_entry(chunk)
        entry["size_bytes"] = layout.MAX_CHUNK_BYTES + 1
        self.write_manifest([entry])

        with self.assertRaisesRegex(layout.SentenceSourceValidationError, "80 MB"):
            layout.validate_source_dataset(self.root)

    def test_verify_checksums_rejects_changed_chunk(self):
        chunk = self.write_chunk("en-id_sentences_0001.txt", "People.\nRakyat?\n")
        self.write_manifest([self.chunk_entry(chunk)])
        chunk.write_text("Changed.\nBerubah.\n", encoding="utf-8")

        with self.assertRaisesRegex(layout.SentenceSourceValidationError, "checksum"):
            layout.validate_source_dataset(self.root, verify_checksums=True)

    def test_rejects_mismatched_total_pair_count(self):
        chunk = self.write_chunk("en-id_sentences_0001.txt", "People.\nRakyat?\n")
        self.write_manifest([self.chunk_entry(chunk)])
        manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        manifest["total_pair_count"] = 2
        (self.root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

        with self.assertRaisesRegex(layout.SentenceSourceValidationError, "total_pair_count"):
            layout.validate_source_dataset(self.root)

    def test_manifest_signature_changes_when_manifest_changes(self):
        chunk = self.write_chunk("en-id_sentences_0001.txt", "People.\nRakyat?\n")
        self.write_manifest([self.chunk_entry(chunk)])
        first = layout.manifest_signature(layout.validate_source_dataset(self.root)["manifest"])

        second_chunk = self.write_chunk("en-id_sentences_0002.txt", "Language.\nBahasa.\n")
        self.write_manifest([self.chunk_entry(chunk), self.chunk_entry(second_chunk)])
        second = layout.manifest_signature(layout.validate_source_dataset(self.root)["manifest"])

        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
