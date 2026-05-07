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

    def create_cache(self, examples):
        conn = sqlite3.connect(self.cache_path)
        try:
            red_book_index._create_schema(conn)
            red_book_index._write_metadata(conn, red_book_index.source_metadata(self.pdf_path))
            red_book_index._insert_batch(conn, examples, 1)
            conn.commit()
        finally:
            conn.close()

    def create_cache_with_entries(self, entries, examples=None):
        conn = sqlite3.connect(self.cache_path)
        try:
            red_book_index._create_schema(conn)
            red_book_index._write_metadata(conn, red_book_index.source_metadata(self.pdf_path))
            red_book_index._insert_entry_batch(conn, entries, 1)
            red_book_index._insert_batch(conn, examples or [], 1)
            conn.commit()
        finally:
            conn.close()

    def test_extracts_examples_from_mocked_bold_italic_roman_chunks(self):
        lines = [
            {
                "page": 21,
                "column": 0,
                "y": 600,
                "chunks": [
                    chunk("coba", "Indrev-Bold", y=600),
                    chunk("1", "Indrev-Bold", x=62, y=600),
                    chunk("to try.", "Indrev-Roman", x=70, y=600),
                ],
            },
            {
                "page": 21,
                "column": 0,
                "y": 590,
                "chunks": [
                    chunk("Ia mengatakan sesuatu.", "Indrev-Italic", x=54, y=590),
                    chunk("He said something.", "Indrev-Roman", x=140, y=590),
                ],
            },
        ]

        examples = red_book_index.extract_examples_from_lines(lines)

        self.assertEqual(1, len(examples))
        self.assertEqual("coba 1", examples[0]["headword"])
        self.assertEqual("Ia mengatakan sesuatu.", examples[0]["indonesian"])
        self.assertEqual("He said something.", examples[0]["english"])

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

    def test_variant_headword_terms_are_normalized(self):
        terms = red_book_index.headword_terms("zuhara , zuharah , zuhrah and zuhrat")

        self.assertEqual(["zuhara", "zuharah", "zuhrah", "zuhrat"], terms)

    def test_exact_headword_examples_rank_before_general_text_matches(self):
        self.create_cache(
            [
                {
                    "headword": "coba",
                    "indonesian": "Ia mengatakan sesuatu.",
                    "english": "He said something.",
                    "page": 21,
                },
                {
                    "headword": "mengatakan",
                    "indonesian": "Saya mengatakan hal itu.",
                    "english": "I said that.",
                    "page": 475,
                },
            ]
        )

        results = red_book_index.search_red_book_examples(
            "mengatakan",
            3,
            self.pdf_path,
            self.cache_path,
        )

        self.assertEqual("mengatakan", results[0]["headword"])
        self.assertEqual("coba", results[1]["headword"])

    def test_whole_word_matching_does_not_match_inside_longer_word(self):
        self.create_cache(
            [
                {
                    "headword": "coba",
                    "indonesian": "Ia mengatakan sesuatu.",
                    "english": "He said something.",
                    "page": 21,
                }
            ]
        )

        results = red_book_index.search_red_book_examples(
            "kata",
            3,
            self.pdf_path,
            self.cache_path,
        )

        self.assertEqual([], results)

    def test_search_never_matches_english_translation_text(self):
        self.create_cache(
            [
                {
                    "headword": "pergi",
                    "indonesian": "Ia pergi.",
                    "english": "He said mengatakan.",
                    "page": 21,
                }
            ]
        )

        results = red_book_index.search_red_book_examples(
            "mengatakan",
            3,
            self.pdf_path,
            self.cache_path,
        )

        self.assertEqual([], results)

    def test_result_limit_applies_across_exact_and_general_matches(self):
        self.create_cache(
            [
                {
                    "headword": "mengatakan",
                    "indonesian": "Saya mengatakan hal itu.",
                    "english": "I said that.",
                    "page": 475,
                },
                {
                    "headword": "coba",
                    "indonesian": "Ia mengatakan sesuatu.",
                    "english": "He said something.",
                    "page": 21,
                },
                {
                    "headword": "risik",
                    "indonesian": "Rumor mengatakan ia pergi.",
                    "english": "Rumors said that he left.",
                    "page": 854,
                },
                {
                    "headword": "ingin",
                    "indonesian": "Aku ingin mengatakan sesuatu.",
                    "english": "I want to say something.",
                    "page": 408,
                },
            ]
        )

        results = red_book_index.search_red_book_examples(
            "mengatakan",
            3,
            self.pdf_path,
            self.cache_path,
        )

        self.assertEqual(3, len(results))

    def test_search_definitions_matches_headword_not_definition_text(self):
        self.create_cache_with_entries(
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

    def test_general_example_matches_can_be_disabled_for_exact_definitions(self):
        self.create_cache(
            [
                {
                    "headword": "coba",
                    "indonesian": "Ia mengatakan sesuatu.",
                    "english": "He said something.",
                    "page": 21,
                }
            ]
        )

        results = red_book_index.search_red_book_examples(
            "mengatakan",
            3,
            self.pdf_path,
            self.cache_path,
            include_general=False,
        )

        self.assertEqual([], results)

    def test_missing_pdf_is_skipped(self):
        result = red_book_index.ensure_red_book_index(
            self.temp_path / "missing.pdf",
            self.cache_path,
        )

        self.assertTrue(result["skipped"])


if __name__ == "__main__":
    unittest.main()
