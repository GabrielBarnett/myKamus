# Local Windows Dependencies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Windows launcher install and load GUI dependencies from local `.mykamus_vendor/`, with clear logging and README guidance.

**Architecture:** Keep `Start myKamus.bat` as the Windows entry point and `gui_app.preflight` as the setup coordinator. Preflight will prepend `.mykamus_vendor/`, check imports only from that local folder, ask before reinstalling, delete the old vendor folder, run pip with `--target .mykamus_vendor --upgrade --force-reinstall`, write `myKamus_setup.log`, then continue to existing data-file checks. The GUI entry point `python -m gui_app.app` remains unchanged for manual and Mac/Linux users.

**Tech Stack:** Python standard library (`importlib.util`, `pathlib`, `shutil`, `subprocess`, `sys`, `unittest`, `unittest.mock`), Windows batch, Markdown documentation.

---

## File Structure

- Modify `gui_app/preflight.py`
  - Add `.mykamus_vendor/` path constants, local import checking, reinstall command construction, vendor deletion, setup logging, and updated failure messages.
- Modify `tests/test_gui_preflight.py`
  - Replace global-pip dependency tests with local-vendor tests.
- Modify `Start myKamus.bat`
  - Prepend `%~dp0.mykamus_vendor` to `PYTHONPATH` before preflight and GUI startup.
- Modify `README.md`
  - Document Windows local dependency setup, support log, and manual command.

Do not change GUI layout, search/indexing logic, result rendering, Mac/Linux entry points, or add wheel/installer/exe support.

---

### Task 1: Vendor Path And Local Import Checks

**Files:**
- Modify: `gui_app/preflight.py`
- Modify: `tests/test_gui_preflight.py`

- [x] **Step 1: Write failing tests for vendor path and local-only checks**

In `tests/test_gui_preflight.py`, replace `test_missing_dependency_imports_maps_requirements_to_modules` with:

```python
    def test_prepend_vendor_path_inserts_local_vendor_first_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vendor_path = Path(temp_dir) / ".mykamus_vendor"
            python_path = ["global-packages"]

            preflight.prepend_vendor_path(vendor_path=vendor_path, python_path=python_path)
            preflight.prepend_vendor_path(vendor_path=vendor_path, python_path=python_path)

        self.assertEqual([str(vendor_path), "global-packages"], python_path)

    def test_missing_dependency_imports_checks_with_vendor_path_first(self):
        calls = []

        def fake_find_spec(module_name):
            calls.append((module_name, list(sys.path)))
            if module_name == "PySide6":
                return None
            return object()

        with tempfile.TemporaryDirectory() as temp_dir:
            vendor_path = Path(temp_dir) / ".mykamus_vendor"
            python_path = ["global-packages"]
            with mock.patch.object(preflight.importlib.util, "find_spec", side_effect=fake_find_spec), \
                    mock.patch.object(preflight.sys, "path", python_path):
                missing = preflight.missing_dependency_imports(
                    ["keyboard", "PySide6"],
                    vendor_path=vendor_path,
                )

        self.assertEqual(["PySide6"], missing)
        self.assertTrue(all(call_path[0] == str(vendor_path) for _module, call_path in calls))
        self.assertEqual([str(vendor_path), "global-packages"], python_path)
```

- [x] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: failures for missing `prepend_vendor_path` and unsupported `vendor_path` argument on `missing_dependency_imports`.

- [x] **Step 3: Implement vendor path helpers**

In `gui_app/preflight.py`, add after `REQUIREMENTS_PATH`:

```python
VENDOR_PATH = BASE_DIR / ".mykamus_vendor"
SETUP_LOG_PATH = BASE_DIR / "myKamus_setup.log"
```

Add before `read_requirements()`:

```python
def prepend_vendor_path(vendor_path=VENDOR_PATH, python_path=None):
    if python_path is None:
        python_path = sys.path
    text_path = str(Path(vendor_path))
    if text_path in python_path:
        python_path.remove(text_path)
    python_path.insert(0, text_path)
```

Replace `missing_dependency_imports()` with:

```python
def missing_dependency_imports(requirements, vendor_path=VENDOR_PATH):
    prepend_vendor_path(vendor_path=vendor_path)
    missing = []
    for requirement in requirements:
        module_name = REQUIREMENT_IMPORTS.get(requirement, requirement)
        if importlib.util.find_spec(module_name) is None:
            missing.append(requirement)
    return missing
```

- [x] **Step 4: Run tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: all `test_gui_preflight.py` tests pass.

- [x] **Step 5: Commit vendor path work**

