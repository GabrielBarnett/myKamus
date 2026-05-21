"""
Dataset-backed sentence-pair search for myKamus.
"""

from collections import defaultdict
import re
import sqlite3

from sentence_data.layout import SentenceDataValidationError, validate_dataset


class IndexUnavailableError(RuntimeError):
    pass


TOKEN_PATTERN = re.compile(r"\b\w+\b", re.IGNORECASE)
_VALIDATION_CACHE = {}


def _connect(path):
    return sqlite3.connect(str(path))


def _translate_sqlite_error(error):
    raise IndexUnavailableError("Sentence dataset is unavailable.") from error


def _connect_or_raise(path):
    try:
        return _connect(path)
    except sqlite3.Error as error:
        _translate_sqlite_error(error)


def _query_scalar(path, query):
    conn = _connect_or_raise(path)
    try:
        try:
            row = conn.execute(query).fetchone()
        except sqlite3.Error as error:
            _translate_sqlite_error(error)
        return None if row is None else row[0]
    finally:
        conn.close()


def _tokenize_text(text):
    return sorted({token.casefold() for token in TOKEN_PATTERN.findall(text)})


def _collect_terms_by_sentence(index_conn, first_sentence_id, last_sentence_id):
    rows = index_conn.execute(
        """
        SELECT sentence_id, term
        FROM sentence_terms
        WHERE sentence_id BETWEEN ? AND ?
        ORDER BY sentence_id, term
        """,
        (first_sentence_id, last_sentence_id),
    ).fetchall()
    terms_by_sentence = {}
    for sentence_id, term in rows:
        terms_by_sentence.setdefault(sentence_id, []).append(term)
    return terms_by_sentence


def _file_signature(path):
    try:
        stat = path.stat()
    except OSError as error:
        raise IndexUnavailableError("Sentence dataset is unavailable.") from error
    return (str(path), stat.st_size, stat.st_mtime_ns)


def _dataset_cache_key(validated):
    return str(validated["paths"].root.resolve())


def _dataset_signature(validated):
    try:
        paths = validated["paths"]
        shard_signatures = tuple(
            _file_signature(paths.shards_dir / shard["file"])
            for shard in validated["manifest"]["shards"]
        )
    except (KeyError, TypeError, ValueError) as error:
        raise IndexUnavailableError("Sentence dataset is unavailable.") from error
    return (
        _file_signature(paths.manifest),
        _file_signature(paths.index),
        shard_signatures,
    )


def _validate_runtime_dataset_fresh(validated):
    paths = validated["paths"]
    index_conn = _connect_or_raise(paths.index)
    try:
        lookup_count = index_conn.execute(
            "SELECT COUNT(*) FROM sentence_lookup"
        ).fetchone()[0]
        term_sentence_count = index_conn.execute(
            "SELECT COUNT(DISTINCT sentence_id) FROM sentence_terms"
        ).fetchone()[0]
        if not lookup_count or term_sentence_count != lookup_count:
            raise IndexUnavailableError("Sentence dataset is unavailable.")

        shard_row_count = 0
        for shard in validated["manifest"]["shards"]:
            shard_path = paths.shards_dir / shard["file"]
            row_count = _query_scalar(
                shard_path,
                "SELECT COUNT(*) FROM sentence_pairs",
            )
            if not row_count:
                raise IndexUnavailableError("Sentence dataset is unavailable.")
            shard_row_count += row_count

            expected_count = shard["last_sentence_id"] - shard["first_sentence_id"] + 1
            lookup_stats = index_conn.execute(
                """
                SELECT COUNT(*), MIN(sentence_id), MAX(sentence_id)
                FROM sentence_lookup
                WHERE shard_file = ?
                """,
                (shard["file"],),
            ).fetchone()
            if lookup_stats is None:
                raise IndexUnavailableError("Sentence dataset is unavailable.")
            lookup_count_for_shard, min_sentence_id, max_sentence_id = lookup_stats
            if (
                lookup_count_for_shard != expected_count
                or min_sentence_id != shard["first_sentence_id"]
                or max_sentence_id != shard["last_sentence_id"]
            ):
                raise IndexUnavailableError("Sentence dataset is unavailable.")

            terms_by_sentence = _collect_terms_by_sentence(
                index_conn,
                shard["first_sentence_id"],
                shard["last_sentence_id"],
            )
            shard_conn = _connect_or_raise(shard_path)
            try:
                shard_rows = shard_conn.execute(
                    """
                    SELECT id, english, indonesian
                    FROM sentence_pairs
                    WHERE id BETWEEN ? AND ?
                    ORDER BY id
                    """,
                    (shard["first_sentence_id"], shard["last_sentence_id"]),
                ).fetchall()
            finally:
                shard_conn.close()

            sentence_ids = {row[0] for row in shard_rows}
            if sentence_ids != set(terms_by_sentence):
                raise IndexUnavailableError("Sentence dataset is unavailable.")

            for sentence_id, english, indonesian in shard_rows:
                expected_terms = sorted(
                    set(_tokenize_text(english) + _tokenize_text(indonesian))
                )
                if terms_by_sentence.get(sentence_id, []) != expected_terms:
                    raise IndexUnavailableError("Sentence dataset is unavailable.")

        if shard_row_count != lookup_count:
            raise IndexUnavailableError("Sentence dataset is unavailable.")
    except sqlite3.Error as error:
        _translate_sqlite_error(error)
    finally:
        index_conn.close()


