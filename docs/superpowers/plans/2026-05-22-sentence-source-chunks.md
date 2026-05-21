# Sentence Source Chunks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single large sentence source file and the rejected checked-in SQLite runtime dataset with GitHub-friendly sentence source chunks that build a local `.mykamus_cache/search.sqlite` cache on first run.

**Architecture:** Git tracks `data/sentence_source/manifest.json` plus ordered text chunks under `data/sentence_source/chunks/`. Runtime validates that source layout and builds/reuses a local SQLite cache at `cache_path`; generated SQLite files are never committed. Maintainer tooling regenerates the source chunks from `en-id_sentences.txt`.

**Tech Stack:** Python standard library, SQLite/FTS5 when available, unittest, existing Tkinter GUI startup workers.

---

## Important Current Branch Context

This plan supersedes the earlier checked-in `data/sentences/*.sqlite` design. The current branch already contains old-design commits through Task 4. Implement this plan by replacing those old-design modules and tests, not by extending the rejected SQLite shard artifact approach.

There are uncommitted scratch edits in `sentence_data/builder.py` and `tests/test_sentence_data_builder.py` from the blocked build attempt. They belong to the rejected design. The first implementation task removes the old `sentence_data` package and its tests, which clears those scratch edits by replacing the design rather than preserving them.

Do not commit generated `.mykamus_cache/` files.

---

## Target File Structure

Create:

- `sentence_source/__init__.py`: package exports for source chunk validation and splitting.
- `sentence_source/layout.py`: constants, path resolution, manifest loading, fast validation, checksum verification, manifest signature helpers.
- `sentence_source/splitter.py`: maintainer-only source splitter and verifier.
- `scripts/split_sentence_source.py`: CLI wrapper for split and verify.
- `tests/test_sentence_source_layout.py`: layout validation tests.
- `tests/test_sentence_source_splitter.py`: splitter and verifier tests.

Modify:

- `search_index.py`: build/search local `.mykamus_cache/search.sqlite` from source chunks.
- `search_functions.py`: configure `sentence_source_dir` plus `cache_path`, preserve outward search result behavior.
- `config.example.json`: replace `sentences_path`/old search block with `sentence_source_dir` plus `cache_path`.
- `gui_app/preflight.py`: validate chunked source layout, not checked-in SQLite shards.
- `gui_app/core/backend.py`: keep `sentence_index` status key while building local cache from chunks.
- `tests/test_search_index.py`: local cache tests from chunks.
- `tests/test_search_functions.py`: integration tests from chunks and local cache.
- `tests/test_gui_preflight.py`: source chunk preflight tests.
- `tests/test_gui_core.py`: backend status tests if wording/status payloads change.
- `tests/test_gui_tk.py`: loading progress expectations if labels change.
- `README.md`: user and maintainer docs.

Delete:

- `sentence_data/__init__.py`
- `sentence_data/layout.py`
- `sentence_data/builder.py`
- `tests/test_sentence_data_layout.py`
- `tests/test_sentence_data_builder.py`
- `scripts/build_sentence_data.py`

Generated in final task:

- `data/sentence_source/manifest.json`
- `data/sentence_source/chunks/en-id_sentences_*.txt`

---

## Task 1: Source Chunk Layout Validation

**Files:**

- Create: `sentence_source/__init__.py`
- Create: `sentence_source/layout.py`
- Create: `tests/test_sentence_source_layout.py`
- Delete: `sentence_data/__init__.py`
- Delete: `sentence_data/layout.py`
- Delete: `tests/test_sentence_data_layout.py`

- [ ] **Step 1: Write the failing layout tests**

Create `tests/test_sentence_source_layout.py`:

```python
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from sentence_source import layout


class SentenceSourceLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "sentence_source"
        self.chunks_dir = self.root / "chunks"
        self.chunks_dir.mkdir(parents=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def write_chunk(self, name, text):
        path = self.chunks_dir / name
        path.write_text(text, encoding="utf-8")
        return path

    def write_manifest(self, chunks):
        manifest = {
            "schema_version": layout.SCHEMA_VERSION,
            "source_format": layout.SOURCE_FORMAT,
            "chunks": chunks,
            "total_pair_count": sum(chunk["pair_count"] for chunk in chunks),
        }
        (self.root / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n",
            encoding="utf-8",
        )
        return manifest

    def chunk_entry(self, path, pair_count=1):
        data = path.read_bytes()
        return {
            "file": path.name,
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "pair_count": pair_count,
        }

    def test_valid_source_dataset_loads_paths_and_manifest(self):
        chunk = self.write_chunk("en-id_sentences_0001.txt", "People.\nRakyat?\n")
        manifest = self.write_manifest([self.chunk_entry(chunk)])

        validated = layout.validate_source_dataset(self.root)

        self.assertEqual(self.root, validated["paths"].root)
        self.assertEqual(manifest["total_pair_count"], validated["manifest"]["total_pair_count"])
        self.assertEqual(1, validated["total_pair_count"])

    def test_missing_manifest_reports_manifest_json(self):
        with self.assertRaisesRegex(layout.SentenceSourceValidationError, "manifest.json"):
            layout.validate_source_dataset(self.root)

    def test_manifest_must_be_json_object(self):
        (self.root / "manifest.json").write_text("[]", encoding="utf-8")

        with self.assertRaisesRegex(layout.SentenceSourceValidationError, "JSON object"):
            layout.validate_source_dataset(self.root)

    def test_rejects_missing_chunk(self):
        self.write_manifest(
            [
                {
                    "file": "en-id_sentences_0001.txt",
                    "size_bytes": 10,
                    "sha256": "0" * 64,
                    "pair_count": 1,
                }
            ]
        )

        with self.assertRaisesRegex(layout.SentenceSourceValidationError, "missing"):
            layout.validate_source_dataset(self.root)

    def test_rejects_oversized_chunk_from_manifest_or_disk(self):
        chunk = self.write_chunk("en-id_sentences_0001.txt", "People.\nRakyat?\n")
        entry = self.chunk_entry(chunk)
        entry["size_bytes"] = layout.MAX_CHUNK_BYTES + 1
        self.write_manifest([entry])

        with self.assertRaisesRegex(layout.SentenceSourceValidationError, "80 MB"):
            layout.validate_source_dataset(self.root)

    def test_verify_checksums_rejects_changed_chunk(self):
        chunk = self.write_chunk("en-id_sentences_0001.txt", "People.\nRakyat?\n")
        self.write_manifest([self.chunk_entry(chunk)])
        chunk.write_text("Changed.\nBerubah.\n", encoding="utf-8")

        with self.assertRaisesRegex(layout.SentenceSourceValidationError, "checksum"):
            layout.validate_source_dataset(self.root, verify_checksums=True)

    def test_manifest_signature_changes_when_manifest_changes(self):
        chunk = self.write_chunk("en-id_sentences_0001.txt", "People.\nRakyat?\n")
        self.write_manifest([self.chunk_entry(chunk)])
        first = layout.manifest_signature(layout.validate_source_dataset(self.root)["manifest"])

        manifest = json.loads((self.root / "manifest.json").read_text(encoding="utf-8"))
        manifest["total_pair_count"] = 2
        (self.root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        second = layout.manifest_signature(layout.validate_source_dataset(self.root)["manifest"])

        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -B -m unittest discover -s tests -p test_sentence_source_layout.py -v
```

Expected: fails because `sentence_source.layout` does not exist.

- [ ] **Step 3: Remove old layout files and create the new package**

Run:

```powershell
git rm sentence_data\__init__.py sentence_data\layout.py tests\test_sentence_data_layout.py
```

Create `sentence_source/__init__.py`:

```python
"""Sentence source chunk helpers for myKamus."""
```

Create `sentence_source/layout.py`:

```python
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
            f"Sentence source is missing {Path(manifest_path).name}."
        ) from error
    except json.JSONDecodeError as error:
        raise SentenceSourceValidationError("Sentence source manifest is not valid JSON.") from error

    if not isinstance(manifest, dict):
        raise SentenceSourceValidationError("Sentence source manifest must be a JSON object.")
    return manifest


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as file:
        for block in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_signature(manifest):
    signature_manifest = {
        "schema_version": manifest.get("schema_version"),
        "source_format": manifest.get("source_format"),
        "total_pair_count": manifest.get("total_pair_count"),
        "chunks": [
            {
                "file": chunk.get("file"),
                "size_bytes": chunk.get("size_bytes"),
                "sha256": chunk.get("sha256"),
                "pair_count": chunk.get("pair_count"),
            }
            for chunk in manifest.get("chunks", [])
        ],
    }
    encoded = json.dumps(signature_manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _require_int(value, message):
    try:
        integer = int(value)
    except (TypeError, ValueError) as error:
        raise SentenceSourceValidationError(message) from error
    return integer


def _validate_chunk_entry(chunk, chunks_dir, verify_checksums):
    if not isinstance(chunk, dict):
        raise SentenceSourceValidationError("Sentence source manifest chunk entries must be objects.")

    chunk_file = chunk.get("file")
    if not isinstance(chunk_file, str) or not chunk_file:
        raise SentenceSourceValidationError("Sentence source manifest chunk file must be a non-empty string.")
    if Path(chunk_file).name != chunk_file:
        raise SentenceSourceValidationError("Sentence source manifest chunk file must not include directories.")

    chunk_path = chunks_dir / chunk_file
    if not chunk_path.is_file():
        raise SentenceSourceValidationError(f"Sentence source chunk is missing: {chunk_file}")

    actual_size = chunk_path.stat().st_size
    declared_size = _require_int(
        chunk.get("size_bytes"),
        f"Sentence source chunk size_bytes must be an integer for {chunk_file}.",
    )
    pair_count = _require_int(
        chunk.get("pair_count"),
        f"Sentence source chunk pair_count must be an integer for {chunk_file}.",
    )
    if pair_count < 0:
        raise SentenceSourceValidationError(f"Sentence source chunk pair_count must not be negative for {chunk_file}.")
    if actual_size > MAX_CHUNK_BYTES or declared_size > MAX_CHUNK_BYTES:
        raise SentenceSourceValidationError("Sentence source chunk exceeds the 80 MB size limit.")
    if actual_size != declared_size:
        raise SentenceSourceValidationError(f"Sentence source chunk size does not match manifest: {chunk_file}")

    sha256 = chunk.get("sha256")
    if not isinstance(sha256, str) or len(sha256) != 64:
        raise SentenceSourceValidationError(f"Sentence source chunk checksum is invalid for {chunk_file}.")
    if verify_checksums and file_sha256(chunk_path) != sha256:
        raise SentenceSourceValidationError(f"Sentence source chunk checksum does not match manifest: {chunk_file}")

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
    if not isinstance(chunks, list) or not chunks:
        raise SentenceSourceValidationError("Sentence source manifest chunks must be a non-empty list.")

    total_pair_count = 0
    for chunk in chunks:
        total_pair_count += _validate_chunk_entry(chunk, paths.chunks_dir, verify_checksums)

    declared_total = _require_int(
        manifest.get("total_pair_count"),
        "Sentence source manifest total_pair_count must be an integer.",
    )
    if declared_total != total_pair_count:
        raise SentenceSourceValidationError("Sentence source manifest pair counts do not add up.")

    return {
        "paths": paths,
        "manifest": manifest,
        "total_pair_count": total_pair_count,
        "manifest_signature": manifest_signature(manifest),
    }
```

