# Portable Zip With Local Vendor Dependencies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a GitHub-friendly portable myKamus zip flow that installs dependencies into local `vendor/`, remembers setup choices, supports external corporate data folders, and keeps the first package GUI-first.

**Architecture:** Extend `gui_app.preflight` into the single setup coordinator: it loads/saves `.mykamus_cache/setup.json`, prepends `vendor/` to `sys.path`, installs packages into `vendor/` using wheels or normal pip, and resolves required data files through app-folder, remembered folder, user-provided folder, then Git LFS fallback. Add a separate `scripts/build_portable_zip.py` that creates a user-only zip and records package metadata without bundling large data files. Keep source layout mostly as-is and defer installer/source-package cleanup.

**Tech Stack:** Python standard library (`argparse`, `json`, `pathlib`, `shutil`, `subprocess`, `sys`, `zipfile`), Windows batch, `unittest`, `unittest.mock`.

---

## File Structure

- Modify `gui_app/preflight.py`
  - Add setup-state helpers, vendor path support, setup-method selection, local install commands, Python-version warning, corporate data-folder flow, and config path updates.
- Modify `tests/test_gui_preflight.py`
  - Add focused tests for setup state, vendor dependency install flow, data folder resolution, and metadata/version warnings.
- Create `scripts/build_portable_zip.py`
  - Build the user-only portable zip and optional wheels.
- Create `tests/test_build_portable_zip.py`
  - Verify zip contents, data exclusions, metadata, and optional wheel download behavior.
- Create `README_FIRST.txt`
  - User-facing short instructions for the portable zip.
- Create `docs/portable-distribution.md`
  - Maintainer-facing packaging instructions.
- Check `Start myKamus.bat`
  - Keep it thin; it should continue to run `python -m gui_app.preflight` before `python -m gui_app.app`.
- Do not move source files into a `src/` package layout in this plan.
- Do not add a bundled Python, installer, custom `.exe`, or CLI launcher in this plan.

---

### Task 1: Setup State, Vendor Path, and Metadata Helpers

**Files:**
- Modify: `gui_app/preflight.py`
- Modify: `tests/test_gui_preflight.py`

- [ ] **Step 1: Write failing tests for setup state and vendor path**

Append these tests to `tests/test_gui_preflight.py`:

```python
    def test_setup_state_round_trips_json_in_cache_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            state = {
                "dependency_method": "wheels",
                "data_folder": "X:/myKamus-data",
            }

            preflight.save_setup_state(state, base_dir=base_dir)

            self.assertEqual(state, preflight.load_setup_state(base_dir=base_dir))
            self.assertTrue((base_dir / ".mykamus_cache" / "setup.json").is_file())

    def test_load_setup_state_returns_empty_dict_when_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual({}, preflight.load_setup_state(base_dir=Path(temp_dir)))

    def test_vendor_path_is_inserted_at_front_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vendor_path = Path(temp_dir) / "vendor"
            python_path = ["existing"]

            preflight.prepend_vendor_path(vendor_path=vendor_path, python_path=python_path)
            preflight.prepend_vendor_path(vendor_path=vendor_path, python_path=python_path)

        self.assertEqual([str(vendor_path), "existing"], python_path)

    def test_read_package_metadata_returns_empty_dict_when_missing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertEqual({}, preflight.read_package_metadata(base_dir=Path(temp_dir)))
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: failures with missing `save_setup_state`, `load_setup_state`, `prepend_vendor_path`, and `read_package_metadata`.

- [ ] **Step 3: Implement setup state, vendor path, and metadata helpers**

Add these constants after `REQUIREMENTS_PATH` in `gui_app/preflight.py`:

```python
SETUP_STATE_PATH = BASE_DIR / ".mykamus_cache" / "setup.json"
PACKAGE_METADATA_PATH = BASE_DIR / "portable-package.json"
VENDOR_PATH = BASE_DIR / "vendor"
```

Add `import json` near the top of `gui_app/preflight.py`.

Add these functions before `read_requirements()`:

```python
def load_setup_state(base_dir=BASE_DIR):
    state_path = Path(base_dir) / ".mykamus_cache" / "setup.json"
    if not state_path.is_file():
        return {}
    with state_path.open(encoding="utf-8") as state_file:
        return json.load(state_file)


