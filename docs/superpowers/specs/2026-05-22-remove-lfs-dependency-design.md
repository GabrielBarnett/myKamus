# Remove Git LFS Dependency Design

## Goal

Make the current myKamus repository usable from a normal GitHub clone or ZIP download without requiring Git LFS, while keeping all runtime files needed by the program in the repository.

## Current State

The sentence corpus has already moved away from Git LFS. It now lives in tracked source chunks under `data/sentence_source/`, and those chunks build the local `.mykamus_cache/search.sqlite` cache on first run.

The remaining Git LFS dependency is the dictionary file:

- `en-id_dict.txt` is tracked by Git LFS.
- The working tree contains the real `en-id_dict.txt` file, about 4.67 MB.
- The Git blob at `HEAD:en-id_dict.txt` is still a 132-byte LFS pointer.
- `.gitattributes` still contains LFS rules for `en-id_dict.txt` and `*.tmx`.
- No `*.tmx` files are currently tracked.
- `indonesiandictionary.pdf` is already a normal tracked file and should not be changed by this work.

## Chosen Approach

Use a forward-only un-LFS migration.

This means the current branch will stop using Git LFS from this point forward, but repository history will not be rewritten. Older commits may still contain LFS pointers, but the current usable project state will not require Git LFS.

## Repository Changes

The implementation should:

1. Remove all Git LFS filter rules from `.gitattributes`.
2. Keep non-LFS attributes that protect the sentence chunk data, especially `data/sentence_source/chunks/*.txt text eol=lf`.
3. Replace the tracked `en-id_dict.txt` pointer with the real dictionary file content.
4. Keep `en-id_dict.txt` at its existing repository path so runtime code and user instructions do not need to change.
5. Leave `indonesiandictionary.pdf` untouched.
6. Leave the existing sentence source chunks untouched except for verification.

## Out Of Scope

This work should not:

- Rewrite Git history.
- Force-push.
- Reintroduce Git LFS through another asset rule.
- Redesign dictionary storage.
- Split `en-id_dict.txt`; it is small enough to track directly.
- Change the sentence chunk format.
- Remove local untracked files unrelated to this work.

## Verification

The implementation is successful when:

- `git lfs ls-files` reports no tracked LFS files.
- `git check-attr -a -- en-id_dict.txt` shows no LFS filter, diff, or merge attributes.
- `git cat-file -s HEAD:en-id_dict.txt` reports the real dictionary size, not a tiny pointer.
- `git cat-file -p HEAD:en-id_dict.txt` no longer begins with `version https://git-lfs.github.com/spec/v1`.
- `en-id_dict.txt` still exists in the working tree and can be read by the app.
- The full test suite passes.
- Sentence source verification still passes.
- No tracked blob exceeds the current project size ceiling for GitHub hosting.

## User Impact

After this change, a non-technical user should be able to get the current repository without installing Git LFS and still have:

- dictionary lookup through `en-id_dict.txt`
- sentence search through tracked source chunks and the generated local cache
- Red Book lookup through the existing PDF and local cache

## Risks And Tradeoffs

The forward-only approach avoids disruptive history rewriting, but old commits may still refer to LFS objects. That is acceptable because the user-facing goal is to make the current project state easy to clone, download, and run.

The dictionary file adds about 4.67 MB of normal Git content, which is small enough for direct tracking.
