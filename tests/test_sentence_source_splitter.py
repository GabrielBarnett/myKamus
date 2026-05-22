import json
from pathlib import Path
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
