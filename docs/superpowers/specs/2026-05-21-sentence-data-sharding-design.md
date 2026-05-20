# Sentence Data Sharding Design

## Goal

Replace the single large runtime sentence corpus file, `en-id_sentences.txt`, with a repo-tracked sharded SQLite dataset that is smaller in individual file size, more efficient at runtime, and easier to manage in the repository.

## User Outcome

Users still search sentences in myKamus the same way they do today, but the app no longer depends on one 700+ MB text file at runtime. Instead, sentence data is stored in a structured set of smaller SQLite files with a central routing index.

This improves:

- repository friendliness by removing the giant sentence file from the normal runtime layout
- runtime efficiency by routing lookups through an index instead of scanning or indexing one raw monolith
- maintainability by giving the project an explicit, versioned sentence-data format

## Scope

Included:

- redesign of the runtime sentence-data format only
- replacement of `en-id_sentences.txt` as the runtime sentence source
- a sharded SQLite dataset committed to the repository
- a central SQLite routing index for sentence lookup
- a manifest file for validation and versioning
- in-repo build tooling that generates the dataset from the legacy corpus
- startup/preflight validation for the new dataset
- documentation updates for the new sentence-data layout and maintenance workflow
- tests for the builder, runtime lookup, and dataset validation

Excluded:

- redesign of dictionary storage
- redesign of Red Book PDF storage
- installer or packaging changes beyond what is needed to recognize the new sentence layout
- a backward-compatible runtime fallback to `en-id_sentences.txt`
- a broader all-data bundle that also includes dictionary or Red Book artifacts

## Design Principles

- Make a clean runtime break from the large text file.
- Keep the on-disk layout understandable by humans.
- Enforce a hard size ceiling so no sentence shard exceeds 80 MB.
- Prefer deterministic builds so the same input produces the same outputs.
- Keep the routing index lean and keep full sentence payloads in the shards.
- Treat the built dataset as a first-class application artifact, not as an incidental cache.

## Target Data Layout

The application should use this runtime structure:

```text
data/
  sentences/
    manifest.json
    sentence_index.sqlite
    shards/
      sentences_0001.sqlite
      sentences_0002.sqlite
      ...
```

Rules:

- `sentence_index.sqlite` is the top-level routing database.
- each shard file stores a range of sentence IDs
- no shard file may exceed 80 MB
- shard membership is determined by sentence ID range, not by alphabetic bucket
- the application runtime supports this structure as the only sentence-data source

`en-id_sentences.txt` becomes a maintenance/build input only. It is no longer part of the normal runtime file structure, preflight expectations, or user-facing startup instructions.

## Data Model

The design separates routing data from full sentence content.

### Routing Index

`sentence_index.sqlite` should store only what is needed to resolve lookups efficiently:

- sentence ID
- shard identifier or shard filename
- minimal searchable/routing metadata required by the search path

It should not duplicate the full English and Indonesian sentence bodies in this design.

### Sentence Shards

Each shard database should store the full bilingual sentence rows for the sentence IDs assigned to that shard. At minimum, each row should include:

- sentence ID
- English sentence
- Indonesian sentence

The first version should stay lean and limit shard rows to the minimum fields needed for sentence retrieval.

### Manifest

`manifest.json` should define the dataset contract for the application. It should include:

- schema version
- dataset/build version
- index filename
- shard filenames
- sentence ID range for each shard
- size metadata for each shard
- any source/build metadata needed to validate or troubleshoot the dataset

The manifest must be authoritative for startup validation.

## Build Tooling

The repository should include a supported builder that converts the legacy text corpus into the new runtime dataset.

The builder should:

- read `en-id_sentences.txt` as a build input
- validate that the source data contains well-formed English/Indonesian sentence pairs
- assign stable sentence IDs deterministically
- write shard databases under `data/sentences/shards/`
- roll to a new shard before a file would exceed the 80 MB limit
- build `data/sentences/sentence_index.sqlite`
- write `data/sentences/manifest.json`
- validate the completed dataset before reporting success

The builder should be deterministic. Given the same input and the same builder version, it should produce the same shard ordering, sentence ID ranges, and manifest structure.

The repo should also include a verification mode that validates an existing built dataset without rebuilding it. That verification path should be usable in development, before release, and in automated checks.

The builder must fail loudly when:

- the source text cannot be parsed into valid pairs
- a shard would exceed the size ceiling
- manifest, index, and shard metadata disagree
- required output files are missing
- the final dataset does not pass validation

## Runtime Search Flow

At runtime, sentence lookup should stop reading `en-id_sentences.txt` entirely.

Sentence search should work like this:

1. load and validate `data/sentences/manifest.json`
2. open `sentence_index.sqlite`
3. resolve candidate sentence IDs and shard locations through the index
4. open only the required shard database or databases
5. load full bilingual sentence rows from those shards
6. return the same outward result shape the rest of the application already expects

This keeps the app's user-visible search behavior stable while replacing the sentence storage layer underneath it.

If the sentence dataset is missing, corrupt, or incompatible with the running app, the runtime should fail with a clear data-layout error. It must not silently fall back to the retired raw text file.

## Repository And Migration Policy

After migration, the repository should track:

- `data/sentences/manifest.json`
- `data/sentences/sentence_index.sqlite`
- all shard databases under `data/sentences/shards/`

The large sentence text file is no longer part of the runtime contract. The repository and documentation should stop presenting it as a required normal-use asset.

Policy rules:

- no sentence shard may exceed 80 MB
- sentence shard files are generated artifacts owned by the builder
- humans should not hand-edit shard databases
- if the sentence source changes, the builder is rerun and the generated artifacts are recommitted

The legacy text file may still exist as a maintainer-only build input, but it should move out of the ordinary runtime story and should not remain the shape of sentence data that the application expects users to provide.

## Validation And Startup Checks

Startup and preflight checks should validate the sentence dataset explicitly.

Validation must confirm:

- `data/sentences/manifest.json` exists
- the index file named in the manifest exists
- every shard listed in the manifest exists
- no shard exceeds the allowed size ceiling
- schema and version metadata are compatible with the running application
- the index and shard metadata agree with the manifest

Validation errors should be surfaced clearly so missing or broken sentence data is easy to diagnose.

## Testing Strategy

Testing should cover three layers.

### Builder Tests

- malformed or incomplete source input
- deterministic sentence ID assignment
- deterministic shard boundaries
- shard file size enforcement
- manifest correctness
- validation-mode behavior

### Runtime Tests

- routing index lookup
- shard row retrieval
- correct assembly of outward search results
- clear failure behavior when the dataset is missing or corrupt
- rejection of incompatible manifest/schema versions

### Integration Tests

- end-to-end sentence search using the sharded dataset
- startup validation against a representative dataset
- representative rebuild and validation flow for maintainers

## Documentation

`README.md` and related maintenance docs should be updated to explain:

- the new sentence-data layout
- that `en-id_sentences.txt` is no longer the runtime sentence asset
- how to rebuild the sentence shard set
- how to validate an existing sentence dataset
- the 80 MB shard-size policy

The documentation should present the sharded SQLite layout as the normal sentence-data format for the project going forward.
