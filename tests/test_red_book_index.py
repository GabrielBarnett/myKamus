from pathlib import Path
import sqlite3
import tempfile
import unittest

import red_book_index


def chunk(text, font, x=42, y=600, page=21):
    return {
        "text": text,
        "font": font,
        "x": x,
        "y": y,
        "page": page,
        "bold": "Bold" in font,
        "italic": "Italic" in font,
    }


class RedBookIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.pdf_path = self.temp_path / "red_book.pdf"
        self.cache_path = self.temp_path / "red_book.sqlite"
        self.pdf_path.write_bytes(b"%PDF-1.3\nfake fixture\n")

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_cache(self, entries):
        conn = sqlite3.connect(self.cache_path)
        try:
            red_book_index._create_schema(conn)
            red_book_index._write_metadata(conn, red_book_index.source_metadata(self.pdf_path))
            red_book_index._insert_entry_batch(conn, entries, 1)
            conn.commit()
        finally:
            conn.close()

    def test_schema_stores_definitions_only(self):
        conn = sqlite3.connect(self.cache_path)
        try:
            red_book_index._create_schema(conn)
            table_names = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
        finally:
            conn.close()

        self.assertIn("red_book_entries", table_names)
        self.assertIn("red_book_entry_terms", table_names)
        self.assertNotIn("red_book_examples", table_names)
        self.assertNotIn("red_book_headword_terms", table_names)

    def test_extracts_definition_from_exact_headword_entry(self):
        lines = [
            {
                "page": 475,
                "column": 0,
                "y": 518,
                "chunks": [
                    chunk("mengatakan", "Indrev-Bold", y=518),
                    chunk("[and", "Indrev-Roman", x=87, y=518),
                    chunk("ngatain", "Indrev-Bold", x=105, y=518),
                    chunk("(", "Indrev-Roman", x=130, y=518),
                    chunk("J coq", "Indrev-Italic", x=133, y=518),
                    chunk(")]", "Indrev-Roman", x=148, y=518),
                    chunk("1", "Indrev-Bold", x=156, y=518),
                    chunk("to say s.t.", "Indrev-Roman", x=160, y=518),
                    chunk("2", "Indrev-Bold", x=194, y=518),
                    chunk("to tell, inform,", "Indrev-Roman", x=198, y=518),
                ],
            },
            {
                "page": 475,
                "column": 0,
                "y": 509,
                "chunks": [
                    chunk("assert, mention.", "Indrev-Roman", x=54, y=509),
                ],
            },
        ]

        definitions = red_book_index.extract_definitions_from_lines(lines)

        self.assertEqual(1, len(definitions))
        self.assertEqual("mengatakan", definitions[0]["headword"])
        self.assertEqual(
            "1 to say s.t. 2 to tell, inform, assert, mention.",
            definitions[0]["definition"],
        )

    def test_definition_extraction_strips_example_sentence_tail(self):
        lines = [
            {
                "page": 21,
                "column": 0,
                "y": 600,
                "chunks": [
                    chunk("coba", "Indrev-Bold", y=600),
                    chunk("1", "Indrev-Bold", x=62, y=600),
                    chunk("to try.", "Indrev-Roman", x=70, y=600),
                    chunk("Ia mengatakan sesuatu.", "Indrev-Italic", x=120, y=600),
                    chunk("He said something.", "Indrev-Roman", x=190, y=600),
                ],
            },
        ]

        definitions = red_book_index.extract_definitions_from_lines(lines)

        self.assertEqual("to try.", definitions[0]["definition"])
        self.assertNotIn("Ia mengatakan sesuatu", definitions[0]["definition"])
        self.assertNotIn("He said something", definitions[0]["definition"])

    def test_definition_extraction_strips_split_italic_example_tail(self):
        lines = [
            {
                "page": 21,
                "column": 0,
                "y": 600,
                "chunks": [
                    chunk("coba", "Indrev-Bold", y=600),
                    chunk("1", "Indrev-Bold", x=62, y=600),
                    chunk("to try.", "Indrev-Roman", x=70, y=600),
                    chunk("Ia", "Indrev-Italic", x=120, y=600),
                    chunk("mengatakan", "Indrev-Italic", x=132, y=600),
                    chunk("sesuatu.", "Indrev-Italic", x=176, y=600),
                    chunk("He said something.", "Indrev-Roman", x=220, y=600),
                ],
            },
        ]

        definitions = red_book_index.extract_definitions_from_lines(lines)

        self.assertEqual("to try.", definitions[0]["definition"])
        self.assertNotIn("Ia mengatakan sesuatu", definitions[0]["definition"])
        self.assertNotIn("He said something", definitions[0]["definition"])

    def test_variant_headword_terms_are_normalized(self):
        terms = red_book_index.headword_terms("zuhara , zuharah , zuhrah and zuhrat")

        self.assertEqual(["zuhara", "zuharah", "zuhrah", "zuhrat"], terms)

    def test_search_definitions_matches_headword_not_definition_text(self):
        self.create_cache(
            [
                {
                    "headword": "mengatakan",
                    "definition": "1 to say s.t. 2 to tell, inform, assert, mention.",
                    "page": 475,
                },
                {
                    "headword": "pergi",
                    "definition": "to say mengatakan in English text only.",
                    "page": 500,
                },
            ]
        )

        results = red_book_index.search_red_book_definitions(
            "mengatakan",
            3,
            self.pdf_path,
            self.cache_path,
        )
        english_only_results = red_book_index.search_red_book_definitions(
            "say",
            3,
            self.pdf_path,
            self.cache_path,
        )

        self.assertEqual(1, len(results))
        self.assertEqual("mengatakan", results[0]["headword"])
        self.assertEqual([], english_only_results)

    def test_result_limit_applies_to_definitions(self):
        self.create_cache(
            [
                {
                    "headword": "bisa",
                    "definition": "can, able to.",
                    "page": 100,
                },
                {
                    "headword": "bisa II",
                    "definition": "poison, venom.",
                    "page": 101,
                },
            ]
        )

        results = red_book_index.search_red_book_definitions(
            "bisa",
            1,
            self.pdf_path,
            self.cache_path,
        )

        self.assertEqual(1, len(results))

    def test_missing_pdf_is_skipped(self):
        result = red_book_index.ensure_red_book_index(
            self.temp_path / "missing.pdf",
            self.cache_path,
        )

        self.assertTrue(result["skipped"])


if __name__ == "__main__":
    unittest.main()
