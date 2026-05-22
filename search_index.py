"""
SQLite-backed local sentence-pair cache for myKamus.
"""

from pathlib import Path
import hashlib
import os
import re
import sqlite3

from sentence_source import layout as source_layout
from sentence_source.layout import SentenceSourceValidationError, validate_source_dataset


SCHEMA_VERSION = "1"
PROGRESS_STEP_BYTES = 1024 * 1024
BATCH_SIZE = 5000


class IndexUnavailableError(RuntimeError):
    pass


SOURCE_FAILURES = (
    OSError,
    SentenceSourceValidationError,
    UnicodeDecodeError,
)
_VALIDATION_CACHE = {}


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


def _expected_metadata(validated, fts_enabled=None):
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "source_schema_version": source_layout.SCHEMA_VERSION,
        "source_manifest_signature": validated["manifest_signature"],
        "source_pair_count": str(validated["total_pair_count"]),
    }
    if fts_enabled is not None:
        metadata["fts_enabled"] = "1" if fts_enabled else "0"
    return metadata


def _write_metadata(conn, metadata):
    conn.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        sorted(metadata.items()),
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
    try:
        progress_callback(
            {
                "title": "Building sentence cache...",
                "processed_bytes": processed_bytes,
                "total_bytes": total_bytes,
                "percent": percent,
                "complete": force or processed_bytes >= total_bytes,
            }
        )
    except Exception as error:
        try:
            error._mykamus_progress_callback = True
        except Exception:
            pass
        raise


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


def _iter_chunk_pairs(chunk_path, expected_sha256, progress):
    digest = hashlib.sha256()
    pending_english = None
    pair_count = 0
    processed_bytes = 0

    with Path(chunk_path).open("rb") as chunk_file:
        for raw_line in chunk_file:
            digest.update(raw_line)
            processed_bytes += len(raw_line)
            line = _clean_line(raw_line.decode("utf-8"))
            if not line:
                yield None, processed_bytes
                continue
            if pending_english is None:
                pending_english = line
            else:
                pair_count += 1
                yield (pending_english, line), processed_bytes
                pending_english = None

    if pending_english is not None:
        raise SentenceSourceValidationError(
            f"Sentence source chunk {Path(chunk_path).name} has an unmatched trailing line."
        )
    if digest.hexdigest() != expected_sha256:
        raise SentenceSourceValidationError(
            f"Sentence source chunk checksum does not match manifest: {Path(chunk_path).name}"
        )
    progress["pair_count"] = pair_count


def _validate_cache_shape(conn, metadata):
    pair_count = conn.execute("SELECT COUNT(*) FROM sentence_pairs").fetchone()[0]
    if str(pair_count) != metadata.get("source_pair_count"):
        return False
    if metadata.get("fts_enabled") == "1":
        fts_count = conn.execute("SELECT COUNT(*) FROM sentence_pairs_fts").fetchone()[0]
        if fts_count != pair_count:
            return False
    return True


def _remove_temp_cache(temp_path):
    if Path(temp_path).exists():
        Path(temp_path).unlink()


def _raise_index_unavailable(error):
    raise IndexUnavailableError("Sentence index is missing or stale.") from error


def _file_signature(path):
    path = Path(path)
    stat = path.stat()
    return (str(path.resolve()), stat.st_size, stat.st_mtime_ns)


def _metadata_signature(metadata):
    return tuple(sorted(metadata.items()))


def _chunk_signatures(validated):
    chunks_dir = validated["paths"].chunks_dir
    return tuple(
        _file_signature(chunks_dir / chunk["file"])
        for chunk in validated["manifest"]["chunks"]
    )


def _validation_cache_key(validated, cache_path, expected_metadata):
    return (
        str(validated["paths"].root.resolve()),
        str(Path(cache_path).resolve()),
        _file_signature(validated["paths"].manifest),
        _chunk_signatures(validated),
        _file_signature(cache_path),
        _metadata_signature(expected_metadata),
    )


def _remember_valid_index(validated, cache_path):
    expected = _expected_metadata(validated)
    _VALIDATION_CACHE[_validation_cache_key(validated, cache_path, expected)] = True


