# Sentence Source Chunks Design

## Goal

Make the sentence corpus hostable on GitHub without Git LFS by replacing the single large `en-id_sentences.txt` runtime/source file with smaller repo-tracked source chunks. myKamus will build the fast local SQLite sentence cache from those chunks on first run.

## Correction To Previous Design

The previous sharded sentence-data design treated generated SQLite files as repo-tracked runtime data. That does not match the intended distribution model.

The corrected model is:

- Git tracks small source-data chunks.
- User machines build generated SQLite cache files locally.
- Generated cache files stay in `.mykamus_cache/` and remain ignored by Git.
- No generated SQLite sentence index is committed to GitHub.

This design supersedes the checked-in `data/sentences/*.sqlite` runtime artifact direction for the sentence corpus.

## User Outcome

A non-technical user can clone or download the GitHub repository without Git LFS, run myKamus, and let the app build its local sentence cache from included chunk files. The first launch may take time, but it should show clear progress and reuse the cache afterward.

The user should not need to locate, download, or place one huge `en-id_sentences.txt` file for normal use.

## Scope

Included:

- sentence corpus distribution only
- splitting `en-id_sentences.txt` into repo-tracked chunks
- manifest validation for chunk order, size, checksums, and pair counts
- first-run local cache build from chunks
- progress reporting during cache build
- documentation updates for users and maintainers
- tests for chunk splitting, validation, and cache rebuild behavior

Excluded for this amendment:

- redesigning dictionary storage
- redesigning Red Book PDF storage
- committing generated SQLite sentence caches
- adding a Windows installer or packaged app
- deleting the maintainer-only source file from all developer workflows

If `en-id_dict.txt` or `indonesiandictionary.pdf` also exceed GitHub limits, they should be handled by separate follow-up designs. The sentence corpus is the current blocker.

## Target Repository Layout

The repository should track this source-data layout:

```text
data/
  sentence_source/
    manifest.json
    chunks/
      en-id_sentences_0001.txt
      en-id_sentences_0002.txt
      en-id_sentences_0003.txt
      ...
```

The repository should not track this generated cache:

```text
.mykamus_cache/
  search.sqlite
```

`en-id_sentences.txt` becomes a maintainer-only input for regenerating chunks. It is not the normal runtime asset and should not be required for GitHub users.

## Chunk Rules

Each chunk file must:

- stay below 80 MB
- use a target size below the hard ceiling, such as 72 MB, to leave margin
- preserve the existing alternating English and Indonesian line-pair format
- never split a bilingual pair across files
- keep source order deterministic
- use UTF-8 text

The splitter must reject malformed source input, including an unmatched trailing line.

## Manifest

`data/sentence_source/manifest.json` is the source-data contract. It should include:

- schema version
- source format name
- ordered chunk list
- file name for each chunk
- byte size for each chunk
- SHA-256 checksum for each chunk
- sentence-pair count for each chunk
- total sentence-pair count
- optional source metadata for maintainers

The manifest is authoritative. Runtime code must validate it before building or trusting the cache.

## Local Cache Build

At runtime, myKamus should use `.mykamus_cache/search.sqlite` as the fast sentence search cache.

Startup flow:

1. Validate `data/sentence_source/manifest.json`.
2. Validate all listed chunk files exist, stay under 80 MB, and match checksums.
3. Check whether `.mykamus_cache/search.sqlite` exists and matches the manifest signature.
4. If the cache is missing or stale, build it from the ordered chunks.
5. Show progress while reading chunks and building the SQLite cache.
6. Use the completed local cache for sentence lookup.

The cache should record the source manifest signature it was built from. If the source chunks change, the cache should rebuild automatically.

Cache rebuild must be safe:

- build into a temporary SQLite file
- validate the finished cache
- atomically replace the old cache only after validation passes
- leave the old working cache intact if rebuild fails

## Search Behavior

User-visible sentence search behavior should stay the same:

- Indonesian queries return English translations.
- English queries return Indonesian translations.
- duplicate sentence pairs are suppressed.
- configured result limits are respected.
- missing or invalid source chunks produce a clear data error.

The runtime should not fall back to `en-id_sentences.txt` for normal users.

## Maintainer Tooling

The repository should include a supported splitter command, for example:

```bash
python scripts/split_sentence_source.py --source en-id_sentences.txt --output data/sentence_source
```

The tool should:

- create `data/sentence_source/chunks/`
- write ordered chunk files
- write `manifest.json`
- verify generated chunks before reporting success
- fail if any chunk exceeds 80 MB

It should also support a verification mode:

```bash
python scripts/split_sentence_source.py --verify --output data/sentence_source
```

## Startup And Preflight

Preflight should require the chunked sentence source layout, not `en-id_sentences.txt` and not checked-in SQLite sentence shards.

If chunks are missing or invalid, the user-facing message should say that the included sentence source chunks are missing or damaged and should be restored from the repository.

If the local SQLite cache is missing, startup should offer or begin rebuilding it from the included chunks, depending on the existing GUI startup flow.

## Documentation

README should explain:

- the GitHub repository includes chunked sentence source files
- no Git LFS is needed for the sentence corpus
- first launch builds a local SQLite cache
- later launches reuse the cache
- `en-id_sentences.txt` is maintainer-only
- how maintainers regenerate chunks
- how developers verify chunks

README should stop presenting `.mykamus_cache/search.sqlite` as a committed or bundled file. It is generated local runtime data.

## Testing Strategy

Tests should cover:

- splitter preserves pair boundaries
- splitter rejects malformed source with unmatched trailing lines
- splitter writes deterministic chunks and manifest
- manifest validation rejects missing, oversized, reordered, or checksum-mismatched chunks
- cache build reads chunks in manifest order
- cache rebuild happens when manifest signature changes
- cache rebuild leaves the old cache intact on failure
- runtime sentence search works from the locally built cache
- runtime does not require `en-id_sentences.txt`

## Migration Notes

The existing sharded SQLite dataset work should be revised rather than extended. In particular:

- remove or replace code paths expecting `data/sentences/manifest.json`
- remove the plan to commit `data/sentences/sentence_index.sqlite`
- reuse useful validation and safe-build patterns where they still fit
- preserve the user-facing goal of simple startup and clear progress

Any uncommitted builder performance changes from the blocked checked-in-SQLite attempt should be reviewed before reuse. They should not be carried forward automatically unless they serve the chunked-source and local-cache design.

## Success Criteria

The amendment is successful when:

- `en-id_sentences.txt` is no longer required for normal runtime use
- GitHub can host the sentence corpus as files under 80 MB each
- the app builds `.mykamus_cache/search.sqlite` locally from chunks
- first-run cache build has clear progress
- subsequent runs reuse the local cache
- tests pass
- README describes the corrected distribution model