Run:

```bash
git add gui_app/preflight.py tests/test_gui_preflight.py
git commit -m "feat: check dependencies from local vendor path"
```

Expected: commit includes only `gui_app/preflight.py` and `tests/test_gui_preflight.py`.

---

### Task 2: Local Reinstall Command And Setup Logging

**Files:**
- Modify: `gui_app/preflight.py`
- Modify: `tests/test_gui_preflight.py`

- [x] **Step 1: Write failing tests for reinstall and logging helpers**

Append these tests to `tests/test_gui_preflight.py`:

```python
    def test_install_dependencies_deletes_vendor_and_uses_force_reinstall_target(self):
        commands = []
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            vendor_path = base_dir / ".mykamus_vendor"
            vendor_path.mkdir()
            (vendor_path / "stale.txt").write_text("old", encoding="utf-8")
            requirements_path = base_dir / "requirements.txt"
            requirements_path.write_text("PySide6\n", encoding="utf-8")

            result = preflight.install_local_dependencies(
                vendor_path=vendor_path,
                requirements_path=requirements_path,
                log_path=base_dir / "myKamus_setup.log",
                run_command_func=lambda command: commands.append(command) or mock.Mock(
                    returncode=0,
                    stdout="installed",
                    stderr="",
                ),
            )

        self.assertTrue(result)
        self.assertFalse((vendor_path / "stale.txt").exists())
        self.assertEqual(
            [[
                sys.executable,
                "-m",
                "pip",
                "install",
                "--target",
                str(vendor_path),
                "--upgrade",
                "--force-reinstall",
                "-r",
                str(requirements_path),
            ]],
            commands,
        )

    def test_install_dependencies_writes_setup_log(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            log_path = base_dir / "myKamus_setup.log"
            result = preflight.install_local_dependencies(
                vendor_path=base_dir / ".mykamus_vendor",
                requirements_path=base_dir / "requirements.txt",
                log_path=log_path,
                run_command_func=lambda _command: mock.Mock(
                    returncode=1,
                    stdout="pip output",
                    stderr="pip error",
                ),
            )

            log_text = log_path.read_text(encoding="utf-8")

        self.assertFalse(result)
        self.assertIn(sys.executable, log_text)
        self.assertIn("pip output", log_text)
        self.assertIn("pip error", log_text)
        self.assertIn("--force-reinstall", log_text)
```

- [x] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: failure with missing `install_local_dependencies`.

- [x] **Step 3: Implement reinstall and logging helpers**

In `gui_app/preflight.py`, add:

```python
def run_pip_command(command):
    return subprocess.run(
        command,
        cwd=BASE_DIR,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def write_setup_log(command, result, log_path=SETUP_LOG_PATH, final_missing=None):
    lines = [
        "myKamus setup log",
        "Python executable: " + sys.executable,
        "Python version: " + sys.version.replace("\n", " "),
        "Command: " + " ".join(str(part) for part in command),
        "",
        "pip stdout:",
        result.stdout or "",
        "",
        "pip stderr:",
        result.stderr or "",
    ]
    if final_missing is not None:
        lines.extend(["", "Final missing packages: " + ", ".join(final_missing)])
    Path(log_path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def append_final_import_check(final_missing, log_path=SETUP_LOG_PATH):
    missing_text = ", ".join(final_missing) if final_missing else "none"
    with Path(log_path).open("a", encoding="utf-8") as log_file:
        log_file.write("\nFinal local import check:\n")
        log_file.write("Missing packages: " + missing_text + "\n")


def install_local_dependencies(
    vendor_path=VENDOR_PATH,
    requirements_path=REQUIREMENTS_PATH,
    log_path=SETUP_LOG_PATH,
    run_command_func=run_pip_command,
):
    vendor_path = Path(vendor_path)
    if vendor_path.exists():
        shutil.rmtree(vendor_path)
    vendor_path.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--target",
        str(vendor_path),
        "--upgrade",
        "--force-reinstall",
        "-r",
        str(requirements_path),
    ]
    result = run_command_func(command)
    write_setup_log(command, result, log_path=log_path)
    return result.returncode == 0
```

- [x] **Step 4: Run tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: all `test_gui_preflight.py` tests pass.

- [x] **Step 5: Commit reinstall and logging helpers**

Run:

```bash
git add gui_app/preflight.py tests/test_gui_preflight.py
git commit -m "feat: reinstall dependencies into local vendor"
```

Expected: commit includes only `gui_app/preflight.py` and `tests/test_gui_preflight.py`.

---

### Task 3: Preflight Dependency Flow

