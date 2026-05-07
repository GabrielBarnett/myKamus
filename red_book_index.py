"""
SQLite-backed index for entries and examples extracted from the Red Book PDF.
"""

from pathlib import Path
import os
import re
import sqlite3


SCHEMA_VERSION = "2"
FIRST_ENTRY_PAGE = 21
LAST_ENTRY_PAGE = 1123
ENTRY_START_MAX_X = 58
COLUMN_SPLIT_X = 250


class RedBookUnavailableError(RuntimeError):
    pass


def source_metadata(pdf_path):
    path = Path(pdf_path).resolve()
    stat = path.stat()
    return {
        "source_path": str(path),
        "source_size": str(stat.st_size),
        "source_mtime_ns": str(stat.st_mtime_ns),
        "schema_version": SCHEMA_VERSION,
        "first_entry_page": str(FIRST_ENTRY_PAGE),
        "last_entry_page": str(LAST_ENTRY_PAGE),
    }


def _connect(cache_path):
    return sqlite3.connect(str(cache_path))


def _read_metadata(conn):
    try:
        rows = conn.execute("SELECT key, value FROM metadata").fetchall()
    except sqlite3.Error:
        return {}
    return dict(rows)


def _write_metadata(conn, metadata):
    conn.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        sorted(metadata.items()),
    )


def _create_schema(conn):
    conn.executescript(
        """
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE red_book_examples (
            id INTEGER PRIMARY KEY,
            headword TEXT NOT NULL,
            headword_normalized TEXT NOT NULL,
            indonesian TEXT NOT NULL,
            indonesian_normalized TEXT NOT NULL,
            english TEXT NOT NULL,
            page INTEGER NOT NULL,
            position INTEGER NOT NULL
        );

        CREATE TABLE red_book_headword_terms (
            term TEXT NOT NULL,
            example_id INTEGER NOT NULL REFERENCES red_book_examples(id)
        );

        CREATE TABLE red_book_entries (
            id INTEGER PRIMARY KEY,
            headword TEXT NOT NULL,
            headword_normalized TEXT NOT NULL,
            definition TEXT NOT NULL,
            page INTEGER NOT NULL,
            position INTEGER NOT NULL
        );

        CREATE TABLE red_book_entry_terms (
            term TEXT NOT NULL,
            entry_id INTEGER NOT NULL REFERENCES red_book_entries(id)
        );

        CREATE INDEX red_book_headword_term_idx
            ON red_book_headword_terms(term, example_id);
        CREATE INDEX red_book_examples_position_idx
            ON red_book_examples(position);
        CREATE INDEX red_book_entry_term_idx
            ON red_book_entry_terms(term, entry_id);
        CREATE INDEX red_book_entries_position_idx
            ON red_book_entries(position);
        """
    )


