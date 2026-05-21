import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from sentence_data.builder import build_sentence_dataset
import red_book_index
import search_index


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        dictionary_path = self.temp_path / "dict.txt"
        self.sentences_path = self.temp_path / "sentences.txt"
        self.dataset_dir = self.temp_path / "sentence_data"
        self.config_path = self.temp_path / "config.json"
        self.red_book_pdf_path = self.temp_path / "red_book.pdf"
        self.red_book_cache_path = self.temp_path / "red_book.sqlite"

        dictionary_path.write_text("\t.\tPEOPLE\tRAKYAT\t.\t.\n", encoding="utf-8")
        self.sentences_path.write_text(
            "People.\n"
            "Rakyat?\n\n"
            "Many people know.\n"
            "Banyak orang tahu.\n",
            encoding="utf-8",
        )
        build_sentence_dataset(self.sentences_path, self.dataset_dir)
        self.config_path.write_text(
            json.dumps(
                {
                    "dictionary_path": str(dictionary_path),
                    "sentence_data_dir": str(self.dataset_dir),
                    "red_book_pdf_path": str(self.red_book_pdf_path),
                    "red_book_cache_path": str(self.red_book_cache_path),
                    "red_book_results_limit": 3,
                    "red_book_enabled": True,
                    "sentence_limit": 1,
                }
            ),
            encoding="utf-8",
        )
        self.red_book_pdf_path.write_bytes(b"%PDF-1.3\nfake fixture\n")

    def tearDown(self):
        self.temp_dir.cleanup()

    def run_cli(self, *args):
        env = dict(os.environ)
        env["MYKAMUS_CONFIG"] = str(self.config_path)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, "cli.py", *args],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_help_does_not_print_loading_banner(self):
        result = self.run_cli("--help")

        self.assertEqual(0, result.returncode)
        self.assertIn("Search the myKamus dictionary and sentence corpus.", result.stdout)
        self.assertNotIn("myKamus is loading", result.stdout)

    def test_missing_query_prints_message(self):
        result = self.run_cli()

        self.assertEqual(0, result.returncode)
        self.assertIn("Please provide a word or phrase to search for.", result.stdout)

    def test_normal_query_uses_bidirectional_sentence_pair(self):
        result = self.run_cli("people")

        self.assertEqual(0, result.returncode)
        self.assertIn("Match: People.", result.stdout)
        self.assertIn("Translation: Rakyat?", result.stdout)
        self.assertIn("Showing the first 1 matching sentence pairs.", result.stdout)

    def test_all_sentences_streams_all_matches(self):
        result = self.run_cli("people", "--all-sentences")

        self.assertEqual(0, result.returncode)
        self.assertIn("Match: People.", result.stdout)
        self.assertIn("Match: Many people know.", result.stdout)
        self.assertIn("All example sentences for the word people have been loaded.", result.stdout)

    def test_normal_query_uses_existing_index_when_available(self):
        search_index.ensure_sentence_dataset(self.dataset_dir)

        result = self.run_cli("people")

        self.assertEqual(0, result.returncode)
        self.assertIn("Match: People.", result.stdout)
        self.assertIn("Translation: Rakyat?", result.stdout)

    def test_cli_prints_red_book_results_when_index_is_available(self):
        conn = red_book_index._connect(self.red_book_cache_path)
        try:
            red_book_index._create_schema(conn)
            red_book_index._write_metadata(
                conn,
                red_book_index.source_metadata(self.red_book_pdf_path),
            )
            red_book_index._insert_entry_batch(
                conn,
                [
                    {
                        "headword": "mengatakan",
                        "definition": "1 to say s.t. 2 to tell, inform, assert, mention.",
                        "page": 475,
                    }
                ],
                1,
            )
            conn.commit()
        finally:
            conn.close()

        result = self.run_cli("mengatakan")

        self.assertEqual(0, result.returncode)
        self.assertIn("Red Book Results:", result.stdout)
        self.assertIn(
            "Definition: 1 to say s.t. 2 to tell, inform, assert, mention.",
            result.stdout,
        )

    def test_cli_does_not_print_red_book_sentence_examples(self):
        conn = red_book_index._connect(self.red_book_cache_path)
        try:
            red_book_index._create_schema(conn)
            red_book_index._write_metadata(
                conn,
                red_book_index.source_metadata(self.red_book_pdf_path),
            )
            red_book_index._insert_entry_batch(
                conn,
                [
                    {
                        "headword": "mengatakan",
                        "definition": "1 to say s.t. 2 to tell, inform, assert, mention.",
                        "page": 475,
                    }
                ],
                1,
            )
            conn.commit()
        finally:
            conn.close()

        result = self.run_cli("mengatakan")

        self.assertEqual(0, result.returncode)
        self.assertIn(
            "Definition: 1 to say s.t. 2 to tell, inform, assert, mention.",
            result.stdout,
        )
        self.assertNotIn("Indonesian: Ia mengatakan sesuatu.", result.stdout)
        self.assertNotIn("English: He said something.", result.stdout)


if __name__ == "__main__":
    unittest.main()
