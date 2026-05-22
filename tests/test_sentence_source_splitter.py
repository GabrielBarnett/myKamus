import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from sentence_source import layout, splitter


class SentenceSourceSplitterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.source_path = self.temp_path / "en-id_sentences.txt"
        self.output_dir = self.temp_path / "sentence_source"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_splitter_preserves_pair_boundaries_across_chunks(self):
        self.source_path.write_text(
            "People.\n"
            "Rakyat?\n\n"
            "That brat.\n"
            "Bocah itu.\n\n"
            "Many people know.\n"
            "Banyak orang tahu.\n",
            encoding="utf-8",
        )

        result = splitter.split_sentence_source(
            self.source_path,
            self.output_dir,
            target_chunk_bytes=32,
        )

        manifest = layout.validate_source_dataset(
            self.output_dir,
            verify_checksums=True,
        )["manifest"]
        self.assertEqual(3, manifest["total_pair_count"])
        self.assertGreaterEqual(len(manifest["chunks"]), 2)
        for chunk in manifest["chunks"]:
            lines = [
                line
                for line in (self.output_dir / "chunks" / chunk["file"])
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            self.assertEqual(0, len(lines) % 2)
            self.assertEqual(chunk["pair_count"], len(lines) // 2)
        self.assertEqual(3, result["total_pair_count"])

    def test_splitter_rejects_unmatched_trailing_line(self):
        self.source_path.write_text("People.\n", encoding="utf-8")

        with self.assertRaisesRegex(
            layout.SentenceSourceValidationError,
            "unmatched trailing line",
        ):
            splitter.split_sentence_source(self.source_path, self.output_dir)

    def test_splitter_rejects_pair_larger_than_limit(self):
        self.source_path.write_text(
            "English sentence.\nKalimat Indonesia.\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            layout.SentenceSourceValidationError,
            "larger than the chunk size limit",
        ):
            splitter.split_sentence_source(
                self.source_path,
                self.output_dir,
                target_chunk_bytes=10,
                max_chunk_bytes=20,
            )

    def test_splitter_output_is_deterministic(self):
        self.source_path.write_text(
            "People.\nRakyat?\nThat brat.\nBocah itu.\n",
            encoding="utf-8",
        )
        first_dir = self.temp_path / "first"
        second_dir = self.temp_path / "second"

        splitter.split_sentence_source(self.source_path, first_dir, target_chunk_bytes=40)
        splitter.split_sentence_source(self.source_path, second_dir, target_chunk_bytes=40)

        first_manifest = json.loads(
            (first_dir / "manifest.json").read_text(encoding="utf-8")
        )
        second_manifest = json.loads(
            (second_dir / "manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(first_manifest, second_manifest)

    def test_verify_sentence_source_returns_counts(self):
        self.source_path.write_text("People.\nRakyat?\n", encoding="utf-8")
        splitter.split_sentence_source(self.source_path, self.output_dir)

        result = splitter.verify_sentence_source(self.output_dir)

        self.assertEqual(1, result["total_pair_count"])
        self.assertEqual(1, result["chunk_count"])

    def test_verify_rejects_chunk_with_unmatched_trailing_line(self):
        self.source_path.write_text("People.\nRakyat?\n", encoding="utf-8")
        splitter.split_sentence_source(self.source_path, self.output_dir)
        manifest_path = self.output_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        chunk_path = self.output_dir / "chunks" / manifest["chunks"][0]["file"]
        chunk_path.write_text("People.\n", encoding="utf-8")
        manifest["chunks"][0]["size_bytes"] = chunk_path.stat().st_size
        manifest["chunks"][0]["sha256"] = layout.file_sha256(chunk_path)
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        with self.assertRaisesRegex(
            layout.SentenceSourceValidationError,
            r"en-id_sentences_0001\.txt.*unmatched trailing line",
        ):
            splitter.verify_sentence_source(self.output_dir)

    def test_verify_rejects_chunk_pair_count_mismatch(self):
        chunks_dir = self.output_dir / "chunks"
        chunks_dir.mkdir(parents=True)
        first_chunk = chunks_dir / "en-id_sentences_0001.txt"
        second_chunk = chunks_dir / "en-id_sentences_0002.txt"
        first_chunk.write_text("People.\nRakyat?\n", encoding="utf-8")
        second_chunk.write_text(
            "That brat.\nBocah itu.\nMany people know.\nBanyak orang tahu.\n",
            encoding="utf-8",
        )
        manifest = {
            "schema_version": layout.SCHEMA_VERSION,
            "source_format": layout.SOURCE_FORMAT,
            "chunks": [
                {
                    "file": first_chunk.name,
                    "size_bytes": first_chunk.stat().st_size,
                    "sha256": layout.file_sha256(first_chunk),
                    "pair_count": 2,
                },
                {
                    "file": second_chunk.name,
                    "size_bytes": second_chunk.stat().st_size,
                    "sha256": layout.file_sha256(second_chunk),
                    "pair_count": 1,
                },
            ],
            "total_pair_count": 3,
        }
        (self.output_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(
            layout.SentenceSourceValidationError,
            r"en-id_sentences_0001\.txt.*pair_count",
        ):
            splitter.verify_sentence_source(self.output_dir)

    def test_cli_validation_error_returns_concise_stderr(self):
        result = subprocess.run(
            [
                sys.executable,
                "scripts/split_sentence_source.py",
                "--verify",
                "--output",
                str(self.output_dir),
            ],
            cwd=Path(__file__).resolve().parents[1],
            capture_output=True,
            text=True,
        )

        self.assertEqual(1, result.returncode)
        self.assertIn("manifest.json", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_splitter_preserves_preexisting_bak_sibling(self):
        self.source_path.write_text("People.\nRakyat?\n", encoding="utf-8")
        splitter.split_sentence_source(self.source_path, self.output_dir)
        bak_dir = self.temp_path / "sentence_source.bak"
        bak_dir.mkdir()
        (bak_dir / "user-file.txt").write_text("keep me", encoding="utf-8")
        self.source_path.write_text("That brat.\nBocah itu.\n", encoding="utf-8")

        splitter.split_sentence_source(self.source_path, self.output_dir)

        self.assertEqual(
            "keep me",
            (bak_dir / "user-file.txt").read_text(encoding="utf-8"),
        )

    def test_failed_replacement_restores_previous_output(self):
        self.source_path.write_text("People.\nRakyat?\n", encoding="utf-8")
        splitter.split_sentence_source(self.source_path, self.output_dir)
        previous_manifest = (self.output_dir / "manifest.json").read_text(encoding="utf-8")
        self.source_path.write_text("That brat.\nBocah itu.\n", encoding="utf-8")

        move_calls = []

        def fail_staging_to_output(source, destination):
            move_calls.append((Path(source), Path(destination)))
            if len(move_calls) == 2:
                raise OSError("simulated move failure")
            Path(source).replace(destination)

        with mock.patch(
            "sentence_source.splitter._move_directory",
            side_effect=fail_staging_to_output,
            create=True,
        ):
            with self.assertRaisesRegex(OSError, "simulated move failure"):
                splitter.split_sentence_source(self.source_path, self.output_dir)

        self.assertTrue(self.output_dir.is_dir())
        self.assertEqual(
            previous_manifest,
            (self.output_dir / "manifest.json").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
