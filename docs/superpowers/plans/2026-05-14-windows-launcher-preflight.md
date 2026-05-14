# Windows Launcher Preflight Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Windows double-click launcher that checks Python packages and bundled data files before opening the myKamus GUI.

**Architecture:** Keep `Start myKamus.bat` thin: find Python, run `gui_app.preflight`, launch `gui_app.app`, and pause on failure. Put all dependency checks, prompts, `pip install`, Git availability, and `git lfs pull` behavior in `gui_app/preflight.py` so it can be covered by unit tests. Preserve `python -m gui_app.app` for Mac, Linux, and developer use.

**Tech Stack:** Windows batch, Python standard library (`importlib.util`, `pathlib`, `subprocess`, `shutil`, `sys`), `unittest`, `unittest.mock`.

---

## File Structure

- Create `gui_app/preflight.py`
  - Owns requirement parsing, dependency import checks, data-file checks, prompts, command execution, and `main()`.
- Create `tests/test_gui_preflight.py`
  - Covers preflight behavior with mocks and temporary directories.
- Create `Start myKamus.bat`
  - Windows launcher that finds Python, runs preflight, launches GUI, and pauses on failure.
- Modify `README.md`
  - Adds Windows beginner setup near the top and keeps the Python command for Mac, Linux, and developer users.
- Do not modify `gui_app/app.py` for this feature unless implementation reveals a direct import crash that prevents tests from importing the new preflight module.

## Implementation Notes

- Use ASCII text in the batch file and Python messages.
- User prompts must accept `y`, `yes`, `n`, and `no`, case-insensitively.
- Default answer for blank input should be `False` so the launcher never installs packages or runs Git LFS silently.
- Use `sys.executable` for `python -m pip install -r requirements.txt` from inside `gui_app.preflight`.
- Use `shutil.which("git")` to decide whether to offer `git lfs pull`.
- Run subprocess commands with `cwd=BASE_DIR`, where `BASE_DIR = Path(__file__).resolve().parent.parent`.

---

### Task 1: Create Preflight Detection Helpers

**Files:**
- Create: `gui_app/preflight.py`
- Create: `tests/test_gui_preflight.py`

- [ ] **Step 1: Write failing tests for requirement and data detection**

Create `tests/test_gui_preflight.py` with this content:

```python
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gui_app import preflight


class PreflightDetectionTests(unittest.TestCase):
    def test_read_requirements_ignores_blank_lines_and_comments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            requirements_path = Path(temp_dir) / "requirements.txt"
            requirements_path.write_text(
                "\n# comment\nkeyboard\npypdf\nPySide6\npyperclip\n",
                encoding="utf-8",
            )

            self.assertEqual(
                ["keyboard", "pypdf", "PySide6", "pyperclip"],
                preflight.read_requirements(requirements_path),
            )

    def test_missing_dependency_imports_maps_requirements_to_modules(self):
        def fake_find_spec(module_name):
            if module_name in {"keyboard", "pypdf"}:
                return object()
            return None

        with mock.patch.object(preflight.importlib.util, "find_spec", side_effect=fake_find_spec):
            missing = preflight.missing_dependency_imports(
                ["keyboard", "pypdf", "PySide6", "pyperclip"]
            )

        self.assertEqual(["PySide6", "pyperclip"], missing)

    def test_missing_data_files_reports_required_files_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            (base_dir / "en-id_dict.txt").write_text("dict", encoding="utf-8")

            missing = preflight.missing_data_files(base_dir)

        self.assertEqual(
            ["en-id_sentences.txt", "indonesiandictionary.pdf"],
            missing,
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail because the module does not exist**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: failure with `ImportError` or `cannot import name 'preflight'`.

- [ ] **Step 3: Create minimal detection implementation**

Create `gui_app/preflight.py` with this content:

```python
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
REQUIREMENTS_PATH = BASE_DIR / "requirements.txt"
REQUIRED_DATA_FILES = [
    "en-id_dict.txt",
    "en-id_sentences.txt",
    "indonesiandictionary.pdf",
]
REQUIREMENT_IMPORTS = {
    "keyboard": "keyboard",
    "pypdf": "pypdf",
    "PySide6": "PySide6",
    "pyperclip": "pyperclip",
}


