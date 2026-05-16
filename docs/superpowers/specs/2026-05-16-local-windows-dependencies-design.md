# Local Windows Dependencies Design

## Goal

Make the Windows launcher reliably use Python packages installed locally inside the myKamus folder, especially PySide6, without trusting corporate-machine global Python package state.

## User Outcome

A Windows user double-clicks `Start myKamus.bat`. If required GUI dependencies are already available from the local myKamus dependency folder, the app starts normally. If they are missing, myKamus explains the issue, asks permission, reinstalls dependencies locally, writes a support log, and then launches the GUI when local imports pass.

## Scope

Included:

- Windows launcher dependency preflight.
- Local dependency folder named `.mykamus_vendor/`.
- Local-only import checks before launch.
- Permission prompt before installing dependencies.
- Delete-and-reinstall behavior for `.mykamus_vendor/`.
- Setup logging to `myKamus_setup.log`.
- README documentation for Windows users and manual users.

Excluded:

- GUI layout redesign.
- Bundled Python.
- Custom `.exe` packaging.
- Windows installer.
- Local `wheels/` support.
- Mac/Linux launcher changes.
- Search, indexing, and result-rendering behavior changes.

## Dependency Model

Windows launcher dependencies live in:

```text
myKamus/
  .mykamus_vendor/
```

The launcher and preflight must make `.mykamus_vendor/` the first dependency lookup location before checking imports or starting the GUI. This avoids using a global PySide6 installation that corporate Python or pip may report as installed but the app cannot reliably load.

The local install command is:

```bash
python -m pip install --target .mykamus_vendor --upgrade --force-reinstall -r requirements.txt
```

When reinstalling, preflight deletes `.mykamus_vendor/` first. This is intentional because partial or corrupted PySide6/Qt installs can leave stale files that cause confusing import or plugin errors.

## Startup Flow

`Start myKamus.bat` remains the Windows entry point.

1. Resolve the launcher folder using `%~dp0`.
2. Prepend `%~dp0.mykamus_vendor` to `PYTHONPATH`, preserving any existing `PYTHONPATH`.
3. Run `python -m gui_app.preflight`.
4. If preflight succeeds, run `python -m gui_app.app`.
5. If preflight fails, keep the terminal open and show a clear support message.

Preflight dependency behavior:

1. Prepend `.mykamus_vendor/` to `sys.path`.
2. Read dependencies from `requirements.txt`.
3. Check required imports from the local dependency context.
4. If imports work, do not run pip.
5. If imports fail, print the missing packages and ask the user before installing.
6. If the user approves, delete `.mykamus_vendor/`.
7. Run the local pip install command.
8. Check imports again from `.mykamus_vendor/`.
9. Return success only when local imports pass.

The dependency check must not treat globally importable packages as sufficient. The user selected local dependencies specifically because corporate computers may report a package as installed while the application still fails to load it.

## Logging And Failure Behavior

When dependency installation runs, preflight writes:

```text
myKamus_setup.log
```

The log must include:

- Python executable path.
- Python version.
- The exact pip command.
- pip stdout.
- pip stderr.
- Final local import-check result.

If install fails, or dependencies still cannot import from `.mykamus_vendor/`, the terminal should show:

```text
myKamus could not install or load its local Python packages.
Please send myKamus_setup.log to your internal support person.
```

The terminal should remain open so a non-technical user can see the failure and support instructions.

## Platform Boundary

This design is Windows-launcher focused.

- `Start myKamus.bat` owns automatic local dependency setup.
- `python -m gui_app.app` remains intact for Mac/Linux/manual users.
- Manual users can install local dependencies themselves with the same pip command.
- No Python runtime is bundled.
- No executable wrapper is introduced.
- No installer is introduced.

## Documentation

Update `README.md` with a Windows dependency setup section that explains:

- Launch with `Start myKamus.bat`.
- Dependencies are installed locally into `.mykamus_vendor/`.
- The launcher does not trust global PySide6 or global pip installs.
- If local dependencies are missing, the launcher asks before reinstalling them.
- Reinstall deletes `.mykamus_vendor/` first.
- Setup failures are written to `myKamus_setup.log`.
- Mac/Linux/manual users can still use `python -m gui_app.app`.

The README should include the manual command:

```bash
python -m pip install --target .mykamus_vendor --upgrade --force-reinstall -r requirements.txt
```

## Testing Strategy

Unit tests should cover:

- Local vendor path is prepended before import checks.
- Import checks use the local vendor context rather than accepting global packages.
- Preflight does not reinstall when local imports pass.
- Preflight asks before installing when local imports fail.
- Reinstall deletes `.mykamus_vendor/` before running pip.
- pip command uses `--target .mykamus_vendor --upgrade --force-reinstall -r requirements.txt`.
- Setup log includes Python details, command, pip output, and final import-check result.
- Launcher sets `PYTHONPATH` to include `.mykamus_vendor` before running `python -m gui_app.app`.
- Failure messaging mentions `myKamus_setup.log`.

Manual smoke tests should cover:

- Start from no `.mykamus_vendor/`, approve install, and launch the GUI.
- Start with a valid `.mykamus_vendor/` and confirm pip is not run again.
- Simulate pip failure and confirm the terminal message and `myKamus_setup.log` are written.

## Future Work

After local dependency startup is reliable, revisit the GUI layout redesign as a separate spec. That redesign should target a fast lookup tool with a clean dictionary-reader presentation.
