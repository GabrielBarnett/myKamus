"""
SQLite-backed sentence-pair index for myKamus.
"""

from pathlib import Path
import os
import re
import sqlite3


SCHEMA_VERSION = "1"
PROGRESS_STEP_BYTES = 1024 * 1024


class IndexUnavailableError(RuntimeError):
    pass


def source_metadata(sentences_path):
    path = Path(sentences_path).resolve()
    stat = path.stat()
    return {
        "source_path": str(path),
        "source_size": str(stat.st_size),
        "source_mtime_ns": str(stat.st_mtime_ns),
        "schema_version": SCHEMA_VERSION,
    }


def _connect(cache_path):
    return sqlite3.connect(str(cache_path))


def _clean_line(line):
    return " ".join(line.strip().split())


def _build_phrase_pattern(query):
    return re.compile(rf"(?<!\w){re.escape(query)}(?!\w)", re.IGNORECASE)


def _has_fts5(conn):
    try:
        conn.execute("CREATE VIRTUAL TABLE fts_probe USING fts5(value)")
        conn.execute("DROP TABLE fts_probe")
        return True
    except sqlite3.OperationalError:
        return False


def _read_metadata(conn):
    try:
        rows = conn.execute("SELECT key, value FROM metadata").fetchall()
    except sqlite3.Error:
        return {}
    return dict(rows)


def _write_metadata(conn, metadata, fts_enabled):
    rows = dict(metadata)
    rows["fts_enabled"] = "1" if fts_enabled else "0"
    conn.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        sorted(rows.items()),
    )


def _create_schema(conn, fts_enabled):
    conn.executescript(
        """
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE sentence_pairs (
            id INTEGER PRIMARY KEY,
            english TEXT NOT NULL,
            indonesian TEXT NOT NULL
        );
        """
    )
    if fts_enabled:
        conn.execute(
            "CREATE VIRTUAL TABLE sentence_pairs_fts USING fts5(english, indonesian)"
        )


def _emit_progress(progress_callback, processed_bytes, total_bytes, force=False):
    if progress_callback is None:
        return
    percent = 100.0 if total_bytes <= 0 else min(100.0, processed_bytes * 100.0 / total_bytes)
    progress_callback(
        {
            "processed_bytes": processed_bytes,
            "total_bytes": total_bytes,
            "percent": percent,
            "complete": force or processed_bytes >= total_bytes,
        }
    )


def _insert_batch(conn, batch, fts_enabled):
    conn.executemany(
        "INSERT INTO sentence_pairs(english, indonesian) VALUES (?, ?)",
        batch,
    )
    if fts_enabled:
        start_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0] - len(batch) + 1
        fts_rows = [
            (start_id + offset, english, indonesian)
            for offset, (english, indonesian) in enumerate(batch)
        ]
        conn.executemany(
            "INSERT INTO sentence_pairs_fts(rowid, english, indonesian) VALUES (?, ?, ?)",
            fts_rows,
        )