**Files:**
- Modify: `gui_app/preflight.py`
- Modify: `tests/test_gui_preflight.py`

- [x] **Step 1: Replace old dependency-flow tests**

Replace the old tests that expect `python -m pip install -r requirements.txt` without a target with these tests:

```python
    def test_ensure_dependencies_does_not_install_when_local_imports_pass(self):
        messages = []
        with mock.patch.object(preflight, "read_requirements", return_value=["PySide6"]), \
                mock.patch.object(preflight, "missing_dependency_imports", return_value=[]), \
                mock.patch.object(preflight, "install_local_dependencies") as install:
            result = preflight.ensure_dependencies(
                input_func=lambda _question: "n",
                output_func=messages.append,
            )

        self.assertTrue(result)
        install.assert_not_called()
        self.assertEqual([], messages)

    def test_ensure_dependencies_asks_before_local_reinstall(self):
        messages = []
        missing_results = [["PySide6"], []]

        with mock.patch.object(preflight, "read_requirements", return_value=["PySide6"]), \
                mock.patch.object(
                    preflight,
                    "missing_dependency_imports",
                    side_effect=lambda _requirements: missing_results.pop(0),
                ), \
                mock.patch.object(preflight, "install_local_dependencies", return_value=True) as install:
            result = preflight.ensure_dependencies(
                input_func=lambda _question: "y",
                output_func=messages.append,
            )

        self.assertTrue(result)
        install.assert_called_once()
        self.assertTrue(any("local Python packages" in message for message in messages))

    def test_ensure_dependencies_failure_mentions_setup_log(self):
        messages = []

        with mock.patch.object(preflight, "read_requirements", return_value=["PySide6"]), \
                mock.patch.object(preflight, "missing_dependency_imports", return_value=["PySide6"]), \
                mock.patch.object(preflight, "install_local_dependencies", return_value=False):
            result = preflight.ensure_dependencies(
                input_func=lambda _question: "y",
                output_func=messages.append,
            )

        self.assertFalse(result)
        self.assertTrue(any("myKamus_setup.log" in message for message in messages))
```

- [x] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: failures because `ensure_dependencies()` still describes global requirements installation and does not call `install_local_dependencies()`.

- [x] **Step 3: Implement local dependency preflight flow**

Replace `ensure_dependencies()` with:

```python
def dependency_failure_message(output_func=print):
    output_func("myKamus could not install or load its local Python packages.")
    output_func("Please send myKamus_setup.log to your internal support person.")


def ensure_dependencies(input_func=input, output_func=print):
    requirements = read_requirements()
    missing = missing_dependency_imports(requirements)
    if not missing:
        return True

    output_func("myKamus needs local Python packages before it can start:")
    for package_name in missing:
        output_func("- " + package_name)
    output_func("")

    if not prompt_yes_no(
        "Install them locally into .mykamus_vendor now?",
        input_func=input_func,
        output_func=output_func,
    ):
        output_func(
            "You can install them later with: python -m pip install --target .mykamus_vendor --upgrade --force-reinstall -r requirements.txt"
        )
        return False

    if not install_local_dependencies():
        dependency_failure_message(output_func=output_func)
        return False

    still_missing = missing_dependency_imports(requirements)
    append_final_import_check(still_missing)
    if still_missing:
        output_func("Some local Python packages are still missing:")
        for package_name in still_missing:
            output_func("- " + package_name)
        dependency_failure_message(output_func=output_func)
        return False

    return True
```

- [x] **Step 4: Run tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: all `test_gui_preflight.py` tests pass.

- [x] **Step 5: Commit dependency flow**

Run:

```bash
git add gui_app/preflight.py tests/test_gui_preflight.py
git commit -m "feat: use local vendor dependency preflight"
```

Expected: commit includes only `gui_app/preflight.py` and `tests/test_gui_preflight.py`.

---

### Task 4: Windows Launcher Vendor Path

**Files:**
- Modify: `Start myKamus.bat`
- Modify: `tests/test_gui_preflight.py`

- [x] **Step 1: Write failing launcher text test**

Append this test to `tests/test_gui_preflight.py`:

```python
    def test_windows_launcher_sets_vendor_pythonpath_before_gui_start(self):
        launcher_text = (preflight.BASE_DIR / "Start myKamus.bat").read_text(encoding="utf-8")
        pythonpath_index = launcher_text.find("PYTHONPATH")
        gui_index = launcher_text.find("-m gui_app.app")

        self.assertIn("%~dp0", launcher_text)
        self.assertIn(".mykamus_vendor", launcher_text)
        self.assertGreaterEqual(pythonpath_index, 0)
        self.assertGreater(gui_index, pythonpath_index)
```

