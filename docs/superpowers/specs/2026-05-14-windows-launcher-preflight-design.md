# Windows Launcher Preflight Design

## Goal

Make myKamus easier to start for Windows users who do not know how to use Python, while preserving the existing `python -m gui_app.app` command for Mac, Linux, and developer use.

## User Outcome

A Windows user should be able to double-click `Start myKamus.bat` from the project folder. If the machine is ready, the GUI opens. If the machine is not ready, the launcher explains the missing piece in plain language and offers the safest next action.

## Scope

This pass adds a Windows-only launcher and a testable Python preflight module. It does not build a packaged `.exe` or installer. Packaging remains a future improvement after the source-folder launch path is friendlier and stable.

## Architecture

The batch file stays thin. It finds a usable Python command, calls a Python preflight module, launches the GUI only after preflight succeeds, and keeps the terminal window open on failure.

The Python preflight module owns all substantive checks and prompts. This keeps the logic easier to test than batch scripting and avoids duplicating dependency knowledge in several places.

## Files

- Create `Start myKamus.bat` at the repository root.
- Create `gui_app/preflight.py`.
- Modify `README.md` to document the Windows beginner path near the top.
- Add tests in `tests/test_gui_preflight.py`.
- Keep `gui_app/app.py` runnable with `python -m gui_app.app` for existing users.

## Launcher Flow

`Start myKamus.bat` should:

1. Try to find Python using `py -3` first.
2. Fall back to `python` if `py -3` is unavailable.
3. If neither works, print a plain message telling the user to install Python from python.org and enable "Add Python to PATH".
4. Run `python -m gui_app.preflight`.
5. If preflight succeeds, run `python -m gui_app.app`.
6. If preflight fails, pause so the user can read the message.

The launcher should not make Mac or Linux users change their command.

## Preflight Dependency Check

`gui_app.preflight` should read or otherwise reflect the packages in `requirements.txt` and check that their importable modules are available:

- `keyboard`
- `pypdf`
- `PySide6`
- `pyperclip`

If one or more dependencies are missing, it should print a friendly message listing the missing packages and ask:

```text
Install them now using requirements.txt? [Y/N]
```

If the user answers yes, preflight should run:

```bash
python -m pip install -r requirements.txt
```

It should then re-check imports. If dependencies are still missing, preflight should fail with a clear message rather than launching the GUI.

If the user answers no, preflight should fail cleanly and tell the user they can install dependencies later with:

```bash
python -m pip install -r requirements.txt
```

## Data File Check

Preflight should check for required local data files:

- `en-id_dict.txt`
- `en-id_sentences.txt`
- `indonesiandictionary.pdf`

If any are missing, it should explain that the large data files may not have downloaded and that the project uses Git LFS for large files.

If Git is available, preflight should offer:

```text
Try downloading the data files with git lfs pull? [Y/N]
```

If the user answers yes, preflight should run:

```bash
git lfs pull
```

It should then re-check the required data files. If they are still missing, preflight should fail with a message explaining which files are still missing.

If Git is unavailable, preflight should explain that Git and Git LFS are needed to fetch the bundled data files from the source repository.

## User-Facing Tone

Messages should avoid Python jargon where possible. They should state:

- What myKamus needs.
- What is missing.
- What action the launcher can take.
- What to do if the automatic step fails.

The launcher should never silently install packages or run Git LFS. It should ask first.

## Error Handling

Preflight should return a successful exit code only when dependencies and data files are ready.

Failure cases should include:

- Python itself is not available, handled by the batch launcher.
- One or more Python dependencies are missing and the user declines installation.
- `pip install -r requirements.txt` fails.
- Dependencies remain missing after installation.
- Required data files are missing and the user declines `git lfs pull`.
- Git is unavailable when data files are missing.
- `git lfs pull` fails.
- Data files remain missing after `git lfs pull`.

In each case, the user should see a readable message and the launcher should pause.

## Testing

Tests should cover the Python preflight module with mocks rather than installing real packages or running Git:

- Detects installed and missing import modules.
- Prompts before dependency installation.
- Runs `python -m pip install -r requirements.txt` when approved.
- Fails cleanly when dependency installation is declined.
- Detects missing data files.
- Offers `git lfs pull` only when Git is available.
- Re-checks data files after `git lfs pull`.
- Returns failure when files remain missing.

The batch file should remain simple enough for manual smoke testing:

- Double-clicking it starts the GUI when everything is installed.
- Temporarily simulating missing Python or missing dependencies produces readable messages.

## Documentation

README should add a Windows beginner section near the top:

```text
On Windows, double-click Start myKamus.bat.
```

It should still document:

```bash
python -m gui_app.app
```

as the Mac, Linux, and developer launch command.

The README should also mention that a true `.exe` or installer is a future improvement, not part of this change.
