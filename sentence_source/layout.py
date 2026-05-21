from dataclasses import dataclass
import hashlib
import json
from pathlib import Path


SCHEMA_VERSION = "1"
SOURCE_FORMAT = "alternating-en-id-lines"
MAX_CHUNK_BYTES = 80 * 1024 * 1024
TARGET_CHUNK_BYTES = 72 * 1024 * 1024
DEFAULT_SENTENCE_SOURCE_DIR = Path("data") / "sentence_source"


class SentenceSourceError(RuntimeError):
    pass


class SentenceSourceValidationError(SentenceSourceError):
    pass


@dataclass(frozen=True)
class SentenceSourcePaths:
    root: Path
    manifest: Path
    chunks_dir: Path


def resolve_source_paths(source_dir):
    root = Path(source_dir)
    return SentenceSourcePaths(
        root=root,
        manifest=root / "manifest.json",
        chunks_dir=root / "chunks",
    )


def load_manifest(manifest_path):
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SentenceSourceValidationError(
            f"Sentence source dataset is missing {Path(manifest_path).name}."
        ) from error
    except json.JSONDecodeError as error:
        raise SentenceSourceValidationError(
            "Sentence source dataset manifest is not valid JSON."
        ) from error

    if not isinstance(manifest, dict):
        raise SentenceSourceValidationError(
            "Sentence source dataset manifest must be a JSON object."
        )

    return manifest


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_signature(manifest):
    manifest_bytes = json.dumps(
        manifest,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(manifest_bytes).hexdigest()


def _require_int(value, field_name, chunk_file=None):
    if not isinstance(value, int) or isinstance(value, bool):
        suffix = f" for {chunk_file}" if chunk_file else ""
        raise SentenceSourceValidationError(
            f"Sentence source manifest {field_name} must be an integer{suffix}."
        )
    return value


def _validate_chunk_file_name(chunk_file):
    if not isinstance(chunk_file, str) or not chunk_file:
        raise SentenceSourceValidationError(
            "Sentence source manifest chunk file must be a non-empty string."
        )
    if Path(chunk_file).name != chunk_file or chunk_file in {".", ".."}:
        raise SentenceSourceValidationError(
            f"Sentence source manifest chunk file must be a basename: {chunk_file}"
        )


def _validate_chunk_entry(chunk, chunks_dir, verify_checksums):
    if not isinstance(chunk, dict):
        raise SentenceSourceValidationError(
            "Sentence source manifest chunk entries must be objects."
        )

    try:
        chunk_file = chunk["file"]
    except KeyError as error:
        raise SentenceSourceValidationError(
            "Sentence source manifest chunk entry is missing a file name."
        ) from error

    _validate_chunk_file_name(chunk_file)

    chunk_path = chunks_dir / chunk_file
    if not chunk_path.is_file():
        raise SentenceSourceValidationError(f"Sentence source chunk is missing: {chunk_file}")

    declared_size = _require_int(chunk.get("size_bytes"), "size_bytes", chunk_file)
    if declared_size < 0:
        raise SentenceSourceValidationError(
            f"Sentence source manifest size_bytes must be non-negative for {chunk_file}."
        )

    actual_size = chunk_path.stat().st_size
    if actual_size > MAX_CHUNK_BYTES or declared_size > MAX_CHUNK_BYTES:
        raise SentenceSourceValidationError("Sentence source chunk exceeds the 80 MB size limit.")

    sha256 = chunk.get("sha256")
    if not isinstance(sha256, str) or len(sha256) != 64:
        raise SentenceSourceValidationError(
            f"Sentence source manifest sha256 must be 64 characters for {chunk_file}."
        )
    if verify_checksums and file_sha256(chunk_path) != sha256:
        raise SentenceSourceValidationError(
            f"Sentence source chunk checksum does not match manifest: {chunk_file}"
        )
    if actual_size != declared_size:
        raise SentenceSourceValidationError(
            f"Sentence source chunk size does not match manifest: {chunk_file}"
        )

    pair_count = _require_int(chunk.get("pair_count"), "pair_count", chunk_file)
    if pair_count < 0:
        raise SentenceSourceValidationError(
            f"Sentence source manifest pair_count must be non-negative for {chunk_file}."
        )

    return pair_count


def validate_source_dataset(source_dir, verify_checksums=False):
    paths = resolve_source_paths(source_dir)
    manifest = load_manifest(paths.manifest)

    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise SentenceSourceValidationError(
            f"Sentence source schema version must be {SCHEMA_VERSION}."
        )
    if manifest.get("source_format") != SOURCE_FORMAT:
        raise SentenceSourceValidationError(
            f"Sentence source format must be {SOURCE_FORMAT}."
        )
    if not paths.chunks_dir.is_dir():
        raise SentenceSourceValidationError("Sentence source chunks directory is missing.")

    chunks = manifest.get("chunks")
    if not isinstance(chunks, list):
        raise SentenceSourceValidationError("Sentence source manifest chunks must be a list.")
    if not chunks:
        raise SentenceSourceValidationError("Sentence source manifest does not list any chunks.")

    total_pair_count = 0
    for chunk in chunks:
        total_pair_count += _validate_chunk_entry(chunk, paths.chunks_dir, verify_checksums)

    declared_total_pair_count = _require_int(
        manifest.get("total_pair_count"),
        "total_pair_count",
    )
    if declared_total_pair_count != total_pair_count:
        raise SentenceSourceValidationError(
            "Sentence source manifest total_pair_count does not match chunks."
        )

    return {
        "paths": paths,
        "manifest": manifest,
        "total_pair_count": total_pair_count,
        "manifest_signature": manifest_signature(manifest),
    }