- [ ] **Step 4: Run layout tests and commit**

Run:

```powershell
python -B -m unittest discover -s tests -p test_sentence_source_layout.py -v
```

Expected: all tests pass.

Commit:

```powershell
git add sentence_source tests/test_sentence_source_layout.py
git commit -m "feat: validate chunked sentence source layout"
```

---

## Task 2: Maintainer Splitter And Verification CLI

**Files:**

- Create: `sentence_source/splitter.py`
- Create: `scripts/split_sentence_source.py`
- Create: `tests/test_sentence_source_splitter.py`
- Delete: `sentence_data/builder.py`
- Delete: `tests/test_sentence_data_builder.py`
- Delete: `scripts/build_sentence_data.py`

- [ ] **Step 1: Write the failing splitter tests**

Create `tests/test_sentence_source_splitter.py`:

```python
import json
from pathlib import Path
import tempfile
import unittest

from sentence_source import layout, splitter


class SentenceSourceSplitterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.source_path = self.temp_path / "en-id_sentences.txt"
        self.output_dir = self.temp_path / "sentence_source"

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_splitter_preserves_pair_boundaries_across_chunks(self):
        self.source_path.write_text(
            "People.\n"
            "Rakyat?\n\n"
            "That brat.\n"
            "Bocah itu.\n\n"
            "Many people know.\n"
            "Banyak orang tahu.\n",
            encoding="utf-8",
        )

        result = splitter.split_sentence_source(
            self.source_path,
            self.output_dir,
            target_chunk_bytes=32,
        )

        manifest = layout.validate_source_dataset(self.output_dir, verify_checksums=True)["manifest"]
        self.assertEqual(3, manifest["total_pair_count"])
        self.assertGreaterEqual(len(manifest["chunks"]), 2)
        for chunk in manifest["chunks"]:
            lines = [
                line
                for line in (self.output_dir / "chunks" / chunk["file"]).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(0, len(lines) % 2)
        self.assertEqual(3, result["total_pair_count"])

    def test_splitter_rejects_unmatched_trailing_line(self):
        self.source_path.write_text("People.\n", encoding="utf-8")

        with self.assertRaisesRegex(layout.SentenceSourceValidationError, "unmatched trailing line"):
            splitter.split_sentence_source(self.source_path, self.output_dir)

    def test_splitter_rejects_pair_larger_than_limit(self):
        self.source_path.write_text("English sentence.\nKalimat Indonesia.\n", encoding="utf-8")

        with self.assertRaisesRegex(layout.SentenceSourceValidationError, "larger than the chunk size limit"):
            splitter.split_sentence_source(
                self.source_path,
                self.output_dir,
                target_chunk_bytes=10,
                max_chunk_bytes=20,
            )

    def test_splitter_output_is_deterministic(self):
        self.source_path.write_text(
            "People.\nRakyat?\nThat brat.\nBocah itu.\n",
            encoding="utf-8",
        )
        first_dir = self.temp_path / "first"
        second_dir = self.temp_path / "second"

        splitter.split_sentence_source(self.source_path, first_dir, target_chunk_bytes=40)
        splitter.split_sentence_source(self.source_path, second_dir, target_chunk_bytes=40)

        first_manifest = json.loads((first_dir / "manifest.json").read_text(encoding="utf-8"))
        second_manifest = json.loads((second_dir / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(first_manifest, second_manifest)

    def test_verify_sentence_source_returns_counts(self):
        self.source_path.write_text("People.\nRakyat?\n", encoding="utf-8")
        splitter.split_sentence_source(self.source_path, self.output_dir)

        result = splitter.verify_sentence_source(self.output_dir)

        self.assertEqual(1, result["total_pair_count"])
        self.assertEqual(1, result["chunk_count"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -B -m unittest discover -s tests -p test_sentence_source_splitter.py -v
```