def read_requirements(requirements_path=REQUIREMENTS_PATH):
    requirements = []
    for line in Path(requirements_path).read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            requirements.append(text)
    return requirements


def missing_dependency_imports(requirements):
    missing = []
    for requirement in requirements:
        module_name = REQUIREMENT_IMPORTS.get(requirement, requirement)
        if importlib.util.find_spec(module_name) is None:
            missing.append(requirement)
    return missing


def missing_data_files(base_dir=BASE_DIR):
    return [
        file_name
        for file_name in REQUIRED_DATA_FILES
        if not (Path(base_dir) / file_name).is_file()
    ]


def command_exists(command_name):
    return shutil.which(command_name) is not None


def run_command(command):
    return subprocess.run(command, cwd=BASE_DIR).returncode == 0


def prompt_yes_no(question, input_func=input, output_func=print):
    while True:
        answer = input_func(question + " [Y/N] ").strip().casefold()
        if answer in {"y", "yes"}:
            return True
        if answer in {"", "n", "no"}:
            return False
        output_func("Please answer Y or N.")


def main():
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run detection tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: `Ran 3 tests` and `OK`.

- [ ] **Step 5: Commit detection helpers**

Run:

```bash
git add gui_app/preflight.py tests/test_gui_preflight.py
git commit -m "feat: add GUI preflight detection helpers"
```

Expected: commit succeeds with only `gui_app/preflight.py` and `tests/test_gui_preflight.py` staged.

---

### Task 2: Add Dependency Install Flow

**Files:**
- Modify: `gui_app/preflight.py`
- Modify: `tests/test_gui_preflight.py`

- [ ] **Step 1: Add failing tests for dependency prompt and install behavior**

Append these tests to `PreflightDetectionTests` in `tests/test_gui_preflight.py`:

```python
    def test_ensure_dependencies_returns_true_when_none_missing(self):
        messages = []

        with mock.patch.object(preflight, "read_requirements", return_value=["PySide6"]), \
                mock.patch.object(preflight, "missing_dependency_imports", return_value=[]):
            result = preflight.ensure_dependencies(
                input_func=lambda _question: "n",
                output_func=messages.append,
            )

        self.assertTrue(result)
        self.assertEqual([], messages)

    def test_ensure_dependencies_installs_when_user_approves(self):
        messages = []
        install_calls = []
        missing_results = [["PySide6"], []]

        with mock.patch.object(preflight, "read_requirements", return_value=["PySide6"]), \
                mock.patch.object(
                    preflight,
                    "missing_dependency_imports",
                    side_effect=lambda _requirements: missing_results.pop(0),
                ), \
                mock.patch.object(
                    preflight,
                    "run_command",
                    side_effect=lambda command: install_calls.append(command) or True,
                ):
            result = preflight.ensure_dependencies(
                input_func=lambda _question: "y",
                output_func=messages.append,
            )

        self.assertTrue(result)
        self.assertEqual([[sys.executable, "-m", "pip", "install", "-r", str(preflight.REQUIREMENTS_PATH)]], install_calls)
        self.assertTrue(any("myKamus needs a few Python packages" in message for message in messages))

    def test_ensure_dependencies_fails_when_user_declines_install(self):
        messages = []

        with mock.patch.object(preflight, "read_requirements", return_value=["PySide6"]), \
                mock.patch.object(preflight, "missing_dependency_imports", return_value=["PySide6"]):
            result = preflight.ensure_dependencies(
                input_func=lambda _question: "n",
                output_func=messages.append,
            )

        self.assertFalse(result)
        self.assertTrue(any("python -m pip install -r requirements.txt" in message for message in messages))

    def test_ensure_dependencies_fails_when_install_command_fails(self):
        messages = []

        with mock.patch.object(preflight, "read_requirements", return_value=["PySide6"]), \
                mock.patch.object(preflight, "missing_dependency_imports", return_value=["PySide6"]), \
                mock.patch.object(preflight, "run_command", return_value=False):
            result = preflight.ensure_dependencies(
                input_func=lambda _question: "y",
                output_func=messages.append,
            )

        self.assertFalse(result)
        self.assertTrue(any("Dependency installation failed" in message for message in messages))
```

Add `import sys` near the top of `tests/test_gui_preflight.py`:

```python
import sys
```

