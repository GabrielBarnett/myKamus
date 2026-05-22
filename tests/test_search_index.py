import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from sentence_source import splitter
import search_index


class SearchIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.source_path = self.temp_path / "sentences.txt"
        self.source_dir = self.temp_path / "sentence_source"
        self.cache_path = self.temp_path / ".mykamus_cache" / "search.sqlite"
        self.source_path.write_text(
            "People.\n"
            "Rakyat?\n\n"
            "That brat.\n"
            "Bocah itu.\n\n"
            "Many people know.\n"
            "Banyak orang tahu.\n\n"
            "Many people know.\n"
            "Banyak orang tahu.\n",
            encoding="utf-8",
        )
        splitter.split_sentence_source(self.source_path, self.source_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_ensure_sentence_index_builds_local_cache_from_chunks(self):
        progress = []

        result = search_index.ensure_sentence_index(
            self.source_dir,
            self.cache_path,
            progress_callback=progress.append,
        )

        self.assertTrue(self.cache_path.is_file())
        self.assertTrue(result["rebuilt"])
        self.assertEqual(100.0, progress[-1]["percent"])

    def test_index_valid_after_build_and_reused_without_rebuild(self):
        search_index.ensure_sentence_index(self.source_dir, self.cache_path)

        self.assertTrue(search_index.is_index_valid(self.source_dir, self.cache_path))
        with mock.patch("search_index.build_sentence_index") as build:
            result = search_index.ensure_sentence_index(self.source_dir, self.cache_path)

        build.assert_not_called()
        self.assertFalse(result["rebuilt"])

    def test_search_is_bidirectional_after_source_file_removed(self):
        search_index.ensure_sentence_index(self.source_dir, self.cache_path)
        self.source_path.unlink()

        english_result = list(search_index.search_sentence_index("people", 1, self.source_dir, self.cache_path))
        indonesian_result = list(search_index.search_sentence_index("rakyat", 1, self.source_dir, self.cache_path))

        self.assertEqual("People.", english_result[0]["match"])
        self.assertEqual("Rakyat?", english_result[0]["translation"])
        self.assertEqual("Rakyat?", indonesian_result[0]["match"])
        self.assertEqual("People.", indonesian_result[0]["translation"])

    def test_cache_rebuilds_when_manifest_signature_changes(self):
        search_index.ensure_sentence_index(self.source_dir, self.cache_path)
        self.source_path.write_text("New people.\nRakyat baru.\n", encoding="utf-8")
        splitter.split_sentence_source(self.source_path, self.source_dir)

        self.assertFalse(search_index.is_index_valid(self.source_dir, self.cache_path))
        result = search_index.ensure_sentence_index(self.source_dir, self.cache_path)

        self.assertTrue(result["rebuilt"])
        matches = list(search_index.search_sentence_index("new people", 1, self.source_dir, self.cache_path))
        self.assertEqual("New people.", matches[0]["match"])

    def test_failed_rebuild_keeps_existing_cache(self):
        search_index.ensure_sentence_index(self.source_dir, self.cache_path)
        original_source = (
            "People.\n"
            "Rakyat?\n\n"
            "That brat.\n"
            "Bocah itu.\n\n"
            "Many people know.\n"
            "Banyak orang tahu.\n\n"
            "Many people know.\n"
            "Banyak orang tahu.\n"
        )
        self.source_path.write_text("New people.\nRakyat baru.\n", encoding="utf-8")
        splitter.split_sentence_source(self.source_path, self.source_dir)

        with mock.patch("search_index._insert_batch", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                search_index.ensure_sentence_index(self.source_dir, self.cache_path)

        self.assertTrue(self.cache_path.is_file())
        self.assertFalse(self.cache_path.with_name(self.cache_path.name + ".tmp").exists())
        self.source_path.write_text(original_source, encoding="utf-8")
        splitter.split_sentence_source(self.source_path, self.source_dir)
        old_matches = list(search_index.search_sentence_index("people", 1, self.source_dir, self.cache_path))
        self.assertEqual("People.", old_matches[0]["match"])

    def test_replace_failure_removes_temp_cache_and_keeps_existing_cache(self):
        search_index.ensure_sentence_index(self.source_dir, self.cache_path)
        original_source = self.source_path.read_text(encoding="utf-8")
        self.source_path.write_text("New people.\nRakyat baru.\n", encoding="utf-8")
        splitter.split_sentence_source(self.source_path, self.source_dir)

        with mock.patch("search_index.os.replace", side_effect=OSError("locked")):
            with self.assertRaises(search_index.IndexUnavailableError):
                search_index.ensure_sentence_index(self.source_dir, self.cache_path)

        self.assertFalse(self.cache_path.with_name(self.cache_path.name + ".tmp").exists())
        self.source_path.write_text(original_source, encoding="utf-8")
        splitter.split_sentence_source(self.source_path, self.source_dir)
        old_matches = list(search_index.search_sentence_index("people", 1, self.source_dir, self.cache_path))
        self.assertEqual("People.", old_matches[0]["match"])

    def test_missing_source_chunks_raise_index_unavailable(self):
        for path in (self.source_dir / "chunks").glob("*.txt"):
            path.unlink()

        with self.assertRaises(search_index.IndexUnavailableError):
            list(search_index.search_sentence_index("people", 1, self.source_dir, self.cache_path))

    def test_missing_source_chunks_raise_index_unavailable_on_ensure(self):
        for path in (self.source_dir / "chunks").glob("*.txt"):
            path.unlink()

        with self.assertRaises(search_index.IndexUnavailableError):
            search_index.ensure_sentence_index(self.source_dir, self.cache_path)

    def test_phrase_search_like_that_brat(self):
        search_index.ensure_sentence_index(self.source_dir, self.cache_path)

        result = list(search_index.search_sentence_index("that brat", 1, self.source_dir, self.cache_path))

        self.assertEqual("That brat.", result[0]["match"])
        self.assertEqual("Bocah itu.", result[0]["translation"])

    def test_build_reads_chunks_in_manifest_order(self):
        multi_source_path = self.temp_path / "many_sentences.txt"
        multi_source_dir = self.temp_path / "many_sentence_source"
        multi_cache_path = self.temp_path / ".mykamus_cache" / "many.sqlite"
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
        splitter.split_sentence_source(
            multi_source_path,
            multi_source_dir,
            target_chunk_bytes=40,
        )

        chunk_files = sorted((multi_source_dir / "chunks").glob("*.txt"))
        self.assertGreaterEqual(len(chunk_files), 2)
        search_index.ensure_sentence_index(multi_source_dir, multi_cache_path)

        result = list(search_index.search_sentence_index("people", None, multi_source_dir, multi_cache_path))

        self.assertEqual(
            ["Alpha people.", "Beta people.", "Gamma people.", "Delta people."],
            [row["match"] for row in result],
        )

    def test_search_suppresses_duplicate_pairs(self):
        search_index.ensure_sentence_index(self.source_dir, self.cache_path)

        result = list(search_index.search_sentence_index("many people know", None, self.source_dir, self.cache_path))

        self.assertEqual(1, len(result))
        self.assertEqual("Many people know.", result[0]["match"])

    def test_search_respects_limit(self):
        search_index.ensure_sentence_index(self.source_dir, self.cache_path)

        result = list(search_index.search_sentence_index("people", 1, self.source_dir, self.cache_path))

        self.assertEqual(1, len(result))

    def test_corrupt_cache_returns_false_from_is_index_valid(self):
        search_index.ensure_sentence_index(self.source_dir, self.cache_path)
        self.cache_path.write_text("not a sqlite database", encoding="utf-8")

        self.assertFalse(search_index.is_index_valid(self.source_dir, self.cache_path))

    def test_invalid_source_returns_false_from_is_index_valid(self):
        (self.source_dir / "manifest.json").write_text("not json", encoding="utf-8")

        self.assertFalse(search_index.is_index_valid(self.source_dir, self.cache_path))

    def test_search_uses_like_fallback_when_fts5_unavailable(self):
        with mock.patch("search_index._has_fts5", return_value=False):
            search_index.ensure_sentence_index(self.source_dir, self.cache_path)

        conn = sqlite3.connect(self.cache_path)
        try:
            metadata = dict(conn.execute("SELECT key, value FROM metadata").fetchall())
        finally:
            conn.close()

        self.assertEqual("0", metadata["fts_enabled"])
        result = list(search_index.search_sentence_index("that brat", 1, self.source_dir, self.cache_path))
        self.assertEqual("That brat.", result[0]["match"])


if __name__ == "__main__":
    unittest.main()