Expected: fails because `sentence_source.splitter` does not exist.

- [ ] **Step 3: Remove old builder files**

Run:

```powershell
git rm sentence_data\builder.py tests\test_sentence_data_builder.py scripts\build_sentence_data.py
```

- [ ] **Step 4: Implement splitter**

Create `sentence_source/splitter.py`:

```python
import json
import os
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
    resolve_source_paths,
    validate_source_dataset,
)


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
        raise SentenceSourceValidationError("Sentence source has an unmatched trailing line.")


def _pair_bytes(english, indonesian):
    return (english + "\n" + indonesian + "\n").encode("utf-8")


def _write_chunk(chunks_dir, chunk_number, chunk_pairs):
    chunk_file = f"en-id_sentences_{chunk_number:04d}.txt"
    chunk_path = chunks_dir / chunk_file
    with chunk_path.open("w", encoding="utf-8", newline="\n") as chunk:
        for english, indonesian in chunk_pairs:
            chunk.write(english + "\n")
            chunk.write(indonesian + "\n")
    size_bytes = chunk_path.stat().st_size
    if size_bytes > MAX_CHUNK_BYTES:
        raise SentenceSourceValidationError("Sentence source chunk exceeds the 80 MB size limit.")
    return {
        "file": chunk_file,
        "size_bytes": size_bytes,
        "sha256": file_sha256(chunk_path),
        "pair_count": len(chunk_pairs),
    }


def _replace_source_dir(staging_root, destination_root):
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


def _split_in_place(source_path, paths, target_chunk_bytes, max_chunk_bytes):
    paths.chunks_dir.mkdir(parents=True, exist_ok=True)
    chunks = []
    current_pairs = []
    current_size = 0
    total_pairs = 0
    chunk_number = 0

    for english, indonesian in iter_sentence_pairs(source_path):
        pair_data = _pair_bytes(english, indonesian)
        if len(pair_data) > max_chunk_bytes:
            raise SentenceSourceValidationError("A sentence pair is larger than the chunk size limit.")
        if current_pairs and current_size + len(pair_data) > target_chunk_bytes:
            chunk_number += 1
            chunks.append(_write_chunk(paths.chunks_dir, chunk_number, current_pairs))
            current_pairs = []
            current_size = 0
        current_pairs.append((english, indonesian))
        current_size += len(pair_data)
        total_pairs += 1

    if not current_pairs:
        raise SentenceSourceValidationError("Sentence source file does not contain any sentence pairs.")

    chunk_number += 1
    chunks.append(_write_chunk(paths.chunks_dir, chunk_number, current_pairs))

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source_format": SOURCE_FORMAT,
        "chunks": chunks,
        "total_pair_count": total_pairs,
    }
    paths.manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    validate_source_dataset(paths.root, verify_checksums=True)
    return {"total_pair_count": total_pairs, "chunk_count": len(chunks)}


def split_sentence_source(
    source_path,
    output_dir,
    target_chunk_bytes=TARGET_CHUNK_BYTES,
    max_chunk_bytes=MAX_CHUNK_BYTES,
):
    if target_chunk_bytes <= 0:
        raise SentenceSourceValidationError("target_chunk_bytes must be greater than zero.")
    if target_chunk_bytes > max_chunk_bytes:
        raise SentenceSourceValidationError("target_chunk_bytes must not exceed max_chunk_bytes.")

    output_paths = resolve_source_paths(output_dir)
    output_paths.root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = Path(
        tempfile.mkdtemp(prefix=output_paths.root.name + ".tmp-", dir=str(output_paths.root.parent))
    )
    try:
        result = _split_in_place(
            Path(source_path),
            resolve_source_paths(staging_root),
            target_chunk_bytes,
            max_chunk_bytes,
        )
        _replace_source_dir(staging_root, output_paths.root)
        return result
    except Exception:
        if staging_root.exists():
            shutil.rmtree(staging_root)
        raise


def verify_sentence_source(source_dir):
    validated = validate_source_dataset(source_dir, verify_checksums=True)
    return {
        "total_pair_count": validated["total_pair_count"],
        "chunk_count": len(validated["manifest"]["chunks"]),
    }
```

- [ ] **Step 5: Implement CLI**

Create `scripts/split_sentence_source.py`:

```python
import argparse
import sys

from sentence_source.splitter import split_sentence_source, verify_sentence_source


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Build or verify chunked myKamus sentence source files.")
    parser.add_argument("--source", help="Path to maintainer-only en-id_sentences.txt input.")
    parser.add_argument("--output", required=True, help="Output sentence source directory.")
    parser.add_argument("--verify", action="store_true", help="Verify an existing chunked sentence source directory.")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    if args.verify:
        result = verify_sentence_source(args.output)
        print(
            "Verified {total_pair_count} sentence pairs across {chunk_count} chunks.".format(**result)
        )
        return 0
    if not args.source:
        print("--source is required unless --verify is used.", file=sys.stderr)
        return 2
    result = split_sentence_source(args.source, args.output)
    print(
        "Built {total_pair_count} sentence pairs into {chunk_count} chunks.".format(**result)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run splitter tests and commit**

Run:

```powershell
python -B -m unittest discover -s tests -p test_sentence_source_splitter.py -v
python -m py_compile sentence_source\layout.py sentence_source\splitter.py scripts\split_sentence_source.py
```

Expected: tests pass and `py_compile` exits successfully.

Commit:

```powershell
git add sentence_source scripts tests
git commit -m "feat: split sentence source into github-sized chunks"
```

---

## Task 3: Local Cache Runtime From Source Chunks

**Files:**

- Modify: `search_index.py`
- Modify: `tests/test_search_index.py`

- [ ] **Step 1: Replace search index tests with chunk-source cache behavior**

Rewrite `tests/test_search_index.py` around `sentence_source.splitter.split_sentence_source` and a local cache path. The tests must include these cases:

```python
def test_ensure_sentence_index_builds_local_cache_from_chunks(self):
    progress = []

    result = search_index.ensure_sentence_index(
        self.source_dir,
        self.cache_path,
        progress_callback=progress.append,
    )

    self.assertTrue(self.cache_path.is_file())
    self.assertTrue(result["rebuilt"])
    self.assertEqual(100.0, progress[-1]["percent"])
```

```python
def test_index_valid_after_build_and_reused_without_rebuild(self):
    search_index.ensure_sentence_index(self.source_dir, self.cache_path)

    self.assertTrue(search_index.is_index_valid(self.source_dir, self.cache_path))
    with mock.patch("search_index.build_sentence_index") as build:
        result = search_index.ensure_sentence_index(self.source_dir, self.cache_path)

    build.assert_not_called()
    self.assertFalse(result["rebuilt"])
```

```python
def test_search_is_bidirectional_after_source_file_removed(self):
    search_index.ensure_sentence_index(self.source_dir, self.cache_path)
    self.source_path.unlink()

    english_result = list(search_index.search_sentence_index("people", 1, self.source_dir, self.cache_path))
    indonesian_result = list(search_index.search_sentence_index("rakyat", 1, self.source_dir, self.cache_path))

    self.assertEqual("People.", english_result[0]["match"])
    self.assertEqual("Rakyat?", english_result[0]["translation"])
    self.assertEqual("Rakyat?", indonesian_result[0]["match"])
    self.assertEqual("People.", indonesian_result[0]["translation"])
```

```python
def test_cache_rebuilds_when_manifest_signature_changes(self):
    search_index.ensure_sentence_index(self.source_dir, self.cache_path)
    self.source_path.write_text("New people.\nRakyat baru.\n", encoding="utf-8")
    splitter.split_sentence_source(self.source_path, self.source_dir)

    self.assertFalse(search_index.is_index_valid(self.source_dir, self.cache_path))
    result = search_index.ensure_sentence_index(self.source_dir, self.cache_path)

    self.assertTrue(result["rebuilt"])
    matches = list(search_index.search_sentence_index("new people", 1, self.source_dir, self.cache_path))
    self.assertEqual("New people.", matches[0]["match"])
```

```python
def test_failed_rebuild_keeps_existing_cache(self):
    search_index.ensure_sentence_index(self.source_dir, self.cache_path)
    self.source_path.write_text("New people.\nRakyat baru.\n", encoding="utf-8")
    splitter.split_sentence_source(self.source_path, self.source_dir)

    with mock.patch("search_index._insert_batch", side_effect=RuntimeError("boom")):
        with self.assertRaises(RuntimeError):
            search_index.ensure_sentence_index(self.source_dir, self.cache_path)

    self.assertTrue(self.cache_path.is_file())