- [ ] **Step 2: Run dependency-flow tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: failures with `AttributeError: module 'gui_app.preflight' has no attribute 'ensure_dependencies'`.

- [ ] **Step 3: Implement dependency install flow**

Add this function to `gui_app/preflight.py` after `prompt_yes_no`:

```python
def ensure_dependencies(input_func=input, output_func=print):
    requirements = read_requirements()
    missing = missing_dependency_imports(requirements)
    if not missing:
        return True

    output_func("myKamus needs a few Python packages before it can start:")
    for package_name in missing:
        output_func("- " + package_name)
    output_func("")

    if not prompt_yes_no(
        "Install them now using requirements.txt?",
        input_func=input_func,
        output_func=output_func,
    ):
        output_func(
            "You can install them later with: python -m pip install -r requirements.txt"
        )
        return False

    install_command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-r",
        str(REQUIREMENTS_PATH),
    ]
    if not run_command(install_command):
        output_func("Dependency installation failed.")
        return False

    still_missing = missing_dependency_imports(requirements)
    if still_missing:
        output_func("Some Python packages are still missing:")
        for package_name in still_missing:
            output_func("- " + package_name)
        return False

    return True
```

- [ ] **Step 4: Run dependency-flow tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: all tests in `test_gui_preflight.py` pass.

- [ ] **Step 5: Commit dependency install flow**

Run:

```bash
git add gui_app/preflight.py tests/test_gui_preflight.py
git commit -m "feat: prompt for missing GUI dependencies"
```

Expected: commit succeeds with only `gui_app/preflight.py` and `tests/test_gui_preflight.py` staged.

---

### Task 3: Add Data File and Git LFS Flow

**Files:**
- Modify: `gui_app/preflight.py`
- Modify: `tests/test_gui_preflight.py`

- [ ] **Step 1: Add failing tests for data-file flow**

Append these tests to `PreflightDetectionTests` in `tests/test_gui_preflight.py`:

```python
    def test_ensure_data_files_returns_true_when_files_exist(self):
        with mock.patch.object(preflight, "missing_data_files", return_value=[]):
            result = preflight.ensure_data_files(
                input_func=lambda _question: "n",
                output_func=lambda _message: None,
            )

        self.assertTrue(result)

    def test_ensure_data_files_fails_when_git_is_unavailable(self):
        messages = []

        with mock.patch.object(preflight, "missing_data_files", return_value=["en-id_sentences.txt"]), \
                mock.patch.object(preflight, "command_exists", return_value=False):
            result = preflight.ensure_data_files(
                input_func=lambda _question: "n",
                output_func=messages.append,
            )

        self.assertFalse(result)
        self.assertTrue(any("Git and Git LFS are needed" in message for message in messages))

    def test_ensure_data_files_runs_git_lfs_pull_when_user_approves(self):
        messages = []
        commands = []
        missing_results = [["en-id_sentences.txt"], []]

        with mock.patch.object(
            preflight,
            "missing_data_files",
            side_effect=lambda: missing_results.pop(0),
        ), \
                mock.patch.object(preflight, "command_exists", return_value=True), \
                mock.patch.object(
                    preflight,
                    "run_command",
                    side_effect=lambda command: commands.append(command) or True,
                ):
            result = preflight.ensure_data_files(
                input_func=lambda _question: "y",
                output_func=messages.append,
            )

        self.assertTrue(result)
        self.assertEqual([["git", "lfs", "pull"]], commands)
        self.assertTrue(any("large data files" in message for message in messages))

    def test_ensure_data_files_fails_when_files_remain_missing_after_git_lfs(self):
        messages = []

        with mock.patch.object(preflight, "missing_data_files", return_value=["en-id_sentences.txt"]), \
                mock.patch.object(preflight, "command_exists", return_value=True), \
                mock.patch.object(preflight, "run_command", return_value=True):
            result = preflight.ensure_data_files(
                input_func=lambda _question: "y",
                output_func=messages.append,
            )

        self.assertFalse(result)
        self.assertTrue(any("still missing" in message for message in messages))

    def test_ensure_data_files_fails_when_user_declines_git_lfs(self):
        messages = []

        with mock.patch.object(preflight, "missing_data_files", return_value=["en-id_sentences.txt"]), \
                mock.patch.object(preflight, "command_exists", return_value=True):
            result = preflight.ensure_data_files(
                input_func=lambda _question: "n",
                output_func=messages.append,
            )

        self.assertFalse(result)
        self.assertTrue(any("Cannot start until these data files are present" in message for message in messages))
```