def _validate_runtime_dataset(dataset_dir):
    cache_key = None
    try:
        validated = validate_dataset(dataset_dir)
        cache_key = _dataset_cache_key(validated)
        signature = _dataset_signature(validated)
        cached_signature = _VALIDATION_CACHE.get(cache_key)
        if cached_signature == signature:
            return validated

        _validate_runtime_dataset_fresh(validated)
        _VALIDATION_CACHE[cache_key] = signature
        return validated
    except SentenceDataValidationError as error:
        if cache_key is not None:
            _VALIDATION_CACHE.pop(cache_key, None)
        raise IndexUnavailableError(str(error)) from error
    except (UnicodeDecodeError, KeyError, TypeError, ValueError) as error:
        if cache_key is not None:
            _VALIDATION_CACHE.pop(cache_key, None)
        raise IndexUnavailableError("Sentence dataset is unavailable.") from error
    except IndexUnavailableError:
        if cache_key is not None:
            _VALIDATION_CACHE.pop(cache_key, None)
        raise


def is_dataset_valid(dataset_dir):
    try:
        _validate_runtime_dataset(dataset_dir)
        return True
    except IndexUnavailableError:
        return False


def ensure_sentence_dataset(dataset_dir, progress_callback=None):
    validated = _validate_runtime_dataset(dataset_dir)

    if progress_callback is not None:
        progress_callback(
            {
                "title": "Validating sentence dataset...",
                "percent": 100.0,
                "complete": True,
            }
        )
    return {
        "dataset_dir": str(validated["paths"].root),
        "rebuilt": False,
        "validated": True,
    }


def _build_phrase_pattern(query):
    return re.compile(rf"(?<!\w){re.escape(query)}(?!\w)", re.IGNORECASE)


def _tokenize_query(query):
    return sorted({token.casefold() for token in TOKEN_PATTERN.findall(query)})


def _candidate_ids(index_conn, query):
    tokens = _tokenize_query(query)
    if not tokens:
        return []

    placeholders = ",".join("?" for _ in tokens)
    rows = index_conn.execute(
        f"""
        SELECT sentence_id
        FROM sentence_terms
        WHERE term IN ({placeholders})
        GROUP BY sentence_id
        HAVING COUNT(DISTINCT term) = ?
        ORDER BY sentence_id
        """,
        [*tokens, len(tokens)],
    ).fetchall()
    return [row[0] for row in rows]


def search_sentence_index(query, limit, dataset_dir):
    validated = _validate_runtime_dataset(dataset_dir)

    paths = validated["paths"]
    pattern = _build_phrase_pattern(query)
    emitted = set()
    emitted_count = 0

    index_conn = _connect_or_raise(paths.index)
    try:
        try:
            ids = _candidate_ids(index_conn, query)
            if not ids:
                return

            placeholders = ",".join("?" for _ in ids)
            rows = index_conn.execute(
                f"""
                SELECT sentence_id, shard_file
                FROM sentence_lookup
                WHERE sentence_id IN ({placeholders})
                ORDER BY sentence_id
                """,
                ids,
            ).fetchall()
        except sqlite3.Error as error:
            _translate_sqlite_error(error)
    finally:
        index_conn.close()

    grouped = defaultdict(list)
    for sentence_id, shard_file in rows:
        grouped[shard_file].append(sentence_id)

    for shard_file, sentence_ids in grouped.items():
        shard_conn = _connect_or_raise(paths.shards_dir / shard_file)
        try:
            try:
                placeholders = ",".join("?" for _ in sentence_ids)
                for sentence_id, english, indonesian in shard_conn.execute(
                    f"""
                    SELECT id, english, indonesian
                    FROM sentence_pairs
                    WHERE id IN ({placeholders})
                    ORDER BY id
                    """,
                    sentence_ids,
                ):
                    english_matches = bool(pattern.search(english))
                    indonesian_matches = bool(pattern.search(indonesian))
                    if not english_matches and not indonesian_matches:
                        continue

                    pair_key = (english, indonesian)
                    if pair_key in emitted:
                        continue
                    if limit is not None and emitted_count >= limit:
                        return

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
                _translate_sqlite_error(error)
        finally:
            shard_conn.close()