def build_sentence_index(source_dir, cache_path, progress_callback=None, validated=None):
    conn = None
    temp_path = None
    try:
        if validated is None:
            validated = validate_source_dataset(source_dir, verify_checksums=False)

        cache_path = Path(cache_path)
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = cache_path.with_name(cache_path.name + ".tmp")
        _VALIDATION_CACHE.clear()
        _remove_temp_cache(temp_path)

        chunks_dir = validated["paths"].chunks_dir
        chunks = validated["manifest"]["chunks"]
        total_bytes = sum(chunk["size_bytes"] for chunk in chunks)
        processed_bytes = 0
        last_reported_bytes = 0
        batch = []
        inserted_pairs = 0

        _emit_progress(progress_callback, 0, total_bytes)
        conn = _connect(temp_path)
        fts_enabled = _has_fts5(conn)
        _create_schema(conn, fts_enabled)
        _write_metadata(conn, _expected_metadata(validated, fts_enabled))

        bytes_before_chunk = 0
        for chunk in chunks:
            chunk_progress = {}
            for pair, chunk_processed in _iter_chunk_pairs(
                chunks_dir / chunk["file"],
                chunk["sha256"],
                chunk_progress,
            ):
                processed_bytes = bytes_before_chunk + chunk_processed
                if pair is not None:
                    batch.append(pair)
                    if len(batch) >= BATCH_SIZE:
                        _insert_batch(conn, batch, fts_enabled)
                        inserted_pairs += len(batch)
                        batch.clear()
                if processed_bytes - last_reported_bytes >= PROGRESS_STEP_BYTES:
                    _emit_progress(progress_callback, processed_bytes, total_bytes)
                    last_reported_bytes = processed_bytes
            if chunk_progress.get("pair_count") != chunk["pair_count"]:
                raise SentenceSourceValidationError(
                    f"Sentence source chunk {chunk['file']} pair_count does not match parsed pairs."
                )
            bytes_before_chunk += chunk["size_bytes"]

        if batch:
            _insert_batch(conn, batch, fts_enabled)
            inserted_pairs += len(batch)
        if inserted_pairs != validated["total_pair_count"]:
            raise SentenceSourceValidationError(
                "Sentence source manifest total_pair_count does not match parsed pairs."
            )

        conn.commit()
        conn.close()
        conn = None
        try:
            os.replace(temp_path, cache_path)
        except OSError as error:
            _remove_temp_cache(temp_path)
            _raise_index_unavailable(error)
        _remember_valid_index(validated, cache_path)
        _emit_progress(progress_callback, total_bytes, total_bytes, force=True)
        return {
            "cache_path": str(cache_path),
            "source_dir": str(validated["paths"].root),
            "fts_enabled": fts_enabled,
        }
    except SOURCE_FAILURES as error:
        if getattr(error, "_mykamus_progress_callback", False):
            raise
        if conn is not None:
            conn.close()
        if temp_path is not None:
            _remove_temp_cache(temp_path)
        _raise_index_unavailable(error)
    except sqlite3.Error as error:
        if conn is not None:
            conn.close()
        if temp_path is not None:
            _remove_temp_cache(temp_path)
        _raise_index_unavailable(error)
    except Exception:
        if conn is not None:
            conn.close()
        if temp_path is not None:
            _remove_temp_cache(temp_path)
        raise


def is_index_valid(source_dir, cache_path):
    cache_path = Path(cache_path)
    if not cache_path.is_file():
        return False
    try:
        validated = validate_source_dataset(source_dir, verify_checksums=False)
        expected = _expected_metadata(validated)
        cache_key = _validation_cache_key(validated, cache_path, expected)
        if _VALIDATION_CACHE.get(cache_key):
            return True

        validated = validate_source_dataset(source_dir, verify_checksums=True)
        expected = _expected_metadata(validated)
        cache_key = _validation_cache_key(validated, cache_path, expected)
        conn = _connect(cache_path)
        try:
            actual = _read_metadata(conn)
            if not all(actual.get(key) == value for key, value in expected.items()):
                return False
            if actual.get("fts_enabled") not in {"0", "1"}:
                return False
            valid = _validate_cache_shape(conn, actual)
            if valid:
                _VALIDATION_CACHE[cache_key] = True
            return valid
        finally:
            conn.close()
    except (OSError, sqlite3.Error, SentenceSourceValidationError, UnicodeDecodeError):
        return False


def ensure_sentence_index(source_dir, cache_path, progress_callback=None):
    try:
        validated = validate_source_dataset(source_dir, verify_checksums=False)
    except SOURCE_FAILURES as error:
        _raise_index_unavailable(error)
    if is_index_valid(source_dir, cache_path):
        total_bytes = sum(chunk["size_bytes"] for chunk in validated["manifest"]["chunks"])
        _emit_progress(progress_callback, total_bytes, total_bytes, force=True)
        return {"cache_path": str(Path(cache_path)), "rebuilt": False}
    result = build_sentence_index(source_dir, cache_path, progress_callback, validated=validated)
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


def search_sentence_index(query, limit, source_dir, cache_path):
    if not query or not query.strip():
        return
    if not is_index_valid(source_dir, cache_path):
        raise IndexUnavailableError("Sentence index is missing or stale.")

    pattern = _build_phrase_pattern(query)
    emitted = set()
    emitted_count = 0
    try:
        conn = _connect(cache_path)
    except sqlite3.Error as error:
        raise IndexUnavailableError("Sentence index is missing or stale.") from error

    try:
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
        except sqlite3.Error as error:
            raise IndexUnavailableError("Sentence index is missing or stale.") from error
    finally:
        conn.close()