def build_sentence_index(sentences_path, cache_path, progress_callback=None):
    sentences_path = Path(sentences_path)
    cache_path = Path(cache_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = cache_path.with_name(cache_path.name + ".tmp")
    if temp_path.exists():
        temp_path.unlink()

    metadata = source_metadata(sentences_path)
    total_bytes = int(metadata["source_size"])
    processed_bytes = 0
    last_reported_bytes = 0
    pending_english = None
    batch = []

    _emit_progress(progress_callback, 0, total_bytes)
    conn = _connect(temp_path)
    try:
        fts_enabled = _has_fts5(conn)
        _create_schema(conn, fts_enabled)
        _write_metadata(conn, metadata, fts_enabled)

        with sentences_path.open("rb") as sentences_file:
            for raw_line in sentences_file:
                processed_bytes += len(raw_line)
                line = _clean_line(raw_line.decode("utf-8", errors="replace"))
                if line:
                    if pending_english is None:
                        pending_english = line
                    else:
                        batch.append((pending_english, line))
                        pending_english = None
                    if len(batch) >= 5000:
                        _insert_batch(conn, batch, fts_enabled)
                        batch.clear()
                if processed_bytes - last_reported_bytes >= PROGRESS_STEP_BYTES:
                    _emit_progress(progress_callback, processed_bytes, total_bytes)
                    last_reported_bytes = processed_bytes
        if batch:
            _insert_batch(conn, batch, fts_enabled)
        conn.commit()
    except Exception:
        conn.close()
        if temp_path.exists():
            temp_path.unlink()
        raise
    else:
        conn.close()
        os.replace(temp_path, cache_path)
        _emit_progress(progress_callback, total_bytes, total_bytes, force=True)
        return {
            "cache_path": str(cache_path),
            "sentences_path": str(sentences_path),
            "fts_enabled": fts_enabled,
        }


def is_index_valid(sentences_path, cache_path):
    cache_path = Path(cache_path)
    if not cache_path.exists():
        return False
    try:
        expected = source_metadata(sentences_path)
        conn = _connect(cache_path)
        try:
            actual = _read_metadata(conn)
        finally:
            conn.close()
    except (OSError, sqlite3.Error):
        return False
    return all(actual.get(key) == value for key, value in expected.items())


def ensure_sentence_index(sentences_path, cache_path, progress_callback=None):
    if is_index_valid(sentences_path, cache_path):
        _emit_progress(
            progress_callback,
            int(source_metadata(sentences_path)["source_size"]),
            int(source_metadata(sentences_path)["source_size"]),
            force=True,
        )
        return {"cache_path": str(cache_path), "rebuilt": False}
    result = build_sentence_index(sentences_path, cache_path, progress_callback)
    result["rebuilt"] = True
    return result


def _fts_query(query):
    terms = re.findall(r"\w+", query.casefold())
    if not terms:
        return None
    if len(terms) == 1:
        return '"' + terms[0].replace('"', '""') + '"'
    return '"' + " ".join(term.replace('"', '""') for term in terms) + '"'


def _escape_like(value):
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def _iter_candidate_pairs(conn, query):
    metadata = _read_metadata(conn)
    if metadata.get("fts_enabled") == "1":
        query_string = _fts_query(query)
        if query_string is not None:
            yield from conn.execute(
                """
                SELECT p.english, p.indonesian
                FROM sentence_pairs_fts f
                JOIN sentence_pairs p ON p.id = f.rowid
                WHERE sentence_pairs_fts MATCH ?
                ORDER BY p.id
                """,
                (query_string,),
            )
            return

    like_query = "%" + _escape_like(query.casefold()) + "%"
    yield from conn.execute(
        """
        SELECT english, indonesian
        FROM sentence_pairs
        WHERE lower(english) LIKE ? ESCAPE '\\'
           OR lower(indonesian) LIKE ? ESCAPE '\\'
        ORDER BY id
        """,
        (like_query, like_query),
    )


def search_sentence_index(query, limit, sentences_path, cache_path):
    if not is_index_valid(sentences_path, cache_path):
        raise IndexUnavailableError("Sentence index is missing or stale.")

    pattern = _build_phrase_pattern(query)
    emitted = set()
    emitted_count = 0
    conn = _connect(cache_path)
    try:
        for english, indonesian in _iter_candidate_pairs(conn, query):
            english_matches = bool(pattern.search(english))
            indonesian_matches = bool(pattern.search(indonesian))
            if not english_matches and not indonesian_matches:
                continue
            pair_key = (english, indonesian)
            if pair_key in emitted:
                continue
            if limit is not None and emitted_count >= limit:
                break
            emitted.add(pair_key)
            emitted_count += 1
            if indonesian_matches:
                yield {
                    "match": indonesian,
                    "translation": english,
                    "matched_language": "indonesian",
                    "english": english,
                    "indonesian": indonesian,
                }
            else:
                yield {
                    "match": english,
                    "translation": indonesian,
                    "matched_language": "english",
                    "english": english,
                    "indonesian": indonesian,
                }
    finally:
        conn.close()
