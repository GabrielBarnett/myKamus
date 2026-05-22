# Remove Git LFS Dependency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the current myKamus repository usable without Git LFS while preserving every runtime data file the program needs.

**Architecture:** Use a forward-only migration: remove LFS attributes, commit the real `en-id_dict.txt` content as a normal Git blob, and remove runtime preflight behavior that asks users to run `git lfs pull`. Do not rewrite history or change data file paths.

**Tech Stack:** Git, Git LFS inspection commands, Python standard library, unittest, existing preflight checks.

---

## Important Current Context

The repository is on `master`. The design spec is:

- `docs/superpowers/specs/2026-05-22-remove-lfs-dependency-design.md`

Current LFS inventory:

- `git lfs ls-files --long` reports only `en-id_dict.txt`.
- `.gitattributes` contains LFS rules for `en-id_dict.txt` and `*.tmx`.
- No `*.tmx` files are tracked.
- `en-id_dict.txt` exists in the working tree as the real dictionary file, about 4.67 MB.
- `HEAD:en-id_dict.txt` is still a 132-byte LFS pointer.
- `indonesiandictionary.pdf` is already a normal tracked file and should not be changed.

There are unrelated untracked files in the main worktree:

- `sentence_data/`
- `tests/__init__.py`
- `tests/test_sentence_data_layout.py`

Leave those untracked files alone.

---

## Target File Structure

Modify:

- `.gitattributes`: remove all LFS filter rules; keep the sentence chunk LF rule.
- `en-id_dict.txt`: replace the tracked LFS pointer with the real dictionary text file at the same path.
- `gui_app/preflight.py`: remove the runtime Git LFS fallback and prompt.
- `tests/test_gui_preflight.py`: update tests for missing data files to expect a repository-restore message, not a Git LFS flow.

Do not modify:

- `indonesiandictionary.pdf`
- `data/sentence_source/**`
- historical Superpowers plan/spec documents, except for this new plan
- unrelated untracked files

---

## Task 1: Track Dictionary Without Git LFS

**Files:**

- Modify: `.gitattributes`
- Modify: `en-id_dict.txt`

- [ ] **Step 1: Confirm the current failing state**

Run:

~~~powershell
git lfs ls-files --long
git check-attr -a -- en-id_dict.txt "*.tmx" data/sentence_source/chunks/en-id_sentences_0001.txt
git cat-file -s HEAD:en-id_dict.txt
git cat-file -p HEAD:en-id_dict.txt
Get-Item en-id_dict.txt | Select-Object Name,Length,@{Name='MB';Expression={[math]::Round($_.Length/1MB,2)}}
~~~

Expected before the fix:

- `git lfs ls-files --long` includes `en-id_dict.txt`.
- `git check-attr` shows `filter: lfs`, `diff: lfs`, and `merge: lfs` for `en-id_dict.txt`.
- `git check-attr` shows `filter: lfs`, `diff: lfs`, and `merge: lfs` for `*.tmx`.
- `git check-attr` shows `text: set` and `eol: lf` for `data/sentence_source/chunks/en-id_sentences_0001.txt`.
- `git cat-file -s HEAD:en-id_dict.txt` prints `132`.
- `git cat-file -p HEAD:en-id_dict.txt` begins with `version https://git-lfs.github.com/spec/v1`.
- `Get-Item en-id_dict.txt` shows the real working-tree file at about 4.67 MB.

- [ ] **Step 2: Update `.gitattributes`**

Replace the entire `.gitattributes` file with:

~~~text
data/sentence_source/chunks/*.txt text eol=lf
~~~

This removes all Git LFS filter rules while preserving the LF protection for sentence source chunks.

- [ ] **Step 3: Stage the real dictionary content**

Run:

~~~powershell
git add .gitattributes
git add --renormalize en-id_dict.txt
~~~

If `git add --renormalize en-id_dict.txt` does not stage the real file, run:

~~~powershell
git add --force en-id_dict.txt
~~~

- [ ] **Step 4: Verify the staged index, not only the working tree**

Run:

~~~powershell
git diff --cached --stat -- .gitattributes en-id_dict.txt
git check-attr -a -- en-id_dict.txt "*.tmx" data/sentence_source/chunks/en-id_sentences_0001.txt
git cat-file -s :en-id_dict.txt
git cat-file -p :en-id_dict.txt | Select-Object -First 3
~~~

Expected after staging:

- The cached diff includes `.gitattributes` and `en-id_dict.txt`.
- `git check-attr` shows no LFS filter, diff, or merge attributes for `en-id_dict.txt`.
- `git check-attr` shows no LFS filter, diff, or merge attributes for `*.tmx`.
- `git check-attr` still shows `text: set` and `eol: lf` for `data/sentence_source/chunks/en-id_sentences_0001.txt`.
- `git cat-file -s :en-id_dict.txt` prints a value larger than `1000000`.
- `git cat-file -p :en-id_dict.txt | Select-Object -First 3` does not print `version https://git-lfs.github.com/spec/v1`.

- [ ] **Step 5: Commit the Git metadata and dictionary blob**

Run:

~~~powershell
git commit -m "chore: track dictionary without git lfs"
~~~

---

## Task 2: Remove Runtime Git LFS Fallback

**Files:**

- Modify: `gui_app/preflight.py`
- Modify: `tests/test_gui_preflight.py`

- [ ] **Step 1: Write the failing preflight tests**

In `tests/test_gui_preflight.py`, replace the Git LFS flow tests with tests that prove missing data files do not prompt for Git LFS or run `git lfs pull`.

Delete the existing tests named:

- `test_ensure_data_files_fails_when_git_is_unavailable`
- `test_ensure_data_files_runs_git_lfs_pull_when_user_approves`
- `test_ensure_data_files_fails_when_files_remain_missing_after_git_lfs`
- `test_ensure_data_files_fails_when_user_declines_git_lfs`

Add these tests in the same area:

~~~python
def test_ensure_data_files_reports_missing_files_without_git_lfs_flow(self):
    messages = []
    input_func = mock.Mock(return_value="y")

    with mock.patch.object(preflight, "missing_data_files", return_value=["en-id_dict.txt"]), \
            mock.patch.object(preflight, "sentence_source_errors", return_value=[]), \
            mock.patch("gui_app.preflight.subprocess.run") as subprocess_run:
        result = preflight.ensure_data_files(
            input_func=input_func,
            output_func=messages.append,
        )

    self.assertFalse(result)
    input_func.assert_not_called()
    subprocess_run.assert_not_called()
    self.assertTrue(any("en-id_dict.txt" in message for message in messages))
    self.assertTrue(any("Restore the missing data files" in message for message in messages))
    self.assertFalse(any("Git LFS" in message for message in messages))
    self.assertFalse(any("git lfs" in message.casefold() for message in messages))


def test_ensure_data_files_reports_missing_files_and_source_without_git_lfs_flow(self):
    messages = []
    input_func = mock.Mock(return_value="y")

    with mock.patch.object(preflight, "missing_data_files", return_value=["en-id_dict.txt"]), \
            mock.patch.object(preflight, "sentence_source_errors", return_value=["Sentence source is missing manifest.json."]), \
            mock.patch("gui_app.preflight.subprocess.run") as subprocess_run:
        result = preflight.ensure_data_files(
            input_func=input_func,
            output_func=messages.append,
        )

    self.assertFalse(result)
    input_func.assert_not_called()
    subprocess_run.assert_not_called()
    self.assertTrue(any("en-id_dict.txt" in message for message in messages))
    self.assertTrue(any("data/sentence_source" in message for message in messages))
    self.assertTrue(any("manifest.json" in message for message in messages))
    self.assertFalse(any("Git LFS" in message for message in messages))
    self.assertFalse(any("git lfs" in message.casefold() for message in messages))
~~~

Keep or rename the pointer-file detection test. A Git LFS pointer should still count as a damaged local data file, but preflight should not offer to fix it with Git LFS.

- [ ] **Step 2: Run the targeted test and verify it fails**

Run:

~~~powershell
python -B -m unittest discover -s tests -p test_gui_preflight.py -k "git_lfs_flow" -v
~~~

Expected before the production change:

- The new tests fail because `ensure_data_files()` still prints Git LFS messages and may call the Git LFS flow.

- [ ] **Step 3: Update `gui_app/preflight.py`**

Remove these functions if they are no longer used:

~~~python
def command_exists(command_name):
    return shutil.which(command_name) is not None


def run_command(command):
    return subprocess.run(command, cwd=BASE_DIR).returncode == 0
~~~

The tests above patch `subprocess.run` directly, so they still work whether the old helper is removed or kept temporarily. Prefer deleting both helpers if no other code uses them.

Then replace `ensure_data_files()` with:

~~~python
def ensure_data_files(input_func=input, output_func=print):
    missing = missing_data_files()
    sentence_errors = sentence_source_errors()
    if not missing and not sentence_errors:
        return True

    if missing:
        output_func("myKamus needs these local data files before it can start:")
        for file_name in missing:
            output_func("- " + file_name)
        output_func("")

    if sentence_errors:
        output_func("myKamus needs the included sentence source chunks before it can start:")
        for message in sentence_errors:
            output_func("- " + message)
        output_func("Restore the data/sentence_source folder from the repository.")

    if missing:
        output_func(
            "Restore the missing data files from a fresh copy of the repository or your approved internal source."
        )

    return False
~~~

Keep `is_git_lfs_pointer()` unless removing it also updates `missing_data_files()` safely. It remains useful because a pointer file is not a usable dictionary.

- [ ] **Step 4: Run the focused preflight tests**

Run:

~~~powershell
python -B -m unittest discover -s tests -p test_gui_preflight.py -v
~~~

Expected:

- All preflight tests pass.
- No test expects `git lfs pull`.

- [ ] **Step 5: Check runtime/user-facing LFS references**

Run:

~~~powershell
git grep -n -i "git lfs\|lfs pull\|Git and Git LFS\|uses Git LFS" -- gui_app tests README.md
~~~

Expected:

- No output.

The pointer header string `version https://git-lfs.github.com/spec/v1` may remain in pointer-detection code or tests. That string is not a runtime dependency or user instruction.

- [ ] **Step 6: Commit the preflight cleanup**

Run:

~~~powershell
git add gui_app/preflight.py tests/test_gui_preflight.py
git commit -m "fix: remove git lfs preflight fallback"
~~~

---

## Task 3: Final No-LFS Verification

**Files:**

- No file changes expected.

- [ ] **Step 1: Verify Git no longer tracks LFS files**

Run:

~~~powershell
git lfs ls-files --long
git check-attr -a -- en-id_dict.txt "*.tmx" data/sentence_source/chunks/en-id_sentences_0001.txt
git cat-file -s HEAD:en-id_dict.txt
git cat-file -p HEAD:en-id_dict.txt | Select-Object -First 3
~~~

Expected:

- `git lfs ls-files --long` prints no tracked LFS files.
- `en-id_dict.txt` has no LFS filter, diff, or merge attributes.
- `*.tmx` has no LFS filter, diff, or merge attributes.
- `data/sentence_source/chunks/en-id_sentences_0001.txt` still has `text: set` and `eol: lf`.
- `git cat-file -s HEAD:en-id_dict.txt` prints a value larger than `1000000`.
- The first lines of `HEAD:en-id_dict.txt` do not include `version https://git-lfs.github.com/spec/v1`.

- [ ] **Step 2: Verify runtime data files still exist**

Run:

~~~powershell
Get-Item en-id_dict.txt, indonesiandictionary.pdf, data/sentence_source/manifest.json |
    Select-Object Name,Length,@{Name='MB';Expression={[math]::Round($_.Length/1MB,2)}}
~~~

Expected:

- `en-id_dict.txt` exists and is about 4.67 MB.
- `indonesiandictionary.pdf` exists and is about 22.98 MB.
- `manifest.json` exists.

- [ ] **Step 3: Verify sentence chunks still validate**

Run:

~~~powershell
python scripts/split_sentence_source.py --verify --output data/sentence_source
~~~

Expected:

- Output includes `Verified 7386480 sentence pairs across 8 chunks.`

- [ ] **Step 4: Run the full test suite**

Run:

~~~powershell
python -B -m unittest discover -s tests
~~~

Expected:

- All tests pass.
- The known Tk `ttk::ThemeChanged` teardown noise may appear on stderr, but the unittest result must be `OK`.

- [ ] **Step 5: Verify tracked blob size ceiling**

Run:

~~~powershell
git ls-files | ForEach-Object {
    $p = $_
    $s = [int64](git cat-file -s "HEAD:$p")
    if ($s -gt 80MB) {
        [pscustomobject]@{ MB = [math]::Round($s/1MB,2); Bytes = $s; Path = $p }
    }
} | Sort-Object Bytes -Descending | Format-Table -AutoSize
~~~

Expected:

- No output.

- [ ] **Step 6: Confirm worktree status**

Run:

~~~powershell
git status --short --branch
~~~

Expected:

- The branch may show unrelated untracked files that existed before this work:
  - `sentence_data/`
  - `tests/__init__.py`
  - `tests/test_sentence_data_layout.py`
- There should be no unstaged or staged changes from this no-LFS work.

---

## Completion Criteria

The work is ready for review when:

- `.gitattributes` contains no LFS rules.
- `en-id_dict.txt` is a normal tracked Git blob, not a pointer.
- `git lfs ls-files --long` reports nothing.
- Preflight no longer asks users to install Git LFS or run `git lfs pull`.
- Runtime data files still exist at the same paths.
- Full tests pass.
- Sentence source verification passes.