def save_setup_state(state, base_dir=BASE_DIR):
    state_path = Path(base_dir) / ".mykamus_cache" / "setup.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("w", encoding="utf-8") as state_file:
        json.dump(state, state_file, indent=2)
        state_file.write("\n")


def prepend_vendor_path(vendor_path=VENDOR_PATH, python_path=None):
    if python_path is None:
        python_path = sys.path
    text_path = str(Path(vendor_path))
    if text_path in python_path:
        python_path.remove(text_path)
    python_path.insert(0, text_path)


def read_package_metadata(base_dir=BASE_DIR):
    metadata_path = Path(base_dir) / "portable-package.json"
    if not metadata_path.is_file():
        return {}
    with metadata_path.open(encoding="utf-8") as metadata_file:
        return json.load(metadata_file)
```

- [ ] **Step 4: Run setup helper tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: all `test_gui_preflight.py` tests pass.

- [ ] **Step 5: Commit setup helper work**

Run:

```bash
git add gui_app/preflight.py tests/test_gui_preflight.py
git commit -m "feat: add portable setup state helpers"
```

Expected: commit includes only `gui_app/preflight.py` and `tests/test_gui_preflight.py`.

---

### Task 2: Install Dependencies Into Local Vendor Folder

**Files:**
- Modify: `gui_app/preflight.py`
- Modify: `tests/test_gui_preflight.py`

- [ ] **Step 1: Write failing tests for setup method selection and vendor install commands**

Append these tests to `tests/test_gui_preflight.py`:

```python
    def test_choose_dependency_method_uses_remembered_choice(self):
        state = {"dependency_method": "normal-pip"}

        choice = preflight.choose_dependency_method(
            state,
            input_func=lambda _question: "1",
            output_func=lambda _message: None,
        )

        self.assertEqual("normal-pip", choice)

    def test_choose_dependency_method_asks_once_and_saves_choice(self):
        state = {}
        messages = []

        choice = preflight.choose_dependency_method(
            state,
            input_func=lambda _question: "1",
            output_func=messages.append,
        )

        self.assertEqual("wheels", choice)
        self.assertEqual("wheels", state["dependency_method"])
        self.assertTrue(any("How should myKamus set up Python packages?" in message for message in messages))

    def test_install_dependencies_with_wheels_targets_vendor(self):
        commands = []

        result = preflight.install_dependencies(
            "wheels",
            run_command_func=lambda command: commands.append(command) or True,
        )

        self.assertTrue(result)
        self.assertEqual(
            [[
                sys.executable,
                "-m",
                "pip",
                "install",
                "--target",
                str(preflight.VENDOR_PATH),
                "--no-index",
                "--find-links",
                str(preflight.BASE_DIR / "wheels"),
                "-r",
                str(preflight.REQUIREMENTS_PATH),
            ]],
            commands,
        )

    def test_install_dependencies_with_normal_pip_targets_vendor(self):
        commands = []

        result = preflight.install_dependencies(
            "normal-pip",
            run_command_func=lambda command: commands.append(command) or True,
        )

        self.assertTrue(result)
        self.assertEqual(
            [[
                sys.executable,
                "-m",
                "pip",
                "install",
                "--target",
                str(preflight.VENDOR_PATH),
                "-r",
                str(preflight.REQUIREMENTS_PATH),
            ]],
            commands,
        )
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: failures with missing `choose_dependency_method` and `install_dependencies`.

- [ ] **Step 3: Implement setup-method and vendor install helpers**

Add these functions after `prompt_yes_no()`:

```python
def choose_dependency_method(state, input_func=input, output_func=print):
    remembered = state.get("dependency_method")
    if remembered in {"wheels", "normal-pip"}:
        return remembered

    output_func("How should myKamus set up Python packages?")
    output_func("1. Use local wheels included with myKamus")
    output_func("2. Use normal pip, such as the corporate pip mirror")
    while True:
        answer = input_func("Choose 1 or 2: ").strip()
        if answer == "1":
            state["dependency_method"] = "wheels"
            return "wheels"
        if answer == "2":
            state["dependency_method"] = "normal-pip"
            return "normal-pip"
        output_func("Please choose 1 or 2.")


def install_dependencies(method, run_command_func=run_command):
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--target",
        str(VENDOR_PATH),
    ]
    if method == "wheels":
        command.extend(["--no-index", "--find-links", str(BASE_DIR / "wheels")])
    command.extend(["-r", str(REQUIREMENTS_PATH)])
    return run_command_func(command)
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: all `test_gui_preflight.py` tests pass.

- [ ] **Step 5: Commit vendor install helpers**

Run:

```bash
git add gui_app/preflight.py tests/test_gui_preflight.py
git commit -m "feat: install GUI dependencies into vendor"
```

Expected: commit includes only `gui_app/preflight.py` and `tests/test_gui_preflight.py`.

---

### Task 3: Rework Dependency Preflight Around Vendor and Fallbacks

**Files:**
- Modify: `gui_app/preflight.py`
- Modify: `tests/test_gui_preflight.py`

- [ ] **Step 1: Replace outdated dependency tests with vendor-first behavior tests**

In `tests/test_gui_preflight.py`, replace tests that expect `ensure_dependencies()` to check imports before prompting or to run `python -m pip install -r requirements.txt` without `--target vendor`.

Add these tests:

```python
    def test_ensure_dependencies_chooses_method_before_import_check(self):
        calls = []
        state = {}

        with mock.patch.object(preflight, "load_setup_state", return_value=state), \
                mock.patch.object(preflight, "save_setup_state") as save_setup_state, \
                mock.patch.object(preflight, "install_dependencies", side_effect=lambda method: calls.append(("install", method)) or True), \
                mock.patch.object(preflight, "prepend_vendor_path", side_effect=lambda: calls.append(("vendor", None))), \
                mock.patch.object(preflight, "read_requirements", return_value=["PySide6"]), \
                mock.patch.object(preflight, "missing_dependency_imports", side_effect=lambda _requirements: calls.append(("imports", None)) or []):
            result = preflight.ensure_dependencies(
                input_func=lambda _question: "1",
                output_func=lambda _message: None,
            )

        self.assertTrue(result)
        self.assertEqual([("install", "wheels"), ("vendor", None), ("imports", None)], calls)
        save_setup_state.assert_called_once_with(state)

    def test_ensure_dependencies_offers_other_method_when_first_method_fails_imports(self):
        state = {"dependency_method": "wheels"}
        messages = []
        installs = []

        with mock.patch.object(preflight, "load_setup_state", return_value=state), \
                mock.patch.object(preflight, "save_setup_state"), \
                mock.patch.object(preflight, "install_dependencies", side_effect=lambda method: installs.append(method) or True), \
                mock.patch.object(preflight, "prepend_vendor_path"), \
                mock.patch.object(preflight, "read_requirements", return_value=["PySide6"]), \
                mock.patch.object(preflight, "missing_dependency_imports", side_effect=[["PySide6"], []]):
            result = preflight.ensure_dependencies(
                input_func=lambda _question: "y",
                output_func=messages.append,
            )

        self.assertTrue(result)
        self.assertEqual(["wheels", "normal-pip"], installs)
        self.assertTrue(any("pip may have installed packages somewhere this Python cannot see" in message for message in messages))
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: failures because `ensure_dependencies()` still uses the old missing-first flow.

- [ ] **Step 3: Implement vendor-first `ensure_dependencies()`**

Replace `ensure_dependencies()` in `gui_app/preflight.py` with:

```python
def other_dependency_method(method):
    return "normal-pip" if method == "wheels" else "wheels"


def ensure_dependencies(input_func=input, output_func=print):
    state = load_setup_state()
    method = choose_dependency_method(
        state,
        input_func=input_func,
        output_func=output_func,
    )
    save_setup_state(state)

    if not install_dependencies(method):
        output_func("Dependency installation failed.")
        return False

    prepend_vendor_path()
    requirements = read_requirements()
    missing = missing_dependency_imports(requirements)
    if not missing:
        return True

    output_func("Some Python packages are still missing:")
    for package_name in missing:
        output_func("- " + package_name)
    output_func("pip may have installed packages somewhere this Python cannot see.")

    fallback_method = other_dependency_method(method)
    if not prompt_yes_no(
        "Try the other setup method?",
        input_func=input_func,
        output_func=output_func,
    ):
        return False

    state["dependency_method"] = fallback_method
    save_setup_state(state)
    if not install_dependencies(fallback_method):
        output_func("Dependency installation failed.")
        return False

    prepend_vendor_path()
    still_missing = missing_dependency_imports(requirements)
    if still_missing:
        output_func("Some Python packages are still missing:")
        for package_name in still_missing:
            output_func("- " + package_name)
        return False

    return True
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: all `test_gui_preflight.py` tests pass.

- [ ] **Step 5: Commit dependency preflight rework**

Run:

```bash
git add gui_app/preflight.py tests/test_gui_preflight.py
git commit -m "feat: use vendor dependency setup in preflight"
```

Expected: commit includes only `gui_app/preflight.py` and `tests/test_gui_preflight.py`.

---

### Task 4: Python Version Metadata Warning

**Files:**
- Modify: `gui_app/preflight.py`
- Modify: `tests/test_gui_preflight.py`

- [ ] **Step 1: Write failing tests for Python version warning**

Append this test:

```python
    def test_warn_python_version_mismatch_returns_true_when_user_continues(self):
        messages = []
        metadata = {"python_version": "3.11"}

        result = preflight.warn_python_version_mismatch(
            metadata,
            current_version="3.12",
            input_func=lambda _question: "y",
            output_func=messages.append,
        )

        self.assertTrue(result)
        self.assertTrue(any("prepared with Python 3.11" in message for message in messages))
        self.assertTrue(any("running Python 3.12" in message for message in messages))
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: failure with missing `warn_python_version_mismatch`.

