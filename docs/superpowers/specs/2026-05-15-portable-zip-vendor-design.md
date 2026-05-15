# Portable Zip With Local Vendor Dependencies Design

## Goal

Make myKamus easier to distribute and run on a closed corporate network without shipping new executable files and without requiring users to install Python packages into global Python locations.

## User Outcome

A non-technical Windows user receives a GitHub-friendly myKamus zip, extracts it, double-clicks `Start myKamus.bat`, answers one setup-method question on first run, and runs the GUI using corporate-approved installed Python. Python dependencies install locally into the myKamus folder.

## Constraints

- Corporate-approved Python is already available.
- The package must not introduce a custom `.exe`.
- Dependencies should live locally inside the myKamus folder.
- The corporate network may have no internet access.
- A corporate pip mirror may exist, but it can be confusing or unreliable for non-technical users.
- Large data files already exist on the corporate network and should not be included in the GitHub-uploadable zip.
- Source-layout cleanup is useful, but it should be planned separately after the portable package flow is stable.
- CLI packaging is deferred; the first portable package is GUI-first.

## Package Shape

The first portable zip should be a user-only runtime package, not a developer archive.

Included:

```text
myKamus/
  Start myKamus.bat
  README_FIRST.txt
  requirements.txt
  wheels/
  gui_app/
  clean_text.py
  config.example.json
  red_book_index.py
  search_functions.py
  search_index.py
```

Generated at runtime:

```text
myKamus/
  vendor/
  .mykamus_cache/
    setup.json
    search.sqlite
    red_book.sqlite
```

Excluded from the portable zip:

```text
en-id_dict.txt
en-id_sentences.txt
indonesiandictionary.pdf
tests/
docs/superpowers/
.git/
.idea/
venv/
.mykamus_cache/
__pycache__/
```

## Local Dependency Model

Dependencies should install into a local `vendor/` folder instead of global Python or a virtual environment.

Wheel-first install command:

```bash
python -m pip install --target vendor --no-index --find-links wheels -r requirements.txt
```

Mirror fallback install command:

```bash
python -m pip install --target vendor -r requirements.txt
```

Runtime import behavior:

- Prepend `vendor/` to `sys.path` before importing third-party dependencies.
- Verify imports with the same corporate-approved Python that launches the app.
- Reuse `vendor/` on later launches.

This avoids creating `.venv/Scripts/python.exe` and keeps packages local to the myKamus folder.

## Setup Choice Flow

The launcher/preflight should ask about the setup method before checking dependency imports.

Reason: on some corporate computers, pip can report packages as installed even when the Python runtime used by the app cannot import them.

First run:

1. Check `.mykamus_cache/setup.json` for a remembered setup method.
2. If none exists, ask once:

   ```text
   How should myKamus set up Python packages?

   1. Use local wheels included with myKamus
   2. Use normal pip, such as the corporate pip mirror
   ```

3. Save the selected method in `.mykamus_cache/setup.json`.
4. Run the selected install command into `vendor/`.
5. Verify imports from `vendor/`.

Later runs:

1. Read the remembered method from `.mykamus_cache/setup.json`.
2. Use that method automatically if dependencies need setup again.
3. Verify imports from `vendor/`.
4. If imports fail, explain that pip may have installed packages somewhere this Python cannot see, then offer the other method as fallback.

The remembered setup choice is local to the project folder so the zip remains portable.

## Python Version Handling

The package should target one corporate Python version, but that version may not be known during design.

Build-time behavior:

- Record the Python version used to prepare the package or download wheels.
- Store it in portable package metadata.

Runtime behavior:

- Compare current runtime Python to the recorded version.
- If versions differ, warn rather than hard-stop.
- Offer fallback setup options because the corporate pip mirror may still provide compatible packages.

Example warning:

```text
This myKamus package was prepared with Python 3.11.
You are running Python 3.12.
Some bundled wheels may not load correctly.
```

## Data Location Flow

Large data files are not included in the GitHub-friendly portable zip.

Required data files:

```text
en-id_dict.txt
en-id_sentences.txt
indonesiandictionary.pdf
```

Lookup priority:

1. App folder.
2. Remembered corporate data folder from `.mykamus_cache/setup.json`.
3. User-provided corporate data folder.
4. Git LFS fallback.
5. Clear failure message.

Flow:

1. Check app folder for all required data files.
2. If files are missing, check remembered data folder.
3. If no remembered folder exists or files are missing there, ask:

   ```text
   Do you already have the myKamus data files in a corporate network folder? [Y/N]
   ```

4. If yes, ask for the folder path, validate required files, and remember the folder in `.mykamus_cache/setup.json`.
5. If no, or if the selected folder is invalid, offer:

   ```text
   Try downloading the large data files with git lfs pull? [Y/N]
   ```

6. If Git LFS succeeds, use files in the app folder.
7. If no valid source is available, print exactly which files are missing.

The current Git LFS pointer-file detection should remain so placeholder files do not count as ready data.

## Build Script

Add:

```text
scripts/build_portable_zip.py
```

Responsibilities:

- Create a clean staging folder such as `dist/myKamus-portable/`.
- Copy only user-facing runtime files.
- Exclude large data files.
- Include `wheels/` if present.
- Optionally download wheels when invoked with `--download-wheels`:

  ```bash
  python -m pip download -r requirements.txt -d wheels
  ```

- Record package metadata, including build Python version.
- Create a zip suitable for GitHub upload.

The default build should package an existing `wheels/` folder. Downloading wheels should be opt-in for build machines that can access the corporate mirror.

## Documentation

Add:

```text
README_FIRST.txt
docs/portable-distribution.md
```

`README_FIRST.txt` is for non-technical users and should cover:

- Double-click `Start myKamus.bat`.
- Choose local wheels or normal pip when asked.
- Where to find or place data files.
- What to do if setup fails.
- Who to contact internally.

`docs/portable-distribution.md` is for maintainers and should cover:

- How to build the portable zip.
- How to include or download wheels.
- Why large data files are excluded.
- How data-folder fallback works.
- Why dependencies install into `vendor/`.
- Why installer and source-layout cleanup are deferred.

## Deferred Work

Do not include these in the first implementation:

- A Windows installer.
- Bundled Python.
- Custom `.exe` packaging.
- CLI-specific launchers.
- Moving modules into a `src/` package layout.
- Shipping the large data files in the GitHub zip.

These can be planned after the portable zip flow is proven.

## Testing Strategy

Unit tests should cover:

- Setup choice is asked before dependency import checks.
- Setup choice is remembered in `.mykamus_cache/setup.json`.
- Local wheels install command uses `--target vendor --no-index --find-links wheels`.
- Normal pip fallback uses `--target vendor`.
- `vendor/` is prepended before dependency imports.
- Python version mismatch warns and offers fallback instead of hard-stopping.
- Data lookup checks app folder, remembered data folder, user-provided folder, then Git LFS fallback.
- Missing data messages list exact filenames.
- Git LFS pointer files do not count as valid data.
- Build script excludes large data files and includes runtime files.
- Build script optionally downloads wheels only when requested.

Manual smoke tests should cover:

- Build a portable zip.
- Extract it to a clean folder.
- Run `Start myKamus.bat` with local wheels.
- Run with no data files in app folder and select a corporate data folder.
- Launch GUI and allow first-run indexing.