def normalize_pdf_text(text):
    replacements = {
        "\u20ac": "fi",
        "\u00b6": "fl",
        "\ufb01": "fi",
        "\ufb02": "fl",
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"(?<=[A-Za-zéÉ])-\s+(?=[A-Za-zéÉ])", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def normalize_lookup_text(text):
    text = normalize_pdf_text(text).casefold()
    text = text.replace("`", "'")
    return text


def _whole_word_pattern(query):
    normalized = normalize_lookup_text(query)
    return re.compile(
        rf"(?<![\w'\-\u2019]){re.escape(normalized)}(?![\w'\-\u2019])",
        re.IGNORECASE,
    )


def _clean_chunk_text(text):
    return normalize_pdf_text(text)


def _is_bold_font(font_name):
    return "Bold" in str(font_name)


def _is_italic_font(font_name):
    return "Italic" in str(font_name)


def _is_word_like(text):
    return bool(re.search(r"[A-Za-zÀ-ž]", text))


def _is_roman_marker(text):
    return bool(re.fullmatch(r"[IVXLCDM]+/?", text))


def _is_entry_start_line(chunks):
    if not chunks:
        return False
    first = chunks[0]
    text = first["text"]
    if first["y"] > 660 or first["y"] < 45:
        return False
    relative_x = first["x"] if first["x"] < COLUMN_SPLIT_X else first["x"] - COLUMN_SPLIT_X
    if relative_x > ENTRY_START_MAX_X:
        return False
    if not first["bold"]:
        return False
    if not _is_word_like(text):
        return False
    if text[0].isdigit() or text.startswith(("–", "~")):
        return False
    return True


def _column_for_x(x):
    return 0 if x < COLUMN_SPLIT_X else 1


def order_pdf_chunks(chunks):
    filtered = [
        chunk
        for chunk in chunks
        if chunk["text"] and 45 <= chunk["y"] <= 660
    ]
    grouped = {}
    for chunk in filtered:
        key = (chunk["page"], _column_for_x(chunk["x"]), round(chunk["y"] * 2) / 2)
        grouped.setdefault(key, []).append(chunk)

    lines = []
    for (page, column, y), line_chunks in grouped.items():
        line_chunks.sort(key=lambda chunk: chunk["x"])
        lines.append(
            {
                "page": page,
                "column": column,
                "y": y,
                "chunks": line_chunks,
            }
        )
    return sorted(lines, key=lambda line: (line["page"], line["column"], -line["y"]))


def _leading_headword_text(chunks):
    parts = []
    for chunk in chunks:
        text = chunk["text"]
        if chunk["bold"]:
            parts.append(text)
            continue
        if text in {"and", "or", ","} and parts:
            parts.append(text)
            continue
        break
    return normalize_pdf_text(" ".join(parts))


def _strip_headword_noise(text):
    text = re.sub(r"\[[^\]]+\]", " ", text)
    text = re.sub(r"/[^/]+/", " ", text)
    text = re.sub(r"\b[IVXLCDM]+\b", " ", text)
    text = re.sub(r"\b\d+\b", " ", text)
    text = text.strip(" .,/;:")
    return normalize_pdf_text(text)


def headword_terms(headword):
    cleaned = _strip_headword_noise(headword)
    raw_terms = re.split(r"\s+(?:and|or)\s+|,", cleaned)
    terms = []
    for term in raw_terms:
        term = _strip_headword_noise(term)
        if not term or not _is_word_like(term):
            continue
        normalized = normalize_lookup_text(term)
        if normalized and normalized not in terms:
            terms.append(normalized)
    return terms


def _chunks_to_text(chunks):
    return normalize_pdf_text(" ".join(chunk["text"] for chunk in chunks))


def _replace_tilde(indonesian, headword):
    terms = headword_terms(headword)
    if not terms:
        return indonesian
    display_term = terms[0]
    return indonesian.replace("~", display_term)


def _looks_like_indonesian_example(text):
    if not _is_word_like(text):
        return False
    if len(text) < 8:
        return False
    if re.fullmatch(r"[A-Za-z]{1,4}", text):
        return False
    return len(re.findall(r"[A-Za-zÀ-ž]+", text)) >= 2


def _looks_like_english_translation(text):
    if not _is_word_like(text):
        return False
    if len(text) < 6:
        return False
    return len(re.findall(r"[A-Za-zÀ-ž]+", text)) >= 2


def extract_examples_from_entry(entry):
    chunks = entry["chunks"]
    examples = []
    index = 0
    while index < len(chunks):
        chunk = chunks[index]
        if not chunk["italic"] or chunk["bold"]:
            index += 1
            continue

        indonesian_chunks = []
        while index < len(chunks):
            current = chunks[index]
            if current["italic"] and not current["bold"]:
                indonesian_chunks.append(current)
                index += 1
                continue
            if current["text"] in {".", ",", ";", ":", "?", "!", "-", "–"}:
                indonesian_chunks.append(current)
                index += 1
                continue
            break

        english_chunks = []
        while index < len(chunks):
            current = chunks[index]
            if current["italic"]:
                break
            if current["bold"] and _is_word_like(current["text"]):
                break
            english_chunks.append(current)
            index += 1

        indonesian = _replace_tilde(_chunks_to_text(indonesian_chunks), entry["headword"])
        english = _chunks_to_text(english_chunks)
        if _looks_like_indonesian_example(indonesian) and _looks_like_english_translation(english):
            examples.append(
                {
                    "headword": entry["headword"],
                    "indonesian": indonesian,
                    "english": english,
                    "page": entry["page"],
                }
            )
    return examples


def extract_entries_from_lines(lines):
    entries = []
    current_entry = None
    for line in lines:
        chunks = line["chunks"]
        if _is_entry_start_line(chunks):
            if current_entry is not None:
                entries.append(current_entry)
            headword = _leading_headword_text(chunks)
            current_entry = {
                "headword": headword,
                "page": line["page"],
                "chunks": list(chunks),
            }
        elif current_entry is not None:
            current_entry["chunks"].extend(chunks)
    if current_entry is not None:
        entries.append(current_entry)

    return entries


def extract_examples_from_lines(lines):
    entries = extract_entries_from_lines(lines)

    examples = []
    for entry in entries:
        examples.extend(extract_examples_from_entry(entry))
    return examples


def _strip_initial_variant_note(text):
    return re.sub(r"^\s*\[[^\]]+\]\s*", "", text)


def _strip_example_tail(definition, entry):
    for chunk in entry["chunks"]:
        if not chunk["italic"]:
            continue
        italic_text = _chunks_to_text([chunk])
        if _looks_like_indonesian_example(italic_text):
            index = definition.find(italic_text)
            if index > 0:
                return definition[:index]
    return definition


def extract_definition_from_entry(entry):
    full_text = _chunks_to_text(entry["chunks"])
    headword = entry["headword"]
    if full_text[: len(headword)].casefold() == headword.casefold():
        definition = full_text[len(headword):]
    else:
        definition = full_text
    definition = _strip_initial_variant_note(definition)
    definition = _strip_example_tail(definition, entry)
    definition = normalize_pdf_text(definition)
    if not definition or not _is_word_like(definition):
        return None
    return {
        "headword": headword,
        "definition": definition,
        "page": entry["page"],
    }


def extract_definitions_from_lines(lines):
    definitions = []
    for entry in extract_entries_from_lines(lines):
        definition = extract_definition_from_entry(entry)
        if definition is not None:
            definitions.append(definition)
    return definitions


def _extract_page_chunks(page, page_number):
    chunks = []

    def visitor(text, cm, tm, font_dict, font_size):
        cleaned = _clean_chunk_text(text)
        if not cleaned:
            return
        font_name = font_dict.get("/BaseFont", "") if font_dict else ""
        chunks.append(
            {
                "text": cleaned,
                "font": str(font_name),
                "x": float(tm[4]),
                "y": float(tm[5]),
                "page": page_number,
                "bold": _is_bold_font(font_name),
                "italic": _is_italic_font(font_name),
            }
        )

    page.extract_text(visitor_text=visitor)
    return chunks


def _iter_pdf_page_records(pdf_path, progress_callback=None):
    try:
        from pypdf import PdfReader
    except ImportError as error:
        raise RedBookUnavailableError(
            "Missing dependency 'pypdf'. Install dependencies with: pip install -r requirements.txt"
        ) from error

    reader = PdfReader(str(pdf_path))
    last_page = min(LAST_ENTRY_PAGE, len(reader.pages))
    first_page = min(FIRST_ENTRY_PAGE, last_page)
    total_pages = max(0, last_page - first_page + 1)

    for index, page_number in enumerate(range(first_page, last_page + 1), start=1):
        page = reader.pages[page_number - 1]
        lines = order_pdf_chunks(_extract_page_chunks(page, page_number))
        entries = extract_entries_from_lines(lines)
        yield {
            "definitions": [
                definition
                for definition in (
                    extract_definition_from_entry(entry)
                    for entry in entries
                )
                if definition is not None
            ],
            "examples": [
                example
                for entry in entries
                for example in extract_examples_from_entry(entry)
            ],
        }
        if progress_callback is not None:
            progress_callback(
                {
                    "processed_pages": index,
                    "total_pages": total_pages,
                    "percent": 100.0 if total_pages == 0 else index * 100.0 / total_pages,
                    "complete": index >= total_pages,
                }
            )


def _iter_pdf_examples(pdf_path, progress_callback=None):
    for records in _iter_pdf_page_records(pdf_path, progress_callback=progress_callback):
        yield from records["examples"]


def _insert_batch(conn, batch, start_position):
    if not batch:
        return
    rows = [
        (
            example["headword"],
            normalize_lookup_text(example["headword"]),
            example["indonesian"],
            normalize_lookup_text(example["indonesian"]),
            example["english"],
            int(example["page"]),
            start_position + offset,
        )
        for offset, example in enumerate(batch)
    ]
    conn.executemany(
        """
        INSERT INTO red_book_examples(
            headword,
            headword_normalized,
            indonesian,
            indonesian_normalized,
            english,
            page,
            position
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        rows,
    )
    first_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0] - len(batch) + 1
    term_rows = []
    for offset, example in enumerate(batch):
        for term in headword_terms(example["headword"]):
            term_rows.append((term, first_id + offset))
    conn.executemany(
        "INSERT INTO red_book_headword_terms(term, example_id) VALUES (?, ?)",
        term_rows,
    )


def _insert_entry_batch(conn, batch, start_position):
    if not batch:
        return
    rows = [
        (
            entry["headword"],
            normalize_lookup_text(entry["headword"]),
            entry["definition"],
            int(entry["page"]),
            start_position + offset,
        )
        for offset, entry in enumerate(batch)
    ]
    conn.executemany(
        """
        INSERT INTO red_book_entries(
            headword,
            headword_normalized,
            definition,
            page,
            position
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        rows,
    )
    first_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0] - len(batch) + 1
    term_rows = []
    for offset, entry in enumerate(batch):
        for term in headword_terms(entry["headword"]):
            term_rows.append((term, first_id + offset))
    conn.executemany(
        "INSERT INTO red_book_entry_terms(term, entry_id) VALUES (?, ?)",
        term_rows,
    )


def build_red_book_index(pdf_path, cache_path, progress_callback=None):
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        return {"cache_path": str(cache_path), "rebuilt": False, "skipped": True}

    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = cache_path.with_name(cache_path.name + ".tmp")
    if temp_path.exists():
        temp_path.unlink()

    conn = _connect(temp_path)
    example_batch = []
    entry_batch = []
    example_position = 1
    entry_position = 1
    try:
        _create_schema(conn)
        _write_metadata(conn, source_metadata(pdf_path))
        for records in _iter_pdf_page_records(pdf_path, progress_callback=progress_callback):
            entry_batch.extend(records["definitions"])
            example_batch.extend(records["examples"])
            if len(entry_batch) >= 1000:
                _insert_entry_batch(conn, entry_batch, entry_position)
                entry_position += len(entry_batch)
                entry_batch.clear()
            if len(example_batch) >= 1000:
                _insert_batch(conn, example_batch, example_position)
                example_position += len(example_batch)
                example_batch.clear()
        if entry_batch:
            _insert_entry_batch(conn, entry_batch, entry_position)
        if example_batch:
            _insert_batch(conn, example_batch, example_position)
        conn.commit()
    except Exception:
        conn.close()
        if temp_path.exists():
            temp_path.unlink()
        raise
    else:
        conn.close()
        os.replace(temp_path, cache_path)
        return {"cache_path": str(cache_path), "rebuilt": True, "skipped": False}


def is_red_book_index_valid(pdf_path, cache_path):
    pdf_path = Path(pdf_path)
    cache_path = Path(cache_path)
    if not pdf_path.exists() or not cache_path.exists():
        return False
    try:
        expected = source_metadata(pdf_path)
        conn = _connect(cache_path)
        try:
            actual = _read_metadata(conn)
        finally:
            conn.close()
    except (OSError, sqlite3.Error):
        return False
    return all(actual.get(key) == value for key, value in expected.items())


def ensure_red_book_index(pdf_path, cache_path, progress_callback=None):
    if not Path(pdf_path).exists():
        return {"cache_path": str(cache_path), "rebuilt": False, "skipped": True}
    if is_red_book_index_valid(pdf_path, cache_path):
        if progress_callback is not None:
            progress_callback(
                {
                    "processed_pages": 1,
                    "total_pages": 1,
                    "percent": 100.0,
                    "complete": True,
                }
            )
        return {"cache_path": str(cache_path), "rebuilt": False, "skipped": False}
    return build_red_book_index(pdf_path, cache_path, progress_callback=progress_callback)


def _select_examples(conn, sql, params, limit, seen):
    results = []
    for row in conn.execute(sql, params):
        example_id, headword, indonesian, english, page = row
        if example_id in seen:
            continue
        seen.add(example_id)
        results.append(
            {
                "headword": headword,
                "indonesian": indonesian,
                "english": english,
                "page": page,
            }
        )
        if len(results) >= limit:
            break
    return results


def _select_definitions(conn, sql, params, limit, seen):
    results = []
    for row in conn.execute(sql, params):
        entry_id, headword, definition, page = row
        if entry_id in seen:
            continue
        seen.add(entry_id)
        results.append(
            {
                "headword": headword,
                "definition": definition,
                "page": page,
            }
        )
        if len(results) >= limit:
            break
    return results


def search_red_book_definitions(query, limit, pdf_path, cache_path):
    if limit is None:
        limit = 3
    if limit is not None and limit <= 0:
        return []
    if not is_red_book_index_valid(pdf_path, cache_path):
        raise RedBookUnavailableError("Red Book index is missing or stale.")

    normalized_query = normalize_lookup_text(query)
    seen = set()
    conn = _connect(cache_path)
    try:
        return _select_definitions(
            conn,
            """
            SELECT e.id, e.headword, e.definition, e.page
            FROM red_book_entries e
            JOIN red_book_entry_terms t ON t.entry_id = e.id
            WHERE t.term = ?
            ORDER BY e.position
            """,
            (normalized_query,),
            limit,
            seen,
        )
    finally:
        conn.close()


def search_red_book_examples(query, limit, pdf_path, cache_path, include_general=True):
    if limit is None:
        limit = 3
    if limit is not None and limit <= 0:
        return []
    if not is_red_book_index_valid(pdf_path, cache_path):
        raise RedBookUnavailableError("Red Book index is missing or stale.")

    normalized_query = normalize_lookup_text(query)
    pattern = _whole_word_pattern(normalized_query)
    results = []
    seen = set()
    conn = _connect(cache_path)
    try:
        exact_results = _select_examples(
            conn,
            """
            SELECT e.id, e.headword, e.indonesian, e.english, e.page
            FROM red_book_examples e
            JOIN red_book_headword_terms t ON t.example_id = e.id
            WHERE t.term = ?
            ORDER BY e.position
            """,
            (normalized_query,),
            limit,
            seen,
        )
        results.extend(exact_results)
        remaining = limit - len(results)
        if remaining <= 0 or not include_general:
            return results

        like_query = "%" + normalized_query.replace("%", "\\%").replace("_", "\\_") + "%"
        for row in conn.execute(
            """
            SELECT id, headword, indonesian, english, page, indonesian_normalized
            FROM red_book_examples
            WHERE indonesian_normalized LIKE ? ESCAPE '\\'
            ORDER BY position
            """,
            (like_query,),
        ):
            example_id, headword, indonesian, english, page, indonesian_normalized = row
            if example_id in seen or not pattern.search(indonesian_normalized):
                continue
            seen.add(example_id)
            results.append(
                {
                    "headword": headword,
                    "indonesian": indonesian,
                    "english": english,
                    "page": page,
                }
            )
            if len(results) >= limit:
                break
    finally:
        conn.close()
    return results