```

```python
def test_missing_source_chunks_raise_index_unavailable(self):
    for path in (self.source_dir / "chunks").glob("*.txt"):
        path.unlink()

    with self.assertRaises(search_index.IndexUnavailableError):
        list(search_index.search_sentence_index("people", 1, self.source_dir, self.cache_path))
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -B -m unittest discover -s tests -p test_search_index.py -v
```

Expected: tests fail because `search_index.py` still expects `data/sentences` SQLite runtime artifacts.

- [ ] **Step 3: Replace `search_index.py` with local cache implementation**

Implement `search_index.py` as a cache builder/search module with these exact public signatures:

- `is_index_valid(source_dir, cache_path)`
- `ensure_sentence_index(source_dir, cache_path, progress_callback=None)`
- `search_sentence_index(query, limit, source_dir, cache_path)`

Use the old master-branch cache schema shape:

```sql
CREATE TABLE metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE sentence_pairs (
    id INTEGER PRIMARY KEY,
    english TEXT NOT NULL,
    indonesian TEXT NOT NULL
);
```

If FTS5 is available, also create:

```sql
CREATE VIRTUAL TABLE sentence_pairs_fts USING fts5(english, indonesian);
```

Cache metadata must include:

```python
{
    "schema_version": SCHEMA_VERSION,
    "source_schema_version": sentence_source.layout.SCHEMA_VERSION,
    "source_manifest_signature": validated["manifest_signature"],
    "source_pair_count": str(validated["total_pair_count"]),
    "fts_enabled": "1" or "0",
}
```

Build behavior:

- call `validate_source_dataset(source_dir, verify_checksums=False)` before checking cache validity
- when rebuilding, read chunks in manifest order
- while reading chunks, parse alternating non-empty lines into sentence pairs
- insert in batches of 5000
- validate checksums while reading chunks by comparing SHA-256 against the manifest entry
- build into `cache_path.with_name(cache_path.name + ".tmp")`
- replace old cache only after commit succeeds
- delete the temp file on failure
- keep the old cache if rebuild fails

Search behavior:

- call `is_index_valid(source_dir, cache_path)` and raise `IndexUnavailableError("Sentence index is missing or stale.")` if false
- use FTS query when metadata says FTS is enabled
- otherwise use `LIKE` fallback
- apply phrase-boundary regex after candidate selection
- preserve result dictionaries with keys `match`, `translation`, `matched_language`, `english`, `indonesian`

Progress payload:

```python
{
    "title": "Building sentence cache...",
    "processed_bytes": processed_bytes,
    "total_bytes": total_bytes,
    "percent": percent,
    "complete": complete,
}
```

- [ ] **Step 4: Run cache tests and commit**

Run:

```powershell
python -B -m unittest discover -s tests -p test_search_index.py -v
```

Expected: all tests pass.

Commit:

```powershell
git add search_index.py tests/test_search_index.py
git commit -m "feat: build local sentence cache from source chunks"
```

---

## Task 4: Search Functions, GUI Backend, And Preflight Integration

**Files:**

- Modify: `search_functions.py`
- Modify: `config.example.json`
- Modify: `gui_app/preflight.py`
- Modify: `gui_app/core/backend.py`
- Modify: `tests/test_search_functions.py`
- Modify: `tests/test_gui_preflight.py`
- Modify: `tests/test_gui_core.py`
- Modify: `tests/test_gui_tk.py`

- [ ] **Step 1: Update tests for the corrected runtime story**

In `tests/test_search_functions.py`, replace use of `sentence_data.builder.build_sentence_dataset` with `sentence_source.splitter.split_sentence_source`.

Config fixtures should use:

```python
{
    "dictionary_path": str(dictionary_path),
    "sentence_source_dir": str(self.source_dir),
    "cache_path": str(self.cache_path),
    "red_book_enabled": False,
    "sentence_limit": 4,
}
```

Add or update tests to prove:

```python
def test_sentence_search_builds_cache_from_chunks_without_raw_source_file(self):
    self.sentences_path.unlink()

    result = sf.search_for_word_data("people", sentence_limit=1)

    self.assertTrue(self.cache_path.exists())
    self.assertEqual("People.", result["sentences"][0]["match"])
```

```python
def test_missing_sentence_source_returns_user_facing_result_message(self):
    for path in self.source_dir.rglob("*"):
        if path.is_file():
            path.unlink()

    result = sf.search_for_word_data("people")

    self.assertEqual([], result["sentences"])
    self.assertEqual("Example sentences are unavailable right now.", result["sentence_message"])
```

In `tests/test_gui_preflight.py`, replace sentence dataset wording with source chunk wording:

```python
def test_sentence_source_errors_reports_missing_manifest(self):
    with tempfile.TemporaryDirectory() as temp_dir:
        errors = preflight.sentence_source_errors(Path(temp_dir))

    self.assertTrue(any("manifest.json" in message for message in errors))
```

```python
def test_ensure_data_files_reports_sentence_source_errors_without_git_lfs_pull(self):
    messages = []
    with mock.patch.object(preflight, "missing_data_files", return_value=[]), \
            mock.patch.object(preflight, "sentence_source_errors", return_value=["Sentence source is missing manifest.json."]), \
            mock.patch.object(preflight, "command_exists") as command_exists, \
            mock.patch.object(preflight, "run_command") as run_command:
        result = preflight.ensure_data_files(output_func=messages.append)

    self.assertFalse(result)
    command_exists.assert_not_called()
    run_command.assert_not_called()
    self.assertTrue(any("data/sentence_source" in message for message in messages))