- [ ] **Step 2: Run data-flow tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: failures with `AttributeError: module 'gui_app.preflight' has no attribute 'ensure_data_files'`.

- [ ] **Step 3: Implement data-file and Git LFS flow**

Add this function to `gui_app/preflight.py` after `ensure_dependencies`:

```python
def ensure_data_files(input_func=input, output_func=print):
    missing = missing_data_files()
    if not missing:
        return True

    output_func("myKamus needs these local data files before it can start:")
    for file_name in missing:
        output_func("- " + file_name)
    output_func("")
    output_func(
        "The large data files may not have downloaded. This project uses Git LFS for large files."
    )

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

- [ ] **Step 4: Run data-flow tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: all tests in `test_gui_preflight.py` pass.

- [ ] **Step 5: Commit data-file flow**

Run:

```bash
git add gui_app/preflight.py tests/test_gui_preflight.py
git commit -m "feat: check GUI data files before launch"
```

Expected: commit succeeds with only `gui_app/preflight.py` and `tests/test_gui_preflight.py` staged.

---

### Task 4: Wire Preflight Main

**Files:**
- Modify: `gui_app/preflight.py`
- Modify: `tests/test_gui_preflight.py`

- [ ] **Step 1: Add failing tests for `main()` exit behavior**

Append these tests to `PreflightDetectionTests` in `tests/test_gui_preflight.py`:

```python
    def test_main_returns_zero_when_dependencies_and_data_are_ready(self):
        with mock.patch.object(preflight, "ensure_dependencies", return_value=True), \
                mock.patch.object(preflight, "ensure_data_files", return_value=True):
            result = preflight.main(
                input_func=lambda _question: "n",
                output_func=lambda _message: None,
            )

        self.assertEqual(0, result)

    def test_main_returns_one_when_dependencies_are_not_ready(self):
        with mock.patch.object(preflight, "ensure_dependencies", return_value=False), \
                mock.patch.object(preflight, "ensure_data_files", return_value=True):
            result = preflight.main(
                input_func=lambda _question: "n",
                output_func=lambda _message: None,
            )

        self.assertEqual(1, result)

    def test_main_returns_one_when_data_files_are_not_ready(self):
        with mock.patch.object(preflight, "ensure_dependencies", return_value=True), \
                mock.patch.object(preflight, "ensure_data_files", return_value=False):
            result = preflight.main(
                input_func=lambda _question: "n",
                output_func=lambda _message: None,
            )

        self.assertEqual(1, result)
```

- [ ] **Step 2: Run main tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: at least one failure because `main()` currently returns `0` without checking dependencies or data files.

- [ ] **Step 3: Implement `main()` orchestration**

Replace the current `main()` in `gui_app/preflight.py` with:

```python
def main(input_func=input, output_func=print):
    if not ensure_dependencies(input_func=input_func, output_func=output_func):
        return 1
    if not ensure_data_files(input_func=input_func, output_func=output_func):
        return 1
    return 0
```

Leave the module entry point as:

```python
if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run preflight tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: all tests in `test_gui_preflight.py` pass.

- [ ] **Step 5: Commit preflight orchestration**

Run:

```bash
git add gui_app/preflight.py tests/test_gui_preflight.py
git commit -m "feat: wire GUI preflight checks"
```

Expected: commit succeeds with only `gui_app/preflight.py` and `tests/test_gui_preflight.py` staged.

---

### Task 5: Add Windows Batch Launcher

**Files:**
- Create: `Start myKamus.bat`

- [ ] **Step 1: Create the launcher**

Create `Start myKamus.bat` with this content:

```bat
@echo off
setlocal
cd /d "%~dp0"

set "PYTHON_CMD="

py -3 --version >nul 2>nul
if %ERRORLEVEL%==0 (
    set "PYTHON_CMD=py -3"
) else (
    python --version >nul 2>nul
    if %ERRORLEVEL%==0 (
        set "PYTHON_CMD=python"
    )
)

if "%PYTHON_CMD%"=="" (
    echo myKamus needs Python before it can start.
    echo Install Python from https://www.python.org/downloads/
    echo During installation, tick "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

%PYTHON_CMD% -m gui_app.preflight
if not %ERRORLEVEL%==0 (
    echo.
    echo myKamus could not finish setup.
    pause
    exit /b 1
)

%PYTHON_CMD% -m gui_app.app
if not %ERRORLEVEL%==0 (
    echo.
    echo myKamus closed with an error.
    pause
    exit /b 1
)

endlocal
```

