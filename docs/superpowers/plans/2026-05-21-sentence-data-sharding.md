# Sentence Data Sharding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the runtime dependency on `en-id_sentences.txt` with a repo-tracked sharded SQLite sentence dataset, builder tooling, startup validation, and updated search/runtime behavior.

**Architecture:** Introduce a dedicated `sentence_data/` package for dataset layout validation, deterministic shard building, and runtime lookup. Keep `search_index.py` as the sentence-search entry point, but repoint it to the new dataset instead of a cache built from the raw text file. Update `search_functions.py`, GUI startup/preflight, and docs so the application treats `data/sentences/` as the canonical runtime sentence source.

**Tech Stack:** Python standard library (`sqlite3`, `json`, `pathlib`, `re`, `argparse`, `tempfile`, `unittest`, `unittest.mock`), existing repository modules (`search_functions.py`, `search_index.py`, `gui_app/preflight.py`, `gui_app/core/backend.py`), Markdown docs.

---

## File Structure

- Create `sentence_data/__init__.py`
  - Package marker plus shared exports for sentence-data errors and helpers.
- Create `sentence_data/layout.py`
  - Runtime dataset paths, schema/version constants, manifest loading, and validation helpers.
- Create `sentence_data/builder.py`
  - Deterministic corpus-to-shards builder plus dataset verification helpers.
- Create `scripts/build_sentence_data.py`
  - Maintainer CLI for build and verify operations.
- Modify `search_index.py`
  - Replace cache-building logic with sharded-dataset validation and search routing.
- Modify `search_functions.py`
  - Switch config defaults and sentence search helpers to `data/sentences/`; remove raw text runtime scanning.
- Modify `gui_app/core/backend.py`
  - Treat sentence data as a validated runtime artifact and only build the Red Book index at startup.
- Modify `gui_app/preflight.py`
  - Validate `data/sentences/` instead of requiring `en-id_sentences.txt`.
- Modify `README.md`
  - Document the sharded sentence layout, builder command, verification command, and new runtime expectations.
- Create `tests/test_sentence_data_layout.py`
  - Unit tests for manifest/path validation and shard size enforcement.
- Create `tests/test_sentence_data_builder.py`
  - Builder/verification tests for deterministic shards and manifest/index correctness.
- Modify `tests/test_search_index.py`
  - Runtime search tests against the sharded dataset instead of the legacy cache file.
- Modify `tests/test_search_functions.py`
  - Search helpers use `sentence_data_dir` and no longer rely on `sentences_path` / `cache_path`.
- Modify `tests/test_cli.py`
  - CLI end-to-end tests build a sharded dataset fixture before invoking `cli.py`.
- Modify `tests/test_gui_preflight.py`
  - Preflight tests validate the sentence dataset and stop treating `en-id_sentences.txt` as a runtime requirement.
- Modify `tests/test_gui_core.py`
  - Backend tests verify startup readiness and build behavior with sentence data validation.
- Modify `tests/test_gui_tk.py`
  - Loading-view progress text and startup behavior reflect â€œsentence data must already exist; only Red Book is buildable.â€
- Generate `data/sentences/manifest.json`
  - Checked-in runtime manifest built from the legacy corpus.
- Generate `data/sentences/sentence_index.sqlite`
  - Checked-in routing index built from the legacy corpus.
- Generate `data/sentences/shards/sentences_*.sqlite`
  - Checked-in shard set; every shard must remain under 80 MB.

Do not change dictionary lookup semantics, Red Book extraction logic, or the Windows launcher entry points.

---

### Task 1: Add Sentence Dataset Layout Validation

**Files:**
- Create: `sentence_data/__init__.py`
- Create: `sentence_data/layout.py`
- Create: `tests/test_sentence_data_layout.py`

- [ ] **Step 1: Write the failing layout-validation tests**

Create `tests/test_sentence_data_layout.py` with:

```python
import json
import tempfile
import unittest
from pathlib import Path

from sentence_data import layout


class SentenceDataLayoutTests(unittest.TestCase):
    def test_resolve_dataset_paths_uses_expected_file_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = layout.resolve_dataset_paths(Path(temp_dir) / "data" / "sentences")

        self.assertEqual("manifest.json", paths.manifest.name)
        self.assertEqual("sentence_index.sqlite", paths.index.name)
        self.assertEqual("shards", paths.shards_dir.name)

    def test_validate_dataset_rejects_missing_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset_dir = Path(temp_dir) / "data" / "sentences"
            dataset_dir.mkdir(parents=True)

            with self.assertRaises(layout.SentenceDataValidationError) as error:
                layout.validate_dataset(dataset_dir)

        self.assertIn("manifest.json", str(error.exception))

    def test_validate_dataset_rejects_oversized_shard(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dataset_dir = Path(temp_dir) / "data" / "sentences"
            shards_dir = dataset_dir / "shards"
            shards_dir.mkdir(parents=True)
            manifest_path = dataset_dir / "manifest.json"
            (dataset_dir / "sentence_index.sqlite").write_bytes(b"index")
            large_shard = shards_dir / "sentences_0001.sqlite"
            large_shard.write_bytes(b"0")
            manifest_path.write_text(
                json.dumps(
                    {
                        "schema_version": layout.SCHEMA_VERSION,
                        "index_file": "sentence_index.sqlite",
                        "shards": [
                            {
                                "file": "sentences_0001.sqlite",
                                "first_sentence_id": 1,
                                "last_sentence_id": 1,
                                "size_bytes": layout.MAX_SHARD_BYTES + 1,
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(layout.SentenceDataValidationError) as error:
                layout.validate_dataset(dataset_dir)

        self.assertIn("80 MB", str(error.exception))
```

- [ ] **Step 2: Run the layout tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_sentence_data_layout.py
```

Expected: `ModuleNotFoundError: No module named 'sentence_data'`.

- [ ] **Step 3: Implement `sentence_data/layout.py`**

Create `sentence_data/__init__.py`:

```python
"""Sentence dataset helpers for the sharded myKamus runtime format."""

from .layout import (
    DEFAULT_SENTENCE_DATA_DIR,
    MAX_SHARD_BYTES,
    SCHEMA_VERSION,
    SentenceDataError,
    SentenceDataValidationError,
    resolve_dataset_paths,
    validate_dataset,
)
```

Create `sentence_data/layout.py`:

```python
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
        raise SentenceDataValidationError(f"Sentence dataset is missing {Path(manifest_path).name}.") from error
    except json.JSONDecodeError as error:
        raise SentenceDataValidationError("Sentence dataset manifest is not valid JSON.") from error


def validate_dataset(dataset_dir):
    paths = resolve_dataset_paths(dataset_dir)
    manifest = load_manifest(paths.manifest)
    if manifest.get("schema_version") != SCHEMA_VERSION:
        raise SentenceDataValidationError(
            f"Sentence dataset schema version must be {SCHEMA_VERSION}."
        )
    if not paths.index.is_file():
        raise SentenceDataValidationError("Sentence dataset index file is missing.")
    if not paths.shards_dir.is_dir():
        raise SentenceDataValidationError("Sentence dataset shards directory is missing.")

    shards = manifest.get("shards") or []
    if not shards:
        raise SentenceDataValidationError("Sentence dataset manifest does not list any shards.")

    for shard in shards:
        shard_path = paths.shards_dir / shard["file"]
        if not shard_path.is_file():
            raise SentenceDataValidationError(f"Sentence shard is missing: {shard['file']}")
        actual_size = shard_path.stat().st_size
        if actual_size > MAX_SHARD_BYTES or int(shard.get("size_bytes", actual_size)) > MAX_SHARD_BYTES:
            raise SentenceDataValidationError("Sentence shard exceeds the 80 MB size limit.")

    return {"paths": paths, "manifest": manifest}
```

- [ ] **Step 4: Run the layout tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_sentence_data_layout.py
```

Expected: `OK`.

- [ ] **Step 5: Commit the layout work**

Run:

```bash
git add sentence_data/__init__.py sentence_data/layout.py tests/test_sentence_data_layout.py
git commit -m "feat: add sentence dataset layout validation"
```

---

### Task 2: Build And Verify The Sharded Sentence Dataset

**Files:**
- Create: `sentence_data/builder.py`
- Create: `scripts/build_sentence_data.py`
- Create: `tests/test_sentence_data_builder.py`

- [ ] **Step 1: Write the failing builder tests**

Create `tests/test_sentence_data_builder.py` with:

```python
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sentence_data import builder, layout


class SentenceDataBuilderTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.source_path = self.temp_path / "sentences.txt"
        self.dataset_dir = self.temp_path / "data" / "sentences"
        self.source_path.write_text(
            "People.\n"
            "Rakyat?\n\n"
            "That brat.\n"
            "Bocah itu.\n\n"
            "Many people know.\n"
            "Banyak orang tahu.\n",
            encoding="utf-8",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_build_sentence_dataset_writes_manifest_index_and_shards(self):
        result = builder.build_sentence_dataset(
            self.source_path,
            self.dataset_dir,
            target_shard_bytes=300,
        )

        self.assertEqual(layout.SCHEMA_VERSION, result["manifest"]["schema_version"])
        self.assertTrue((self.dataset_dir / "manifest.json").is_file())
        self.assertTrue((self.dataset_dir / "sentence_index.sqlite").is_file())
        self.assertGreaterEqual(len(result["manifest"]["shards"]), 2)

    def test_verify_sentence_dataset_confirms_index_rows_have_shard_rows(self):
        builder.build_sentence_dataset(self.source_path, self.dataset_dir, target_shard_bytes=300)

        verification = builder.verify_sentence_dataset(self.dataset_dir)

        self.assertEqual(3, verification["sentence_count"])
        self.assertEqual(verification["sentence_count"], verification["lookup_count"])

    def test_builder_assigns_deterministic_sentence_ids(self):
        first = builder.build_sentence_dataset(self.source_path, self.dataset_dir, target_shard_bytes=300)
        second_dir = self.temp_path / "second" / "data" / "sentences"
        second = builder.build_sentence_dataset(self.source_path, second_dir, target_shard_bytes=300)

        self.assertEqual(first["manifest"]["shards"], second["manifest"]["shards"])
        self.assertEqual(first["sentence_count"], second["sentence_count"])
```

- [ ] **Step 2: Run the builder tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_sentence_data_builder.py
```

Expected: `ImportError` for `sentence_data.builder`.

- [ ] **Step 3: Implement the builder and CLI**

Create `sentence_data/builder.py`:

```python
import json
import re
import shutil
import sqlite3
from pathlib import Path

