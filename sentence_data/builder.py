import json
import os
import re
import shutil
import sqlite3
import tempfile
from pathlib import Path

from .layout import (
    MAX_SHARD_BYTES,
    SCHEMA_VERSION,
    TARGET_SHARD_BYTES,
    SentenceDataValidationError,
    resolve_dataset_paths,
    validate_dataset,
)


TOKEN_PATTERN = re.compile(r"\b\w+\b", re.IGNORECASE)


def _clean_line(line):
    return " ".join(line.strip().split())


def iter_sentence_pairs(source_path):
    pending_english = None
    with Path(source_path).open(encoding="utf-8", errors="replace") as source_file:
        for raw_line in source_file:
            cleaned = _clean_line(raw_line)
            if not cleaned:
                continue
            if pending_english is None:
                pending_english = cleaned
            else:
                yield pending_english, cleaned
                pending_english = None
    if pending_english is not None:
        raise SentenceDataValidationError("Sentence source has an unmatched trailing line.")


def _connect(path):
    return sqlite3.connect(str(path))


def _create_index_schema(conn):
    conn.executescript(
        """
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE sentence_lookup (
            sentence_id INTEGER PRIMARY KEY,
            shard_file TEXT NOT NULL
        );

        CREATE TABLE sentence_terms (
            term TEXT NOT NULL,
            sentence_id INTEGER NOT NULL
        );

        CREATE INDEX sentence_terms_term_idx
        ON sentence_terms(term, sentence_id);
        """
    )


def _create_shard_schema(conn):
    conn.execute(
        """
        CREATE TABLE sentence_pairs (
            id INTEGER PRIMARY KEY,
            english TEXT NOT NULL,
            indonesian TEXT NOT NULL
        )
        """
    )


def _tokenize(text):
    return sorted({token.casefold() for token in TOKEN_PATTERN.findall(text)})


def _database_size_bytes(path):
    db_path = Path(path)
    if not db_path.exists():
        return 0
    return db_path.stat().st_size


def _open_shard(paths, shard_number):
    shard_file = f"sentences_{shard_number:04d}.sqlite"
    shard_path = paths.shards_dir / shard_file
    shard_conn = _connect(shard_path)
    _create_shard_schema(shard_conn)
    return shard_file, shard_path, shard_conn


def _finalize_shard(shard_infos, shard_file, shard_path, first_sentence_id, last_sentence_id):
    size_bytes = _database_size_bytes(shard_path)
    if size_bytes > MAX_SHARD_BYTES:
        raise SentenceDataValidationError("Sentence shard exceeds the 80 MB size limit.")
    shard_infos.append(
        {
            "file": shard_file,
            "first_sentence_id": first_sentence_id,
            "last_sentence_id": last_sentence_id,
            "size_bytes": size_bytes,
        }
    )


def _build_dataset_in_place(source_path, paths, target_shard_bytes):
    paths.shards_dir.mkdir(parents=True, exist_ok=True)

    index_conn = _connect(paths.index)
    shard_conn = None
    manifest = None
    try:
        _create_index_schema(index_conn)
        index_conn.executemany(
            "INSERT INTO metadata(key, value) VALUES (?, ?)",
            [
                ("schema_version", SCHEMA_VERSION),
                ("source_path", str(source_path.resolve())),
                ("source_size", str(source_path.stat().st_size)),
                ("target_shard_bytes", str(int(target_shard_bytes))),
            ],
        )

        sentence_count = 0
        shard_number = 0
        shard_infos = []
        shard_file = None
        shard_path = None
        first_sentence_id = None

        for english, indonesian in iter_sentence_pairs(source_path):
            if shard_conn is None:
                shard_number += 1
                shard_file, shard_path, shard_conn = _open_shard(paths, shard_number)
                first_sentence_id = sentence_count + 1

            sentence_count += 1
            shard_conn.execute(
                "INSERT INTO sentence_pairs(id, english, indonesian) VALUES (?, ?, ?)",
                (sentence_count, english, indonesian),
            )
            index_conn.execute(
                "INSERT INTO sentence_lookup(sentence_id, shard_file) VALUES (?, ?)",
                (sentence_count, shard_file),
            )
            for term in sorted(set(_tokenize(english) + _tokenize(indonesian))):
                index_conn.execute(
                    "INSERT INTO sentence_terms(term, sentence_id) VALUES (?, ?)",
                    (term, sentence_count),
                )

            shard_conn.commit()
            if _database_size_bytes(shard_path) >= target_shard_bytes:
                _finalize_shard(
                    shard_infos,
                    shard_file,
                    shard_path,
                    first_sentence_id,
                    sentence_count,
                )
                shard_conn.close()
                shard_conn = None
                shard_file = None
                shard_path = None
                first_sentence_id = None

        if sentence_count == 0:
            raise SentenceDataValidationError("Sentence source file does not contain any sentence pairs.")

        if shard_conn is not None:
            shard_conn.commit()
            _finalize_shard(
                shard_infos,
                shard_file,
                shard_path,
                first_sentence_id,
                sentence_count,
            )
            shard_conn.close()
            shard_conn = None

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "index_file": paths.index.name,
            "shards": shard_infos,
        }
        paths.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        index_conn.commit()
    finally:
        if shard_conn is not None:
            shard_conn.close()
        index_conn.close()

    validate_dataset(paths.root)
    verification = verify_sentence_dataset(paths.root)
    return {
        "manifest": manifest,
        "sentence_count": verification["sentence_count"],
        "lookup_count": verification["lookup_count"],
    }