- [ ] **Step 2: Manually smoke-check batch syntax without launching the GUI**

Run:

```bash
cmd /c "Start myKamus.bat"
```

Expected: if dependencies and data files are present, it opens the GUI. Close the GUI after confirming it starts. If a local environment prevents GUI launch, record the exact error and verify the launcher reached `python -m gui_app.app` after preflight.

- [ ] **Step 3: Commit launcher**

Run:

```bash
git add "Start myKamus.bat"
git commit -m "feat: add Windows GUI launcher"
```

Expected: commit succeeds with only `Start myKamus.bat` staged.

---

### Task 6: Update README

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README Windows instructions**

In `README.md`, replace the `## Prerequisites` section through the first dependency install code block with:

````markdown
## Windows beginner start

On Windows, double-click:

```text
Start myKamus.bat
```

The launcher checks whether Python packages and bundled data files are ready. If packages are missing, it asks before running `python -m pip install -r requirements.txt`. If large data files are missing, it explains Git LFS and can offer to run `git lfs pull`.

This is still a source-folder launcher, not a packaged `.exe`. A true Windows app or installer is a future improvement.

## Prerequisites for Mac, Linux, and development

- Python 3.x
- Git LFS for the bundled dictionary and sentence corpus
- Python dependencies in `requirements.txt`

Install Git LFS and Python dependencies:

```bash
git lfs install
git lfs pull
python -m pip install -r requirements.txt
```
````

Keep the existing Git LFS troubleshooting paragraph after this block.

- [ ] **Step 2: Run a README search to verify both launch paths are documented**

Run:

```bash
Select-String -Path README.md -Pattern "Start myKamus.bat|python -m gui_app.app"
```

Expected: output includes one line for `Start myKamus.bat` and one line for `python -m gui_app.app`.

- [ ] **Step 3: Commit README update**

Run:

```bash
git add README.md
git commit -m "docs: document Windows launcher"
```

Expected: commit succeeds with only `README.md` staged.

---

### Task 7: Final Verification

**Files:**
- Verify: all changed files

- [ ] **Step 1: Run full unit test suite**

Run:

```bash
python -B -m unittest discover -s tests
```

Expected: all tests pass. Existing environment may report one skipped Qt dependency test when PySide6 is installed.

- [ ] **Step 2: Run preflight directly**

Run:

```bash
python -m gui_app.preflight
```

Expected: exit code `0` when the current environment has dependencies and data files. If the command prompts, answer `n` and record which check failed.

- [ ] **Step 3: Run GUI command directly**

Run:

```bash
python -m gui_app.app
```

Expected: GUI launches as before. Close the GUI after smoke-checking the window title.

- [ ] **Step 4: Check git status**

Run:

```bash
git status --short
```

Expected: no unstaged files from this implementation plan. If unrelated pre-existing files remain modified, identify them separately and do not revert them.

- [ ] **Step 5: Request code review**

Use `superpowers:requesting-code-review` on the implementation range. Review should check:

- Preflight does not install or run Git LFS without consent.
- Batch launcher keeps Mac/Linux command untouched.
- Tests cover missing dependency and missing data-file flows.
- README points beginners at the launcher and still documents `python -m gui_app.app`.

---

## Self-Review

Spec coverage:

- Windows double-click launcher: Task 5.
- Python preflight module: Tasks 1 through 4.
- Dependency prompts and `pip install`: Task 2.
- Data-file checks and optional `git lfs pull`: Task 3.
- Exit codes: Task 4.
- README updates: Task 6.
- Verification and review: Task 7.

Placeholder scan:

- No placeholder markers or unspecified code steps are intentionally present.

Type and name consistency:

- `read_requirements`, `missing_dependency_imports`, `missing_data_files`, `command_exists`, `run_command`, `prompt_yes_no`, `ensure_dependencies`, `ensure_data_files`, and `main` are introduced before later tasks use them.
