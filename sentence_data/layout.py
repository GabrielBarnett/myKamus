from dataclasses import dataclass
import json
from pathlib import Path


SCHEMA_VERSION = "1"
MAX_SHARD_BYTES = 80 * 1024 * 1024
TARGET_SHARD_BYTES = 72 * 1024 * 1024
DEFAULT_SENTENCE_DATA_DIR = Path("data") / "sentences"


class SentenceDataError(RuntimeError):
    pass


class SentenceDataValidationError(SentenceDataError):
    pass


@dataclass(frozen=True)
class SentenceDatasetPaths:
    root: Path
    manifest: Path
    index: Path
    shards_dir: Path


def resolve_dataset_paths(dataset_dir):
    root = Path(dataset_dir)
    return SentenceDatasetPaths(
        root=root,
        manifest=root / "manifest.json",
        index=root / "sentence_index.sqlite",
        shards_dir=root / "shards",
    )


def load_manifest(manifest_path):
    try:
        return json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SentenceDataValidationError(
            f"Sentence dataset is missing {Path(manifest_path).name}."
        ) from error
    except json.JSONDecodeError as error:
        raise SentenceDataValidationError("Sentence dataset manifest is not valid JSON.") from error


def _validate_shard_entry(shard, shards_dir):
    if not isinstance(shard, dict):
        raise SentenceDataValidationError("Sentence dataset manifest shard entries must be objects.")

    try:
        shard_file = shard["file"]
    except KeyError as error:
        raise SentenceDataValidationError(
            "Sentence dataset manifest shard entry is missing a file name."
        ) from error

    if not isinstance(shard_file, str) or not shard_file:
        raise SentenceDataValidationError("Sentence dataset manifest shard file must be a non-empty string.")

    shard_path = shards_dir / shard_file
    if not shard_path.is_file():
        raise SentenceDataValidationError(f"Sentence shard is missing: {shard_file}")

    actual_size = shard_path.stat().st_size
    try:
        declared_size = int(shard.get("size_bytes", actual_size))
    except (TypeError, ValueError) as error:
        raise SentenceDataValidationError(
            f"Sentence dataset manifest shard size_bytes must be an integer for {shard_file}."
        ) from error

    if actual_size > MAX_SHARD_BYTES or declared_size > MAX_SHARD_BYTES:
        raise SentenceDataValidationError("Sentence shard exceeds the 80 MB size limit.")


def validate_dataset(dataset_dir):
    paths = resolve_dataset_paths(dataset_dir)
    manifest = load_manifest(paths.manifest)
    if not isinstance(manifest, dict):
        raise SentenceDataValidationError("Sentence dataset manifest must be a JSON object.")
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise SentenceDataValidationError(
            f"Sentence dataset schema version must be {SCHEMA_VERSION}."
        )
    if not paths.index.is_file():
        raise SentenceDataValidationError("Sentence dataset index file is missing.")
    if not paths.shards_dir.is_dir():
        raise SentenceDataValidationError("Sentence dataset shards directory is missing.")

    shards = manifest.get("shards")
    if not isinstance(shards, list):
        raise SentenceDataValidationError("Sentence dataset manifest shards must be a list.")
    if not shards:
        raise SentenceDataValidationError("Sentence dataset manifest does not list any shards.")

    for shard in shards:
        _validate_shard_entry(shard, paths.shards_dir)

    return {"paths": paths, "manifest": manifest}