- [ ] **Step 3: Implement Python version warning helper and call it from `main()`**

Add:

```python
def current_python_version():
    return str(sys.version_info.major) + "." + str(sys.version_info.minor)


def warn_python_version_mismatch(metadata, current_version=None, input_func=input, output_func=print):
    expected = metadata.get("python_version")
    if not expected:
        return True
    if current_version is None:
        current_version = current_python_version()
    if current_version == expected:
        return True
    output_func("This myKamus package was prepared with Python " + expected + ".")
    output_func("You are running Python " + current_version + ".")
    output_func("Some bundled wheels may not load correctly.")
    return prompt_yes_no(
        "Continue and use fallback setup options if needed?",
        input_func=input_func,
        output_func=output_func,
    )
```

Update `main()` before `ensure_dependencies()`:

```python
    metadata = read_package_metadata()
    if not warn_python_version_mismatch(metadata, input_func=input_func, output_func=output_func):
        return 1
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: all `test_gui_preflight.py` tests pass.

- [ ] **Step 5: Commit Python version warning**

Run:

```bash
git add gui_app/preflight.py tests/test_gui_preflight.py
git commit -m "feat: warn on portable Python version mismatch"
```

Expected: commit includes only `gui_app/preflight.py` and `tests/test_gui_preflight.py`.

---

### Task 5: Corporate Data Folder Resolution and Config Update

**Files:**
- Modify: `gui_app/preflight.py`
- Modify: `tests/test_gui_preflight.py`

- [ ] **Step 1: Write failing tests for remembered and user-provided data folders**

Append these tests:

```python
    def test_missing_data_files_uses_external_data_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            data_dir.mkdir()
            for file_name in preflight.REQUIRED_DATA_FILES:
                (data_dir / file_name).write_text("data", encoding="utf-8")

            self.assertEqual([], preflight.missing_data_files(data_dir))

    def test_choose_data_folder_remembers_valid_user_folder(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir) / "data"
            data_dir.mkdir()
            for file_name in preflight.REQUIRED_DATA_FILES:
                (data_dir / file_name).write_text("data", encoding="utf-8")
            state = {}

            chosen = preflight.choose_data_folder(
                state,
                input_func=lambda _question: str(data_dir),
                output_func=lambda _message: None,
            )

        self.assertEqual(str(data_dir), chosen)
        self.assertEqual(str(data_dir), state["data_folder"])

    def test_apply_data_folder_to_config_writes_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            data_dir = base_dir / "data"
            data_dir.mkdir()

            preflight.apply_data_folder_to_config(data_dir, base_dir=base_dir)

            config = json.loads((base_dir / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(str(data_dir / "en-id_dict.txt"), config["dictionary_path"])
        self.assertEqual(str(data_dir / "en-id_sentences.txt"), config["sentences_path"])
        self.assertEqual(str(data_dir / "indonesiandictionary.pdf"), config["red_book_pdf_path"])
```

Add `import json` at the top of `tests/test_gui_preflight.py`.

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: failures with missing `choose_data_folder` and `apply_data_folder_to_config`.

- [ ] **Step 3: Implement data-folder selection and config update helpers**

Add:

```python
def choose_data_folder(state, input_func=input, output_func=print):
    remembered = state.get("data_folder")
    if remembered and not missing_data_files(remembered):
        return remembered

    output_func("Please enter the folder path where myKamus data files are stored:")
    for file_name in REQUIRED_DATA_FILES:
        output_func("- " + file_name)
    folder = input_func("Data folder path: ").strip().strip('"')
    if not folder:
        return None
    if missing_data_files(folder):
        output_func("That folder does not contain all required myKamus data files.")
        return None
    state["data_folder"] = folder
    return folder


def apply_data_folder_to_config(data_folder, base_dir=BASE_DIR):
    config_path = Path(base_dir) / "config.json"
    config = {}
    if config_path.is_file():
        with config_path.open(encoding="utf-8") as config_file:
            config = json.load(config_file)
    folder = Path(data_folder)
    config["dictionary_path"] = str(folder / "en-id_dict.txt")
    config["sentences_path"] = str(folder / "en-id_sentences.txt")
    config["red_book_pdf_path"] = str(folder / "indonesiandictionary.pdf")
    with config_path.open("w", encoding="utf-8") as config_file:
        json.dump(config, config_file, indent=2)
        config_file.write("\n")
```

- [ ] **Step 4: Rework `ensure_data_files()` to use layered data lookup**

Modify `ensure_data_files()` so its order is:

```python
    if not missing_data_files(BASE_DIR):
        return True
    state = load_setup_state()
    data_folder = state.get("data_folder")
    if data_folder and not missing_data_files(data_folder):
        apply_data_folder_to_config(data_folder)
        return True
    if prompt_yes_no("Do you already have the myKamus data files in a corporate network folder?", input_func=input_func, output_func=output_func):
        chosen = choose_data_folder(state, input_func=input_func, output_func=output_func)
        if chosen:
            save_setup_state(state)
            apply_data_folder_to_config(chosen)
            return True
```

Keep the existing Git LFS fallback after this corporate-folder path.

- [ ] **Step 5: Run tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: all `test_gui_preflight.py` tests pass.

- [ ] **Step 6: Commit data-folder resolution**

Run:

```bash
git add gui_app/preflight.py tests/test_gui_preflight.py
git commit -m "feat: support corporate data folder setup"
```

Expected: commit includes only `gui_app/preflight.py` and `tests/test_gui_preflight.py`.

---

### Task 6: Portable Zip Build Script

**Files:**
- Create: `scripts/build_portable_zip.py`
- Create: `tests/test_build_portable_zip.py`

- [ ] **Step 1: Write failing build-script tests**

Create `tests/test_build_portable_zip.py`:

```python
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from scripts import build_portable_zip


class BuildPortableZipTests(unittest.TestCase):
    def test_runtime_files_exclude_large_data_and_dev_folders(self):
        names = build_portable_zip.runtime_file_names()

        self.assertIn("Start myKamus.bat", names)
        self.assertIn("gui_app", names)
        self.assertNotIn("en-id_sentences.txt", names)
        self.assertNotIn("tests", names)
        self.assertNotIn("docs/superpowers", names)

    def test_build_zip_writes_metadata_and_excludes_large_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir) / "repo"
            repo.mkdir()
            for path in [
                "Start myKamus.bat",
                "README_FIRST.txt",
                "requirements.txt",
                "clean_text.py",
                "config.example.json",
                "red_book_index.py",
                "search_functions.py",
                "search_index.py",
                "en-id_sentences.txt",
            ]:
                (repo / path).write_text("x", encoding="utf-8")
            (repo / "gui_app").mkdir()
            (repo / "gui_app" / "__init__.py").write_text("", encoding="utf-8")
            (repo / "gui_app" / "app.py").write_text("", encoding="utf-8")
            output = Path(temp_dir) / "out"

            zip_path = build_portable_zip.build_zip(repo, output, download_wheels=False)

            with zipfile.ZipFile(zip_path) as archive:
                names = set(archive.namelist())
        self.assertIn("myKamus/portable-package.json", names)
        self.assertIn("myKamus/Start myKamus.bat", names)
        self.assertNotIn("myKamus/en-id_sentences.txt", names)

    def test_download_wheels_is_opt_in(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)

            with mock.patch.object(build_portable_zip, "run_command", return_value=True) as run_command:
                build_portable_zip.prepare_wheels(repo, download_wheels=False)
                run_command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_build_portable_zip.py
```

Expected: import failure because `scripts/build_portable_zip.py` does not exist.

- [ ] **Step 3: Implement build script**

Create `scripts/build_portable_zip.py`:

```python
import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path


PACKAGE_ROOT_NAME = "myKamus"
LARGE_DATA_FILES = {
    "en-id_dict.txt",
    "en-id_sentences.txt",
    "indonesiandictionary.pdf",
}


def runtime_file_names():
    return [
        "Start myKamus.bat",
        "README_FIRST.txt",
        "requirements.txt",
        "wheels",
        "gui_app",
        "clean_text.py",
        "config.example.json",
        "red_book_index.py",
        "search_functions.py",
        "search_index.py",
    ]


def run_command(command, cwd):
    return subprocess.run(command, cwd=cwd).returncode == 0


def prepare_wheels(repo_root, download_wheels=False):
    if not download_wheels:
        return True
    wheels_dir = Path(repo_root) / "wheels"
    wheels_dir.mkdir(exist_ok=True)
    return run_command(
        [sys.executable, "-m", "pip", "download", "-r", "requirements.txt", "-d", str(wheels_dir)],
        cwd=repo_root,
    )


def copy_runtime_files(repo_root, staging_root):
    package_root = Path(staging_root) / PACKAGE_ROOT_NAME
    package_root.mkdir(parents=True, exist_ok=True)
    for name in runtime_file_names():
        source = Path(repo_root) / name
        if not source.exists():
            continue
        destination = package_root / name
        if source.is_dir():
            shutil.copytree(source, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        else:
            shutil.copy2(source, destination)
    return package_root


def write_metadata(package_root):
    metadata = {
        "python_version": str(sys.version_info.major) + "." + str(sys.version_info.minor),
        "package": "myKamus-portable",
    }
    with (Path(package_root) / "portable-package.json").open("w", encoding="utf-8") as metadata_file:
        json.dump(metadata, metadata_file, indent=2)
        metadata_file.write("\n")


def make_zip(package_root, output_dir):
    zip_path = Path(output_dir) / "myKamus-portable.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in Path(package_root).rglob("*"):
            if path.is_file():
                archive.write(path, path.relative_to(Path(package_root).parent))
    return zip_path


def build_zip(repo_root, output_dir, download_wheels=False):
    repo_root = Path(repo_root)
    output_dir = Path(output_dir)
    staging_root = output_dir / "myKamus-portable"
    if staging_root.exists():
        shutil.rmtree(staging_root)
    output_dir.mkdir(parents=True, exist_ok=True)
    if not prepare_wheels(repo_root, download_wheels=download_wheels):
        raise RuntimeError("Wheel download failed.")
    package_root = copy_runtime_files(repo_root, staging_root)
    write_metadata(package_root)
    return make_zip(package_root, output_dir)


def parse_args():
    parser = argparse.ArgumentParser(description="Build the myKamus portable zip.")
    parser.add_argument("--repo-root", default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--output-dir", default="dist")
    parser.add_argument("--download-wheels", action="store_true")
    return parser.parse_args()


def main():
    args = parse_args()
    zip_path = build_zip(args.repo_root, args.output_dir, download_wheels=args.download_wheels)
    print("Built " + str(zip_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run build-script tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_build_portable_zip.py
```

Expected: all `test_build_portable_zip.py` tests pass.

- [ ] **Step 5: Commit build script**

Run:

```bash
git add scripts/build_portable_zip.py tests/test_build_portable_zip.py
git commit -m "feat: add portable zip build script"
```

Expected: commit includes only build script and build tests.

---

### Task 7: User and Maintainer Documentation

**Files:**
- Create: `README_FIRST.txt`
- Create: `docs/portable-distribution.md`

- [ ] **Step 1: Create user README**

Create `README_FIRST.txt`:

```text
myKamus Portable Start Guide

1. Extract the myKamus zip to a folder you can write to.
2. Double-click Start myKamus.bat.
3. When asked how to set up packages, choose local wheels if your zip includes a wheels folder.
4. If asked for data files, enter the corporate network folder that contains:
   - en-id_dict.txt
   - en-id_sentences.txt
   - indonesiandictionary.pdf
5. Leave the first launch open while myKamus builds its search indexes.

If setup fails, contact your internal myKamus support person and include the message shown in the terminal window.
```

- [ ] **Step 2: Create maintainer docs**

Create `docs/portable-distribution.md`:

````markdown
# Portable Distribution

The portable zip is for Windows users on a corporate network. It uses corporate-approved installed Python and does not bundle Python or a custom executable.

## Build

```bash
python scripts/build_portable_zip.py
```

To download wheels on a build machine that can access the configured pip mirror:

```bash
python scripts/build_portable_zip.py --download-wheels
```

The zip is written to:

```text
dist/myKamus-portable.zip
```

## What Is Included

- GUI runtime Python files
- `Start myKamus.bat`
- `README_FIRST.txt`
- `requirements.txt`
- `wheels/` when present
- `portable-package.json`

## What Is Excluded

Large data files are excluded so the zip can be uploaded to GitHub:

- `en-id_dict.txt`
- `en-id_sentences.txt`
- `indonesiandictionary.pdf`

Users provide those files from the corporate network data folder or use Git LFS fallback.

## Dependency Location

Dependencies install into local `vendor/` using:

```bash
python -m pip install --target vendor ...
```

This keeps packages local to the myKamus folder without creating a virtual environment or local Python executable.

## Deferred Work

- Windows installer
- Bundled Python
- Custom executable packaging
- CLI launchers
- Source-layout cleanup
````

- [ ] **Step 3: Commit docs**

Run:

```bash
git add README_FIRST.txt docs/portable-distribution.md
git commit -m "docs: add portable distribution instructions"
```

Expected: commit includes only the two documentation files.

---

### Task 8: Integrate Build Script File List With Docs and Run Full Verification

**Files:**
- Modify as needed: `scripts/build_portable_zip.py`, `README_FIRST.txt`, `docs/portable-distribution.md`

- [ ] **Step 1: Build a portable zip**

Run:

```bash
python scripts/build_portable_zip.py
```

Expected: command exits `0` and prints `Built dist\myKamus-portable.zip` or equivalent path.

- [ ] **Step 2: Inspect zip contents**

Run:

```bash
python -c "import zipfile; archive=zipfile.ZipFile('dist/myKamus-portable.zip'); names=set(archive.namelist()); print('myKamus/Start myKamus.bat' in names); print('myKamus/portable-package.json' in names); print('myKamus/en-id_sentences.txt' in names)"
```

Expected:

```text
True
True
False
```

- [ ] **Step 3: Run focused tests**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
python -B -m unittest discover -s tests -p test_build_portable_zip.py
```

Expected: both commands pass.

- [ ] **Step 4: Run full test suite**

Run:

```bash
python -B -m unittest discover -s tests
```

Expected: all tests pass. Existing environment may report one skipped Qt dependency test when PySide6 is installed.

- [ ] **Step 5: Commit any integration corrections**

If Step 1 through Step 4 required edits, commit them:

```bash
git add scripts/build_portable_zip.py README_FIRST.txt docs/portable-distribution.md tests/test_build_portable_zip.py tests/test_gui_preflight.py gui_app/preflight.py
git commit -m "fix: align portable zip integration"
```

If no edits were required, skip this commit.

- [ ] **Step 6: Request code review**

Use `superpowers:requesting-code-review` on the implementation range. Review should check:

- Dependencies install into `vendor/`.
- `vendor/` is prepended before dependency imports.
- Setup choice is remembered in `.mykamus_cache/setup.json`.
- Data folder fallback writes usable config paths.
- Build zip excludes large data files.
- Build zip includes runtime files and metadata.
- No custom `.exe`, installer, bundled Python, or CLI launcher was added.

---

## Self-Review

Spec coverage:

- Local `vendor/` dependencies: Tasks 1 through 3.
- Setup choice before import checks: Tasks 2 and 3.
- Remembered setup state: Task 1 and Task 3.
- Python version warning: Task 4.
- External corporate data folder: Task 5.
- Git LFS fallback remains in `ensure_data_files`: Task 5 keeps the existing fallback after corporate-folder resolution.
- Build script and optional wheel download: Task 6.
- User and maintainer docs: Task 7.
- Full verification and review: Task 8.

Deferred scope preserved:

- No installer.
- No bundled Python.
- No custom `.exe`.
- No CLI launcher.
- No source-layout migration.
- No large data files in the zip.

Placeholder scan:

- No placeholder markers or intentionally unspecified implementation steps are present.

Type and name consistency:

- `load_setup_state`, `save_setup_state`, `prepend_vendor_path`, `read_package_metadata`, `choose_dependency_method`, `install_dependencies`, `other_dependency_method`, `warn_python_version_mismatch`, `choose_data_folder`, and `apply_data_folder_to_config` are introduced before later tasks rely on them.