- [x] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: failure because `Start myKamus.bat` does not set `PYTHONPATH`.

- [x] **Step 3: Update launcher**

In `Start myKamus.bat`, after `cd /d "%~dp0"` add:

```bat
set "MYKAMUS_DIR=%~dp0"
if defined PYTHONPATH (
    set "PYTHONPATH=%MYKAMUS_DIR%.mykamus_vendor;%PYTHONPATH%"
) else (
    set "PYTHONPATH=%MYKAMUS_DIR%.mykamus_vendor"
)
```

In the preflight failure block, replace:

```bat
echo myKamus could not finish setup.
```

with:

```bat
echo myKamus could not install or load its local Python packages.
echo Please send myKamus_setup.log to your internal support person.
```

- [x] **Step 4: Run tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: all `test_gui_preflight.py` tests pass.

- [x] **Step 5: Commit launcher update**

Run:

```bash
git add "Start myKamus.bat" tests/test_gui_preflight.py
git commit -m "feat: load local vendor dependencies in Windows launcher"
```

Expected: commit includes launcher and test updates.

---

### Task 5: README Documentation

**Files:**
- Modify: `README.md`

- [x] **Step 1: Update README Windows section**

Replace the current "Windows beginner start" section with:

````markdown
## Windows beginner start

On Windows, double-click:

```text
Start myKamus.bat
```

The launcher checks whether local Python packages and bundled data files are ready before starting the GUI. Python packages are installed into `.mykamus_vendor/` inside the myKamus folder, so myKamus does not rely on global PySide6 or global pip package state on corporate computers.

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
````

- [x] **Step 2: Verify README contains required support text**

Run:

```bash
Select-String -Path README.md -Pattern ".mykamus_vendor|myKamus_setup.log|--force-reinstall|python -m gui_app.app|Start myKamus.bat"
```

Expected: all five patterns appear.

- [x] **Step 3: Commit README docs**

Run:

```bash
git add README.md
git commit -m "docs: document local Windows dependency setup"
```

Expected: commit includes only `README.md`.

---

### Task 6: Full Verification

**Files:**
- Modify as needed: `gui_app/preflight.py`, `tests/test_gui_preflight.py`, `Start myKamus.bat`, `README.md`

- [x] **Step 1: Run focused tests**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: all preflight tests pass.

- [x] **Step 2: Run full test suite**

Run:

```bash
python -B -m unittest discover -s tests
```

Expected: all tests pass. Existing environment may report one skipped Qt dependency test depending on PySide6 availability.

- [x] **Step 3: Compile changed Python file**

Run:

```bash
python -m py_compile gui_app\preflight.py
```

Expected: command exits `0`.

- [x] **Step 4: Check final git state**

Run:

```bash
git status --short --branch
```

Expected: clean working tree on the implementation branch.

- [x] **Step 5: Request code review**

Use `superpowers:requesting-code-review` over the implementation range. Review should check:

- Local dependency checks use `.mykamus_vendor/`.
- Global packages are not accepted as sufficient for Windows launcher preflight.
- Reinstall deletes `.mykamus_vendor/` first.
- pip command uses `--target .mykamus_vendor --upgrade --force-reinstall -r requirements.txt`.
- `myKamus_setup.log` records useful failure context.
- `Start myKamus.bat` prepends `.mykamus_vendor` to `PYTHONPATH`.
- README describes the behavior for non-technical users.

---

## Self-Review

Spec coverage:

- `.mykamus_vendor/` local dependency model: Tasks 1 through 4.
- Local-only import checks: Task 1 and Task 3.
- Ask before reinstalling: Task 3.
- Delete-and-reinstall behavior: Task 2 and Task 3.
- Setup logging: Task 2 and Task 3.
- Launcher `PYTHONPATH`: Task 4.
- README documentation: Task 5.
- Verification and review: Task 6.

Scope control:

- No GUI layout redesign.
- No bundled Python.
- No custom executable.
- No installer.
- No wheel support.
- No Mac/Linux launcher change.

Placeholder scan:

- No placeholder markers or intentionally unspecified implementation steps are present.

Type and name consistency:

- `VENDOR_PATH`, `SETUP_LOG_PATH`, `prepend_vendor_path`, `missing_dependency_imports`, `install_local_dependencies`, `write_setup_log`, `append_final_import_check`, `dependency_failure_message`, and `ensure_dependencies` are introduced before later tasks rely on them.

