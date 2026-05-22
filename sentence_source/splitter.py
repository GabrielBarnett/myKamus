import json
import shutil
import tempfile
from pathlib import Path

from .layout import (
    MAX_CHUNK_BYTES,
    SCHEMA_VERSION,
    SOURCE_FORMAT,
    TARGET_CHUNK_BYTES,
    SentenceSourceValidationError,
    file_sha256,
    validate_source_dataset,
)


def _clean_line(line):
    return " ".join(line.strip().split())


def _pair_bytes(english, indonesian):
    return f"{english}\n{indonesian}\n".encode("utf-8")


def iter_sentence_pairs(source_path):
    pending_english = None
    with Path(source_path).open(encoding="utf-8", errors="replace") as source_file:
        for raw_line in source_file:
            cleaned = _clean_line(raw_line)
            if not cleaned:
                continue
            if pending_english is None:
                pending_english = cleaned
                continue
            yield pending_english, cleaned
            pending_english = None

    if pending_english is not None:
        raise SentenceSourceValidationError(
            "Sentence source has an unmatched trailing line."
        )


def _validate_chunk_sizes(target_chunk_bytes, max_chunk_bytes):
    if target_chunk_bytes <= 0:
        raise SentenceSourceValidationError(
            "Sentence source target chunk size must be positive."
        )
    if max_chunk_bytes <= 0:
        raise SentenceSourceValidationError(
            "Sentence source maximum chunk size must be positive."
        )
    if target_chunk_bytes > max_chunk_bytes:
        raise SentenceSourceValidationError(
            "Sentence source target chunk size must not exceed the maximum chunk size."
        )


def _write_chunk(chunks_dir, chunk_index, chunk_parts, pair_count):
    chunk_file = f"en-id_sentences_{chunk_index:04d}.txt"
    chunk_path = chunks_dir / chunk_file
    chunk_path.write_bytes(b"".join(chunk_parts))
    return {
        "file": chunk_file,
        "size_bytes": chunk_path.stat().st_size,
        "sha256": file_sha256(chunk_path),
        "pair_count": pair_count,
    }


def _write_manifest(root, chunks):
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source_format": SOURCE_FORMAT,
        "chunks": chunks,
        "total_pair_count": sum(chunk["pair_count"] for chunk in chunks),
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def _move_directory(source, destination):
    Path(source).replace(destination)


def _unique_backup_path(output_dir):
    backup_dir = Path(tempfile.mkdtemp(
        prefix=f".{output_dir.name}.",
        suffix=".bak",
        dir=output_dir.parent,
    ))
    backup_dir.rmdir()
    return backup_dir


def _replace_output_dir(staging_root, output_dir):
    output_dir = Path(output_dir)
    backup_dir = None
    success = False
    # Windows stdlib cannot atomically replace populated directories, so this
    # uses a best-effort swap with rollback to preserve the previous output.
    if output_dir.exists():
        backup_dir = _unique_backup_path(output_dir)
        _move_directory(output_dir, backup_dir)

    try:
        _move_directory(staging_root, output_dir)
        success = True
    except Exception:
        if backup_dir is not None and backup_dir.exists() and not output_dir.exists():
            _move_directory(backup_dir, output_dir)
        raise
    finally:
        if success and backup_dir is not None and backup_dir.exists():
            shutil.rmtree(backup_dir)


def split_sentence_source(
    source_path,
    output_dir,
    target_chunk_bytes=TARGET_CHUNK_BYTES,
    max_chunk_bytes=MAX_CHUNK_BYTES,
):
    _validate_chunk_sizes(target_chunk_bytes, max_chunk_bytes)

    output_dir = Path(output_dir)
    parent_dir = output_dir.parent
    parent_dir.mkdir(parents=True, exist_ok=True)
    staging_parent = Path(tempfile.mkdtemp(
        prefix=f".{output_dir.name}.",
        suffix=".tmp",
        dir=parent_dir,
    ))
    staging_root = staging_parent / output_dir.name
    chunks_dir = staging_root / "chunks"
    chunks_dir.mkdir(parents=True)

    chunks = []
    chunk_parts = []
    chunk_size = 0
    chunk_pair_count = 0
    chunk_index = 1

    try:
        for english, indonesian in iter_sentence_pairs(source_path):
            pair_data = _pair_bytes(english, indonesian)
            pair_size = len(pair_data)
            if pair_size > max_chunk_bytes:
                raise SentenceSourceValidationError(
                    "A sentence pair is larger than the chunk size limit."
                )
            if chunk_parts and chunk_size + pair_size > target_chunk_bytes:
                chunks.append(
                    _write_chunk(chunks_dir, chunk_index, chunk_parts, chunk_pair_count)
                )
                chunk_index += 1
                chunk_parts = []
                chunk_size = 0
                chunk_pair_count = 0

            if chunk_size + pair_size > max_chunk_bytes:
                chunks.append(
                    _write_chunk(chunks_dir, chunk_index, chunk_parts, chunk_pair_count)
                )
                chunk_index += 1
                chunk_parts = []
                chunk_size = 0
                chunk_pair_count = 0

            chunk_parts.append(pair_data)
            chunk_size += pair_size
            chunk_pair_count += 1

        if chunk_parts:
            chunks.append(_write_chunk(chunks_dir, chunk_index, chunk_parts, chunk_pair_count))
        if not chunks:
            raise SentenceSourceValidationError(
                "Sentence source does not contain any sentence pairs."
            )

        _write_manifest(staging_root, chunks)
        validated = validate_source_dataset(staging_root, verify_checksums=True)
        _replace_output_dir(staging_root, output_dir)

        return {
            "total_pair_count": validated["total_pair_count"],
            "chunk_count": len(validated["manifest"]["chunks"]),
        }
    except Exception:
        shutil.rmtree(staging_parent, ignore_errors=True)
        raise
    finally:
        if staging_parent.exists():
            shutil.rmtree(staging_parent, ignore_errors=True)


def verify_sentence_source(source_dir):
    validated = validate_source_dataset(source_dir, verify_checksums=True)
    return {
        "total_pair_count": validated["total_pair_count"],
        "chunk_count": len(validated["manifest"]["chunks"]),
    }
