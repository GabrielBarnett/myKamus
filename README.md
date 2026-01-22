# myKamus

myKamus is an open source, clipboard-driven translation tool for Indonesian that provides English translations plus example sentences from a large bilingual corpus.

It uses open source bitext corpora to provide access to over 50 million example sentences and word translations for Indonesian ↔ English.

## Features

- Watches your clipboard for Indonesian words/phrases and displays translations automatically.
- Shows example sentences to provide context.
- Supports manual search (Ctrl+S) and bulk sentence loading (L).

## Prerequisites

- Python 3.x
- `pyperclip`
- `keyboard`

Install dependencies:

```bash
pip install pyperclip keyboard
```

## Usage

1. Open `myKamus_initialise.py` in your IDE or run it from the terminal.
2. Highlight an Indonesian word or short phrase and copy it (`Ctrl+C`).
3. Watch translations appear in real time. If no results appear, try shorter substrings and ensure there are no leading/trailing spaces.
4. To search for a specific word, focus the console, press `Ctrl+S`, and enter your term.
5. To load all example sentences, press `L`. Note: this may return very large results for common words.

## Data Sources

Bitext corpus for sentences sourced from:

P. Lison and J. Tiedemann, 2016, OpenSubtitles2016: Extracting Large Parallel Corpora from Movie and TV Subtitles. In Proceedings of the 10th International Conference on Language Resources and Evaluation (LREC 2016)

## Future fixes and known improvements

These are recommended follow-ups based on identified issues and performance considerations:

- Add indexing or caching to avoid scanning the entire dictionary and sentence corpus for each query.
- Provide a proper search boundary (e.g., word tokenization or regex matching) to reduce false positives.
- Add a configuration file for paths, keyboard shortcuts, and output limits.
- Improve sentence selection logic to avoid repeated sentences when multiple adjacent lines match.
- Add a command-line entry point and help text (`--help`) for easier launching.

## License and contact

The program is free to use for academic and non-commercial applications. If you wish to use it for something else, email gabrielcbarnett@gmail.com so we can discuss any needs you might have for updates or specific vocabulary requirements. A representative from your organization must make contact first.

If you find this program useful, feel free to email with your success story or suggested improvements.