```

In `tests/test_gui_core.py`, keep the `sentence_index` result key:

```python
self.assertEqual(
    {
        "sentence_index": {"cache_path": "cache.sqlite", "rebuilt": True},
        "red_book_index": {"rebuilt": False},
    },
    result,
)
```

- [ ] **Step 2: Run focused tests and verify failure**

Run:

```powershell
python -B -m unittest discover -s tests -p test_search_functions.py -v
python -B -m unittest discover -s tests -p test_gui_preflight.py -v
python -B -m unittest discover -s tests -p test_gui_core.py -v
python -B -m unittest discover -s tests -p test_gui_tk.py -v
```

Expected: failures until runtime and preflight are updated.

- [ ] **Step 3: Update configuration and search facade**

In `config.example.json`, use:

```json
{
  "dictionary_path": "en-id_dict.txt",
  "sentence_source_dir": "data/sentence_source",
  "cache_path": ".mykamus_cache/search.sqlite",
  "red_book_pdf_path": "indonesiandictionary.pdf",
  "red_book_cache_path": ".mykamus_cache/red_book.sqlite",
  "red_book_results_limit": 3,
  "red_book_enabled": true,
  "sentence_limit": 4,
  "gui": {
    "always_on_top": true,
    "compact_mode": false,
    "window_size": "900x700",
    "window_position": "+100+100",
    "load_all_sentence_limit": 200,
    "search_status_delay_ms": 200
  },
  "hotkeys": {
    "manual_search": "ctrl+s",
    "load_all_sentences": "l"
  },
  "poll_interval": 0.1
}
```

In `search_functions.py`:

- set `CONFIG_DEFAULTS["sentence_source_dir"] = "data/sentence_source"`
- set `CONFIG_DEFAULTS["cache_path"] = ".mykamus_cache/search.sqlite"`
- remove `sentence_data_dir()`
- add:

```python
def sentence_source_dir():
    overrides = _load_config_overrides()
    if "sentence_source_dir" not in overrides and "sentences_path" in overrides:
        legacy_path = Path(overrides["sentences_path"])
        if not legacy_path.is_absolute():
            legacy_path = BASE_DIR / legacy_path
        return legacy_path.parent / "data" / "sentence_source"
    return data_path("sentence_source_dir")


def cache_path():
    return data_path("cache_path")
```

- update:

```python
def is_sentence_index_valid():
    return search_index.is_index_valid(sentence_source_dir(), cache_path())


def ensure_sentence_index(progress_callback=None):
    return search_index.ensure_sentence_index(
        sentence_source_dir(),
        cache_path(),
        progress_callback=progress_callback,
    )


def iter_matching_indexed_sentence_pairs(query, limit):
    yield from search_index.search_sentence_index(
        query,
        limit,
        sentence_source_dir(),
        cache_path(),
    )
```

- keep the existing `IndexUnavailableError` handling in `search_for_word_data()` and `load_all_sentences()`.

- [ ] **Step 4: Update preflight**

In `gui_app/preflight.py`:

- import `DEFAULT_SENTENCE_SOURCE_DIR`, `SentenceSourceValidationError`, and `validate_source_dataset` from `sentence_source.layout`
- replace `sentence_dataset_errors()` with:

```python
def sentence_source_errors(base_dir=BASE_DIR):
    source_dir = Path(base_dir) / DEFAULT_SENTENCE_SOURCE_DIR
    try:
        validate_source_dataset(source_dir, verify_checksums=False)
    except SentenceSourceValidationError as error:
        return [str(error)]
    return []
```

- update `ensure_data_files()` to call `sentence_source_errors()`
- replace user text:

```text
myKamus needs the included sentence source chunks before it can start:
Restore the data/sentence_source folder from the repository.
```

- keep Git LFS flow for `en-id_dict.txt` and `indonesiandictionary.pdf` only.

- [ ] **Step 5: Update GUI backend and loading expectations**

Keep `GuiBackend.build_indexes()` ordering:

```python
sentence_status = self._ensure_sentence_index(progress_callback=progress_callback)
red_book_status = self._ensure_red_book_index(progress_callback=progress_callback)
return {
    "sentence_index": sentence_status,
    "red_book_index": red_book_status,
}
```

If `tests/test_gui_tk.py` checks progress labels, update sentence cache progress payload expectations to:

```python
{
    "title": "Building sentence cache...",
    "percent": 100.0,
    "complete": True,
}
```

- [ ] **Step 6: Run focused tests and commit**

Run:

```powershell
python -B -m unittest discover -s tests -p test_search_functions.py -v
python -B -m unittest discover -s tests -p test_gui_preflight.py -v
python -B -m unittest discover -s tests -p test_gui_core.py -v
python -B -m unittest discover -s tests -p test_gui_tk.py -v
```

Expected: all pass. Tk tests may emit the existing harmless `ttk::ThemeChanged` teardown noise.

Commit:

```powershell
git add search_functions.py config.example.json gui_app tests
git commit -m "feat: use source chunks for local sentence cache"
```

---

## Task 5: Generate GitHub-Friendly Sentence Source Chunks And Update Docs

**Files:**

- Generate: `data/sentence_source/manifest.json`
- Generate: `data/sentence_source/chunks/en-id_sentences_*.txt`
- Modify: `README.md`

- [ ] **Step 1: Generate the real chunked source dataset**

Run:

```powershell
python scripts/split_sentence_source.py --source en-id_sentences.txt --output data/sentence_source
```

Expected output:

```text
Built <count> sentence pairs into <count> chunks.
```

- [ ] **Step 2: Verify chunks and file sizes**

Run:

```powershell
python scripts/split_sentence_source.py --verify --output data/sentence_source
Get-ChildItem data\sentence_source -Recurse -File | Select-Object Name,@{Name='SizeMB';Expression={[math]::Round($_.Length/1MB,2)}} | Sort-Object SizeMB -Descending
```

Expected:

- verify command prints `Verified <count> sentence pairs across <count> chunks.`
- every chunk file is below 80 MB
- `manifest.json` is small

If any generated file under `data/sentence_source` exceeds 80 MB, stop and report BLOCKED.

- [ ] **Step 3: Update README**

Edit README so the runtime sentence data section includes:

```markdown
## Runtime sentence data

