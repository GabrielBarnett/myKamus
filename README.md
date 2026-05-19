# myKamus

myKamus is an open source Indonesian-English dictionary and example sentence search tool. It combines dictionary entries, indexed bilingual sentence pairs, and Red Book headword definitions in a desktop GUI and CLI.

It uses open source bitext corpora to provide access to over 50 million example sentences and word translations for Indonesian ↔ English.

## Features

- Tkinter desktop GUI with manual search, clipboard monitoring, compact mode, recent searches, and always-on-top support.
- Fast indexed lookup using local SQLite caches in `.mykamus_cache/`.
- Bidirectional sentence search: Indonesian queries return English translations, and English queries return Indonesian translations.
- Red Book Results section for whole-word Indonesian headword definitions extracted from `indonesiandictionary.pdf`.
- CLI search for quick terminal lookups.

## Windows beginner start

On Windows, double-click:

```text
Start myKamus.bat
```

The launcher checks whether local Python packages and bundled data files are ready before starting the GUI. Python packages are installed into `.mykamus_vendor/` inside the myKamus folder, and the desktop app uses the Tkinter module that normally ships with Python, so myKamus does not depend on a separately installed GUI toolkit or other global pip package state on corporate computers.

If local packages are missing, the launcher asks before deleting `.mykamus_vendor/` and reinstalling dependencies with:

```bash
python -m pip install --target .mykamus_vendor --upgrade --force-reinstall -r requirements.txt
```

If setup fails, myKamus writes details to `myKamus_setup.log`. Send that file to your internal support person.

Mac, Linux, and manual users can still run:

```bash
python -m gui_app.app
```

This is still a source-folder launcher, not a packaged `.exe`. A true Windows app or installer is a future improvement.

## Prerequisites for Mac, Linux, and development

- Python 3.x
- Tkinter support in the Python install
- Git LFS for the bundled dictionary and sentence corpus
- Python dependencies in `requirements.txt`

Install Git LFS and Python dependencies:

```bash
git lfs install
git lfs pull
python -m pip install -r requirements.txt
```

If `git status`, clone, or checkout fails with `git-lfs: command not found`, install Git LFS first. On macOS with Homebrew:

```bash
brew install git-lfs
git lfs install
git lfs pull
```

## GUI usage

The main app is the Tkinter GUI:

```bash
python -m gui_app.app
```

On first launch, myKamus builds local SQLite indexes for the sentence corpus and Red Book definitions. The loading screen shows progress as a percentage. Later launches reuse the cache unless the source data changes.

Search workflow:

- Type a word or phrase and press Enter or click Search.
- After a manual search, the search box keeps focus and selects the previous query so you can type the next word immediately.
- Clipboard monitoring updates results automatically without stealing focus from the search box.
- Load All is capped by the GUI configuration so common words do not attempt to render an unbounded result set.

Result order:

1. Red Book Results
2. Word Translations
3. Example Sentences

## CLI usage

You can also run a one-off search from the command line:

```bash
python cli.py "kata"
python cli.py "kata" --all-sentences
```

## Legacy clipboard launcher

The older console clipboard workflow is still available:

```bash
python myKamus_initialise.py
```

The GUI is the recommended runtime path for normal use.

## Configuration

Runtime settings such as file paths, hotkeys, and the default sentence limit are stored in `config.json`.
Defaults are tracked in `config.example.json`. The GUI writes local window settings to `config.json`, which is ignored by Git.
You can create or update `config.json` to customize keyboard shortcuts, sentence limits, cache paths, Red Book indexing, or data file paths.

Generated search indexes live in `.mykamus_cache/` and are rebuilt automatically when the sentence corpus or Red Book PDF changes. They are local runtime data and should not be committed.

## Data Sources

Bitext corpus for sentences sourced from:

P. Lison and J. Tiedemann, 2016, OpenSubtitles2016: Extracting Large Parallel Corpora from Movie and TV Subtitles. In Proceedings of the 10th International Conference on Language Resources and Evaluation (LREC 2016)

Red Book definitions are extracted from `indonesiandictionary.pdf` when the file is present. Only Indonesian headwords are indexed for Red Book matching; example sentences from the PDF are intentionally not stored.

## Implemented improvements

- Dictionary indexing plus cached sentence search to avoid loading the full corpus at startup.
- Proper search boundaries (word tokenization or regex matching) to reduce false positives.
- A configuration file for paths, keyboard shortcuts, and output limits.
- Improved sentence selection logic to avoid repeated sentences when multiple adjacent lines match.
- A command-line entry point and help text (`--help`) for easier launching.
- Cleaner CLI formatting with wrapped output, labeled sentence pairs, and normalized dictionary spacing.
- Bidirectional sentence lookup, so Indonesian and English queries return the opposite-language sentence.
- A capped GUI load-all action to avoid rendering unbounded result sets.
- A local SQLite sentence index with first-run progress feedback for faster repeated lookup.
- Red Book headword definitions from `indonesiandictionary.pdf`, indexed separately for whole-word Indonesian lookup.
- A Tkinter GUI redesign with responsive layout, clear colors, search history, and background worker threads.

## Future data bundle

SQLite is the recommended future single-file shipping format for myKamus data. A bundled `mykamus_data.sqlite` can hold dictionary entries, sentence pairs, Red Book headword definitions, source metadata, and schema versions in one portable artifact.

## Testing

Run the test suite with bytecode disabled to avoid dirtying tracked cache files:

```bash
QT_QPA_PLATFORM=offscreen PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover -s tests
```

## License and contact

The program is free to use for academic and non-commercial applications. If you wish to use it for something else, email gabrielcbarnett@gmail.com so we can discuss any needs you might have for updates or specific vocabulary requirements. A representative from your organization must make contact first.

If you find this program useful, feel free to email with your success story or suggested improvements.