def _replace_dataset_dir(staging_root, destination_root):
    staging_root = Path(staging_root)
    destination_root = Path(destination_root)
    backup_root = destination_root.with_name(destination_root.name + ".bak")

    if backup_root.exists():
        shutil.rmtree(backup_root)

    if destination_root.exists():
        os.replace(destination_root, backup_root)
        try:
            os.replace(staging_root, destination_root)
        except Exception:
            os.replace(backup_root, destination_root)
            raise
        else:
            shutil.rmtree(backup_root)
    else:
        os.replace(staging_root, destination_root)


def build_sentence_dataset(source_path, dataset_dir, target_shard_bytes=TARGET_SHARD_BYTES):
    source_path = Path(source_path)
    if target_shard_bytes <= 0:
        raise SentenceDataValidationError("target_shard_bytes must be greater than zero.")

    paths = resolve_dataset_paths(dataset_dir)
    parent_dir = paths.root.parent
    parent_dir.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(prefix=paths.root.name + ".tmp-", dir=str(parent_dir))
    )
    try:
        staging_paths = resolve_dataset_paths(staging_root)
        result = _build_dataset_in_place(source_path, staging_paths, target_shard_bytes)
        _replace_dataset_dir(staging_root, paths.root)
        return result
    except Exception:
        if staging_root.exists():
            shutil.rmtree(staging_root)
        raise


def verify_sentence_dataset(dataset_dir):
    validated = validate_dataset(dataset_dir)
    paths = validated["paths"]
    manifest = validated["manifest"]

    index_conn = _connect(paths.index)
    try:
        lookup_rows = index_conn.execute(
            "SELECT sentence_id, shard_file FROM sentence_lookup ORDER BY sentence_id"
        ).fetchall()
        term_rows = index_conn.execute(
            "SELECT sentence_id, term FROM sentence_terms ORDER BY sentence_id, term"
        ).fetchall()
    except sqlite3.Error as error:
        raise SentenceDataValidationError(
            "Sentence dataset index is missing or inconsistent for sentence_terms."
        ) from error
    finally:
        index_conn.close()

    lookup_map = {sentence_id: shard_file for sentence_id, shard_file in lookup_rows}
    term_map = {}
    for sentence_id, term in term_rows:
        term_map.setdefault(sentence_id, []).append(term)

    sentence_count = 0
    shard_row_count = 0
    for shard in manifest["shards"]:
        shard_file = shard["file"]
        shard_conn = _connect(paths.shards_dir / shard_file)
        try:
            rows = shard_conn.execute(
                "SELECT id, english, indonesian FROM sentence_pairs ORDER BY id"
            ).fetchall()
        finally:
            shard_conn.close()

        sentence_ids = [row[0] for row in rows]
        if sentence_ids:
            expected_range = list(range(shard["first_sentence_id"], shard["last_sentence_id"] + 1))
            if sentence_ids != expected_range:
                raise SentenceDataValidationError(
                    f"Sentence shard {shard_file} contains unexpected sentence IDs."
                )
        shard_row_count += len(sentence_ids)
        for sentence_id, english, indonesian in rows:
            routed_shard_file = lookup_map.get(sentence_id)
            if routed_shard_file != shard_file:
                raise SentenceDataValidationError(
                    f"Sentence lookup for {sentence_id} does not match shard {shard_file}."
                )
            expected_terms = sorted(set(_tokenize(english) + _tokenize(indonesian)))
            actual_terms = term_map.get(sentence_id, [])
            if actual_terms != expected_terms:
                raise SentenceDataValidationError(
                    f"Sentence terms for {sentence_id} are missing or inconsistent."
                )
        sentence_count += len(sentence_ids)

    if sentence_count != len(lookup_rows):
        raise SentenceDataValidationError("Sentence lookup row count does not match shard row count.")
    if set(term_map) != set(lookup_map):
        raise SentenceDataValidationError("Sentence terms do not cover the same sentence IDs as the lookup index.")

    return {
        "sentence_count": sentence_count,
        "lookup_count": len(lookup_rows),
        "shard_count": len(manifest["shards"]),
        "shard_row_count": shard_row_count,
    }