myKamus includes GitHub-friendly sentence source chunks under:

~~~text
data/
  sentence_source/
    manifest.json
    chunks/
      en-id_sentences_0001.txt
      en-id_sentences_0002.txt
~~~

The first launch builds a local SQLite sentence cache at:

~~~text
.mykamus_cache/search.sqlite
~~~

That cache is generated on the user's computer and is not committed to Git.
Later launches reuse it unless the sentence source manifest changes.

`en-id_sentences.txt` is no longer required for normal use. It is a maintainer-only input used to regenerate the chunked source files.

Maintainers can rebuild the chunked source files with:

~~~bash
python scripts/split_sentence_source.py --source en-id_sentences.txt --output data/sentence_source
~~~

Developers can verify the checked-in chunks with:

~~~bash
python scripts/split_sentence_source.py --verify --output data/sentence_source
~~~
```

Also remove or rewrite README text that says:

- Git LFS is needed for the sentence corpus
- `en-id_sentences.txt` is a normal runtime requirement
- `.mykamus_cache/search.sqlite` is bundled or committed
- first launch builds from one giant sentence file

- [ ] **Step 4: Run full verification**

Run:

```powershell
python -B -m unittest discover -s tests
python -m py_compile sentence_source\layout.py sentence_source\splitter.py scripts\split_sentence_source.py search_index.py search_functions.py gui_app\preflight.py gui_app\core\backend.py
git diff --check
```

Expected:

- unittest suite passes
- `py_compile` exits successfully
- `git diff --check` prints nothing

- [ ] **Step 5: Commit generated chunks and docs**

Run:

```powershell
git add data/sentence_source README.md
git commit -m "feat: check in chunked sentence source"
```

---

## Task 6: Final Cleanup, Review, And Branch Finish

**Files:**

- Inspect all touched files.

- [ ] **Step 1: Check for old design references**

Run:

```powershell
rg "data/sentences|sentence_data|build_sentence_data|sentence_index.sqlite|checked-in sharded sentence dataset|en-id_sentences.txt is.*runtime|Git LFS.*sentence" .
```

Expected:

- no runtime code imports `sentence_data`
- no docs present `data/sentences/*.sqlite` as current runtime design
- `en-id_sentences.txt` appears only as maintainer-only source input text or legacy config compatibility text
- Git LFS is not described as required for the sentence corpus

- [ ] **Step 2: Verify git status and generated file sizes**

Run:

```powershell
git status --short --branch
Get-ChildItem data\sentence_source -Recurse -File | Where-Object { $_.Length -gt 80MB }
```

Expected:

- branch has no uncommitted changes
- second command prints no files

- [ ] **Step 3: Final code review**

Dispatch a final read-only code-review subagent with:

```text
Review the corrected chunked sentence source implementation from the base before this plan to HEAD.
Focus on:
- no committed generated SQLite files
- no runtime dependency on en-id_sentences.txt
- cache rebuild safety
- source chunk validation and checksums
- first-run progress
- GitHub file-size constraint
- docs accuracy
```

Expected: reviewer approves or provides findings. Fix any findings with focused commits and re-review until approved.

- [ ] **Step 4: Finish branch**

Use `superpowers:finishing-a-development-branch`.

Expected options:

- push branch for PR
- provide commit summary
- keep worktree for later follow-up

---

## Self-Review Checklist

- Spec coverage: The plan implements repo-tracked source chunks, local first-run SQLite cache generation, no committed sentence SQLite runtime artifacts, preflight validation, maintainer splitter tooling, docs, tests, and generated chunk files under 80 MB.
- Placeholder scan: The plan has concrete paths, commands, expected outputs, function names, and test cases.
- Type consistency: Runtime APIs use `source_dir` plus `cache_path`; config uses `sentence_source_dir`; generated source layout uses `data/sentence_source`.
- Scope control: This plan addresses the sentence corpus only. Dictionary and Red Book large-file distribution remain separate follow-up topics.
