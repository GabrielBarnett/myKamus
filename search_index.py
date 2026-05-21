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


def _connect(path):
    return sqlite3.connect(str(path))


def is_dataset_valid(dataset_dir):
    try:
        validate_dataset(dataset_dir)
        return True
    except SentenceDataValidationError:
        return False


def ensure_sentence_dataset(dataset_dir, progress_callback=None):
    try:
        validated = validate_dataset(dataset_dir)
    except SentenceDataValidationError as error:
        raise IndexUnavailableError(str(error)) from error

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
    try:
        validated = validate_dataset(dataset_dir)
    except SentenceDataValidationError as error:
        raise IndexUnavailableError(str(error)) from error

    paths = validated["paths"]
    pattern = _build_phrase_pattern(query)
    emitted = set()
    emitted_count = 0

    index_conn = _connect(paths.index)
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
    finally:
        index_conn.close()

    grouped = defaultdict(list)
    for sentence_id, shard_file in rows:
        grouped[shard_file].append(sentence_id)

    for shard_file, sentence_ids in grouped.items():
        shard_conn = _connect(paths.shards_dir / shard_file)
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
        finally:
            shard_conn.close()