from .layout import (
    MAX_SHARD_BYTES,
    SCHEMA_VERSION,
    TARGET_SHARD_BYTES,
    SentenceDataValidationError,
    load_manifest,
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
        CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE sentence_lookup (
            sentence_id INTEGER PRIMARY KEY,
            shard_file TEXT NOT NULL
        );
        CREATE TABLE sentence_terms (
            term TEXT NOT NULL,
            sentence_id INTEGER NOT NULL
        );
        CREATE INDEX sentence_terms_term_idx ON sentence_terms(term, sentence_id);
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
    if not Path(path).exists():
        return 0
    return Path(path).stat().st_size


def build_sentence_dataset(source_path, dataset_dir, target_shard_bytes=TARGET_SHARD_BYTES):
    source_path = Path(source_path)
    paths = resolve_dataset_paths(dataset_dir)
    if paths.root.exists():
        shutil.rmtree(paths.root)
    paths.shards_dir.mkdir(parents=True, exist_ok=True)

    index_conn = _connect(paths.index)
    _create_index_schema(index_conn)
    index_conn.executemany(
        "INSERT INTO metadata(key, value) VALUES (?, ?)",
        [
            ("schema_version", SCHEMA_VERSION),
            ("source_path", str(source_path.resolve())),
            ("source_size", str(source_path.stat().st_size)),
        ],
    )

    sentence_id = 0
    shard_number = 1
    shard_infos = []
    shard_path = None
    shard_conn = None
    first_sentence_id = None

    def open_shard(number):
        file_name = f"sentences_{number:04d}.sqlite"
        path = paths.shards_dir / file_name
        conn = _connect(path)
        _create_shard_schema(conn)
        return file_name, path, conn

    try:
        shard_file, shard_path, shard_conn = open_shard(shard_number)
        for english, indonesian in iter_sentence_pairs(source_path):
            sentence_id += 1
            if first_sentence_id is None:
                first_sentence_id = sentence_id
            shard_conn.execute(
                "INSERT INTO sentence_pairs(id, english, indonesian) VALUES (?, ?, ?)",
                (sentence_id, english, indonesian),
            )
            for term in sorted(set(_tokenize(english) + _tokenize(indonesian))):
                index_conn.execute(
                    "INSERT INTO sentence_terms(term, sentence_id) VALUES (?, ?)",
                    (term, sentence_id),
                )
            index_conn.execute(
                "INSERT INTO sentence_lookup(sentence_id, shard_file) VALUES (?, ?)",
                (sentence_id, shard_file),
            )
            shard_conn.commit()
            if _database_size_bytes(shard_path) >= target_shard_bytes:
                shard_infos.append(
                    {
                        "file": shard_file,
                        "first_sentence_id": first_sentence_id,
                        "last_sentence_id": sentence_id,
                        "size_bytes": _database_size_bytes(shard_path),
                    }
                )
                if shard_infos[-1]["size_bytes"] > MAX_SHARD_BYTES:
                    raise SentenceDataValidationError("Sentence shard exceeds the 80 MB size limit.")
                shard_conn.close()
                shard_number += 1
                shard_file, shard_path, shard_conn = open_shard(shard_number)
                first_sentence_id = None
        if sentence_id == 0:
            raise SentenceDataValidationError("Sentence source file does not contain any sentence pairs.")
        shard_conn.commit()
        shard_infos.append(
            {
                "file": shard_file,
                "first_sentence_id": first_sentence_id,
                "last_sentence_id": sentence_id,
                "size_bytes": _database_size_bytes(shard_path),
            }
        )
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


def verify_sentence_dataset(dataset_dir):
    validated = validate_dataset(dataset_dir)
    paths = validated["paths"]
    manifest = validated["manifest"]
    index_conn = _connect(paths.index)
    try:
        lookup_rows = index_conn.execute(
            "SELECT sentence_id, shard_file FROM sentence_lookup ORDER BY sentence_id"
        ).fetchall()
    finally:
        index_conn.close()

    sentence_count = 0
    for shard in manifest["shards"]:
        shard_conn = _connect(paths.shards_dir / shard["file"])
        try:
            sentence_count += shard_conn.execute("SELECT COUNT(*) FROM sentence_pairs").fetchone()[0]
        finally:
            shard_conn.close()

    return {
        "sentence_count": sentence_count,
        "lookup_count": len(lookup_rows),
        "shard_count": len(manifest["shards"]),
    }
```

Create `scripts/build_sentence_data.py`:

```python
import argparse
from pathlib import Path

from sentence_data import builder, layout


def parse_args():
    parser = argparse.ArgumentParser(description="Build or verify the sharded myKamus sentence dataset.")
    parser.add_argument("--source", help="Path to the legacy sentence corpus text file.")
    parser.add_argument(
        "--output",
        default=str(layout.DEFAULT_SENTENCE_DATA_DIR),
        help="Output directory for the sentence dataset.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Validate an existing sentence dataset instead of rebuilding it.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.verify:
        result = builder.verify_sentence_dataset(Path(args.output))
        print(f"Verified {result['sentence_count']} sentence pairs across {result['shard_count']} shards.")
        return
    if not args.source:
        raise SystemExit("--source is required unless --verify is used.")
    result = builder.build_sentence_dataset(Path(args.source), Path(args.output))
    print(
        f"Built {result['sentence_count']} sentence pairs into {len(result['manifest']['shards'])} shards."
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the builder tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_sentence_data_builder.py
```

Expected: `OK`.

- [ ] **Step 5: Commit the builder and CLI**

Run:

```bash
git add sentence_data/builder.py scripts/build_sentence_data.py tests/test_sentence_data_builder.py
git commit -m "feat: add sharded sentence dataset builder"
```

---

### Task 3: Switch Runtime Search To The Sharded Dataset

**Files:**
- Modify: `search_index.py`
- Modify: `search_functions.py`
- Modify: `tests/test_search_index.py`
- Modify: `tests/test_search_functions.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Write the failing runtime-search tests**

Update `tests/test_search_index.py` to build a dataset in `setUp()` and search it:

```python
from pathlib import Path
import tempfile
import unittest

from sentence_data import builder
import search_index


class SearchIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.source_path = self.temp_path / "sentences.txt"
        self.dataset_dir = self.temp_path / "data" / "sentences"
        self.source_path.write_text(
            "People.\n"
            "Rakyat?\n\n"
            "That brat.\n"
            "Bocah itu.\n\n"
            "Many people know.\n"
            "Banyak orang tahu.\n",
            encoding="utf-8",
        )
        builder.build_sentence_dataset(self.source_path, self.dataset_dir, target_shard_bytes=300)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_dataset_validates_successfully(self):
        self.assertTrue(search_index.is_dataset_valid(self.dataset_dir))

    def test_dataset_search_is_bidirectional(self):
        english_result = list(search_index.search_sentence_index("people", 1, self.dataset_dir))
        indonesian_result = list(search_index.search_sentence_index("rakyat", 1, self.dataset_dir))

        self.assertEqual("People.", english_result[0]["match"])
        self.assertEqual("Rakyat?", english_result[0]["translation"])
        self.assertEqual("Rakyat?", indonesian_result[0]["match"])
        self.assertEqual("People.", indonesian_result[0]["translation"])
```

Update `tests/test_search_functions.py` config setup to use `sentence_data_dir`:

```python
from sentence_data import builder

# inside setUp()
sentence_data_dir = self.temp_path / "data" / "sentences"
builder.build_sentence_dataset(sentences_path, sentence_data_dir, target_shard_bytes=300)
config_path.write_text(
    json.dumps(
        {
            "dictionary_path": str(dictionary_path),
            "sentence_data_dir": str(sentence_data_dir),
            "red_book_enabled": False,
            "sentence_limit": 4,
        }
    ),
    encoding="utf-8",
)
```

Update `tests/test_cli.py` to build the dataset before running the CLI and remove the old cache-path setup:

```python
from sentence_data import builder

# inside setUp()
self.dataset_dir = self.temp_path / "data" / "sentences"
builder.build_sentence_dataset(sentences_path, self.dataset_dir, target_shard_bytes=300)
self.config_path.write_text(
    json.dumps(
        {
            "dictionary_path": str(dictionary_path),
            "sentence_data_dir": str(self.dataset_dir),
            "red_book_pdf_path": str(self.red_book_pdf_path),
            "red_book_cache_path": str(self.red_book_cache_path),
            "red_book_results_limit": 3,
            "red_book_enabled": True,
            "sentence_limit": 1,
        }
    ),
    encoding="utf-8",
)
```

- [ ] **Step 2: Run the runtime tests and verify they fail**

Run:

```bash
python -B -m unittest tests.test_search_index tests.test_search_functions tests.test_cli -v
```

Expected: failures for missing `is_dataset_valid`, missing `sentence_data_dir` handling, and old cache-based search assumptions.

- [ ] **Step 3: Implement runtime sentence lookup against the shard set**

Replace `search_index.py` with a dataset-backed search facade:

```python
from collections import defaultdict
from pathlib import Path
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
    validated = validate_dataset(dataset_dir)
    if progress_callback is not None:
        progress_callback({"title": "Validating sentence dataset...", "percent": 100.0, "complete": True})
    return {"dataset_dir": str(validated["paths"].root), "rebuilt": False, "validated": True}


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
            f"SELECT sentence_id, shard_file FROM sentence_lookup WHERE sentence_id IN ({placeholders}) ORDER BY sentence_id",
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
```

Update `search_functions.py` to use `sentence_data_dir` and remove the raw text runtime path:

```python
CONFIG_DEFAULTS = {
    "dictionary_path": "en-id_dict.txt",
    "sentence_data_dir": "data/sentences",
    "red_book_pdf_path": "indonesiandictionary.pdf",
    "red_book_cache_path": ".mykamus_cache/red_book.sqlite",
    "red_book_results_limit": 3,
    "red_book_enabled": True,
    "sentence_limit": 4,
    "gui": {
        "always_on_top": True,
        "compact_mode": False,
        "window_size": "900x700",
        "window_position": "+100+100",
        "load_all_sentence_limit": 200,
        "search_status_delay_ms": 200,
    },
    "search": {
        "use_index": True,
    },
    "hotkeys": {
        "manual_search": "ctrl+s",
        "load_all_sentences": "l",
    },
    "poll_interval": 0.1,
}


def sentence_data_dir():
    return data_path("sentence_data_dir")


def is_sentence_index_valid():
    return search_index.is_dataset_valid(sentence_data_dir())


def ensure_sentence_index(progress_callback=None):
    return search_index.ensure_sentence_dataset(
        sentence_data_dir(),
        progress_callback=progress_callback,
    )


def iter_matching_indexed_sentence_pairs(query, limit):
    yield from search_index.search_sentence_index(
        query,
        limit,
        sentence_data_dir(),
    )


def search_for_word_data(query, sentence_limit=_DEFAULT_SENTENCE_LIMIT):
    cleaned_query = normalize_query(query)
    result = {
        "query": cleaned_query,
        "definitions": [],
        "red_book_definitions": [],
        "red_book_results": [],
        "sentences": [],
        "message": None,
        "sentence_limit": None,
        "sentences_truncated": False,
    }
    if not cleaned_query:
        result["message"] = "No word provided. Please enter a word or phrase."
        return result
    config = load_config()
    if sentence_limit is _DEFAULT_SENTENCE_LIMIT:
        sentence_limit = config["sentence_limit"]
    sentence_limit = _coerce_sentence_limit(sentence_limit)
    result["sentence_limit"] = sentence_limit
    for line in iter_matching_dictionary_lines(cleaned_query):
        formatted_line = format_dictionary_line(line)
        if formatted_line:
            result["definitions"].append(formatted_line)
    if red_book_enabled():
        red_book_limit = _coerce_sentence_limit(config.get("red_book_results_limit", 3))
        result["red_book_definitions"] = search_matching_red_book_definitions(
            cleaned_query,
            red_book_limit,
        )
    search_limit = None if sentence_limit is None else sentence_limit + 1
    sentence_iter = iter_matching_indexed_sentence_pairs(cleaned_query, search_limit)
    emitted = set()
    sentence_index = 1
    for sentence in sentence_iter:
        pair_key = (sentence["english"], sentence["indonesian"])
        if pair_key in emitted:
            continue
        if sentence_limit is not None and len(result["sentences"]) >= sentence_limit:
            result["sentences_truncated"] = True
            break
        result["sentences"].append(
            {
                "index": sentence_index,
                "match": sentence["match"],
                "translation": sentence["translation"],
                "matched_language": sentence["matched_language"],
            }
        )
        emitted.add(pair_key)
        sentence_index += 1
    return result


def load_all_sentences(string, sentence_limit=None):
    query = normalize_query(string)
    if not query:
        print("No word provided. Please enter a word or phrase.")
        return
    emitted = set()
    found_any = False
    limit = _coerce_sentence_limit(sentence_limit)
    search_limit = None if limit is None else limit + 1
    index = 1
    for sentence in iter_matching_indexed_sentence_pairs(query, search_limit):
        pair_key = (sentence["english"], sentence["indonesian"])
        if pair_key in emitted:
            continue
        if limit is not None and len(emitted) >= limit:
            print(
                "Showing the first "
                + str(limit)
                + " matching sentence pairs. Narrow the query for fewer results."
            )
            break
        print(format_sentence_block(index, sentence["match"], sentence["translation"]))
        print()
        emitted.add(pair_key)
        found_any = True
        index += 1
    if found_any and (limit is None or len(emitted) < limit):
        print("All example sentences for the word " + query + " have been loaded.")
    elif not found_any:
        print("No example sentences found for the word " + query + ".")
```

- [ ] **Step 4: Run the runtime tests and verify they pass**

Run:

```bash
python -B -m unittest tests.test_search_index tests.test_search_functions tests.test_cli -v
```

Expected: all three test modules pass.

- [ ] **Step 5: Commit the runtime search switch**

Run:

```bash
git add search_index.py search_functions.py tests/test_search_index.py tests/test_search_functions.py tests/test_cli.py
git commit -m "feat: switch sentence search to sharded dataset"
```

---

### Task 4: Update Startup Validation, GUI Backend, And Preflight

**Files:**
- Modify: `gui_app/preflight.py`
- Modify: `gui_app/core/backend.py`
- Modify: `tests/test_gui_preflight.py`
- Modify: `tests/test_gui_core.py`
- Modify: `tests/test_gui_tk.py`

- [ ] **Step 1: Write the failing startup/preflight tests**

Add these assertions to `tests/test_gui_preflight.py`:

```python
from sentence_data import builder


def test_missing_data_files_no_longer_requires_en_id_sentences_txt(self):
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        (base_dir / "en-id_dict.txt").write_text("dict", encoding="utf-8")
        (base_dir / "indonesiandictionary.pdf").write_text("pdf", encoding="utf-8")

        missing = preflight.missing_data_files(base_dir)

    self.assertEqual([], missing)


def test_sentence_dataset_errors_reports_missing_manifest(self):
    with tempfile.TemporaryDirectory() as temp_dir:
        base_dir = Path(temp_dir)
        errors = preflight.sentence_dataset_errors(base_dir)

    self.assertTrue(any("manifest.json" in message for message in errors))
```

Add backend coverage to `tests/test_gui_core.py`:

```python
class GuiBackendTests(unittest.TestCase):
    def test_indexes_are_ready_requires_sentence_dataset_and_red_book_index(self):
        wrapped_backend = backend.GuiBackend(
            is_sentence_index_valid_func=mock.Mock(return_value=True),
            is_red_book_index_valid_func=mock.Mock(return_value=False),
        )

        self.assertFalse(wrapped_backend.indexes_are_ready())

    def test_build_indexes_validates_sentence_dataset_before_red_book_build(self):
        events = []
        wrapped_backend = backend.GuiBackend(
            ensure_sentence_index_func=lambda progress_callback=None: events.append("sentence") or {"validated": True},
            ensure_red_book_index_func=lambda progress_callback=None: events.append("red-book") or {"rebuilt": False},
        )

        wrapped_backend.build_indexes(progress_callback=lambda _progress: None)

        self.assertEqual(["sentence", "red-book"], events)
```

Update `tests/test_gui_tk.py` loading-view progress text to match the new startup story:

```python
build_indexes_callback=lambda progress_callback: progress_callback(
    {
        "title": "Building Red Book index...",
        "percent": 100.0,
        "processed_pages": 1,
        "total_pages": 1,
    }
)
```

- [ ] **Step 2: Run the GUI/preflight tests and verify they fail**

Run:

```bash
python -B -m unittest tests.test_gui_preflight tests.test_gui_core tests.test_gui_tk -v
```

Expected: failures for missing `sentence_dataset_errors`, stale `REQUIRED_DATA_FILES`, and old progress text assumptions.

- [ ] **Step 3: Implement sentence dataset startup validation**

Update `gui_app/preflight.py`:

```python
from sentence_data.layout import DEFAULT_SENTENCE_DATA_DIR, SentenceDataValidationError, validate_dataset


REQUIRED_DATA_FILES = [
    "en-id_dict.txt",
    "indonesiandictionary.pdf",
]


def sentence_dataset_errors(base_dir=BASE_DIR):
    dataset_dir = Path(base_dir) / DEFAULT_SENTENCE_DATA_DIR
    try:
        validate_dataset(dataset_dir)
    except SentenceDataValidationError as error:
        return [str(error)]
    return []


def ensure_data_files(input_func=input, output_func=print):
    missing = missing_data_files()
    dataset_errors = sentence_dataset_errors()
    if not missing and not dataset_errors:
        return True

    if missing:
        output_func("myKamus needs these local data files before it can start:")
        for file_name in missing:
            output_func("- " + file_name)
    if dataset_errors:
        output_func("myKamus needs the checked-in sharded sentence dataset before it can start:")
        for message in dataset_errors:
            output_func("- " + message)
    output_func("")

    if dataset_errors:
        output_func("Restore the data/sentences folder from the repository before starting myKamus.")
        return False

    output_func("The large data files may not have downloaded. This project uses Git LFS for large files.")
    if not command_exists("git"):
        output_func("Git and Git LFS are needed to fetch the bundled data files.")
        return False
    if not prompt_yes_no(
        "Try downloading the data files with git lfs pull?",
        input_func=input_func,
        output_func=output_func,
    ):
        output_func("Cannot start until these data files are present.")
        return False
    if not run_command(["git", "lfs", "pull"]):
        output_func("git lfs pull failed.")
        return False
    still_missing = missing_data_files()
    if still_missing:
        output_func("These data files are still missing:")
        for file_name in still_missing:
            output_func("- " + file_name)
        return False
    return True
```

Update `gui_app/core/backend.py` to validate sentence data first and only build the Red Book index afterward:

```python
class GuiBackend:
    def __init__(
        self,
        *,
        load_config_func=load_config,
        ensure_sentence_index_func=ensure_sentence_index,
        ensure_red_book_index_func=ensure_red_book_index,
        is_sentence_index_valid_func=is_sentence_index_valid,
        is_red_book_index_valid_func=is_red_book_index_valid,
        search_for_word_data_func=search_for_word_data,
    ):
        self._load_config = load_config_func
        self._ensure_sentence_index = ensure_sentence_index_func
        self._ensure_red_book_index = ensure_red_book_index_func
        self._is_sentence_index_valid = is_sentence_index_valid_func
        self._is_red_book_index_valid = is_red_book_index_valid_func
        self._search_for_word_data = search_for_word_data_func

    def load_config(self):
        return self._load_config()

    def indexes_are_ready(self):
        return self._is_sentence_index_valid() and self._is_red_book_index_valid()

    def build_indexes(self, progress_callback):
        sentence_status = self._ensure_sentence_index(progress_callback=progress_callback)
        red_book_status = self._ensure_red_book_index(progress_callback=progress_callback)
        return {
            "sentence_index": sentence_status,
            "red_book_index": red_book_status,
        }

    def search(self, query, sentence_limit):
        return self._search_for_word_data(query, sentence_limit=sentence_limit)
```

- [ ] **Step 4: Run the GUI/preflight tests and verify they pass**

Run:

```bash
python -B -m unittest tests.test_gui_preflight tests.test_gui_core tests.test_gui_tk -v
```

Expected: all three test modules pass.

- [ ] **Step 5: Commit the startup and GUI integration changes**

Run:

```bash
git add gui_app/preflight.py gui_app/core/backend.py tests/test_gui_preflight.py tests/test_gui_core.py tests/test_gui_tk.py
git commit -m "feat: validate sharded sentence data at startup"
```

---

### Task 5: Generate The Checked-In Dataset, Update Docs, And Verify Everything

**Files:**
- Generate: `data/sentences/manifest.json`
- Generate: `data/sentences/sentence_index.sqlite`
- Generate: `data/sentences/shards/sentences_*.sqlite`
- Modify: `README.md`

- [ ] **Step 1: Build the real checked-in sentence dataset**

Run:

```bash
python scripts/build_sentence_data.py --source en-id_sentences.txt --output data/sentences
```

Expected: output like `Built <count> sentence pairs into <count> shards.`

- [ ] **Step 2: Verify the built dataset and inspect shard sizes**

Run:

```bash
python scripts/build_sentence_data.py --verify --output data/sentences
```

Expected: output like `Verified <count> sentence pairs across <count> shards.`

Then check shard sizes:

```bash
powershell -Command "Get-ChildItem data\\sentences\\shards\\*.sqlite | Select-Object Name,@{Name='SizeMB';Expression={[math]::Round($_.Length/1MB,2)}}"
```

Expected: every shard reports `SizeMB` less than `80`.

- [ ] **Step 3: Update README to describe the new runtime sentence layout**

Edit `README.md` so the sentence-data sections say:

```markdown
## Runtime sentence data

myKamus now expects checked-in sharded sentence data under:

~~~text
data/
  sentences/
    manifest.json
    sentence_index.sqlite
    shards/
      sentences_0001.sqlite
      ...
~~~

`en-id_sentences.txt` is no longer the runtime sentence asset. It is a maintainer-only build input used to regenerate the sharded dataset.

Rebuild the dataset with:

~~~bash
python scripts/build_sentence_data.py --source en-id_sentences.txt --output data/sentences
~~~

Verify an existing dataset with:

~~~bash
python scripts/build_sentence_data.py --verify --output data/sentences
~~~
```

Also remove or rewrite any README text that still presents the old sentence file or `.mykamus_cache/search.sqlite` as the normal runtime path.

- [ ] **Step 4: Run the full verification suite**

Run:

```bash
python -B -m unittest discover -s tests
python -m py_compile sentence_data\\layout.py sentence_data\\builder.py scripts\\build_sentence_data.py search_index.py search_functions.py gui_app\\preflight.py gui_app\\core\\backend.py
git diff --check
```

Expected:

- unit test suite passes
- `py_compile` exits successfully
- `git diff --check` prints nothing

- [ ] **Step 5: Commit the generated dataset and docs**

Run:

```bash
git add data/sentences README.md
git commit -m "feat: check in sharded sentence dataset"
```

---

## Self-Review Checklist

- Spec coverage:
  - data layout + manifest validation -> Task 1
  - deterministic builder + verification mode -> Task 2
  - runtime search flow through central index + shards -> Task 3
  - startup/preflight validation -> Task 4
  - checked-in dataset + docs + final verification -> Task 5
- Placeholder scan:
  - no placeholder markers remain
  - commands and file paths are concrete
- Type consistency:
  - `sentence_data_dir` is the runtime config key throughout the plan
  - `validate_dataset()` is the canonical validation entry point
  - `search_index.search_sentence_index(query, limit, dataset_dir)` is the runtime lookup signature throughout the plan
