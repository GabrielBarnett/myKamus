import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path

from sentence_data.layout import DEFAULT_SENTENCE_DATA_DIR
from search_index import IndexUnavailableError, ensure_sentence_dataset


BASE_DIR = Path(__file__).resolve().parent.parent
REQUIREMENTS_PATH = BASE_DIR / "requirements.txt"
VENDOR_PATH = BASE_DIR / ".mykamus_vendor"
SETUP_LOG_PATH = BASE_DIR / "myKamus_setup.log"
REQUIRED_DATA_FILES = [
    "en-id_dict.txt",
    "indonesiandictionary.pdf",
]
REQUIREMENT_IMPORTS = {
    "keyboard": "keyboard",
    "pypdf": "pypdf",
    "pyperclip": "pyperclip",
}


def prepend_vendor_path(vendor_path=VENDOR_PATH, python_path=None):
    if python_path is None:
        python_path = sys.path
    text_path = str(Path(vendor_path))
    if text_path in python_path:
        python_path.remove(text_path)
    python_path.insert(0, text_path)


def path_is_inside(path, base_path):
    try:
        Path(path).resolve(strict=False).relative_to(Path(base_path).resolve(strict=False))
        return True
    except (OSError, ValueError):
        return False


def spec_uses_vendor_path(spec, vendor_path):
    origin = getattr(spec, "origin", None)
    if origin and origin not in {"built-in", "frozen"} and path_is_inside(origin, vendor_path):
        return True

    for location in getattr(spec, "submodule_search_locations", None) or []:
        if path_is_inside(location, vendor_path):
            return True

    return False


def read_requirements(requirements_path=REQUIREMENTS_PATH):
    requirements = []
    for line in Path(requirements_path).read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            requirements.append(text)
    return requirements


def missing_dependency_imports(requirements, vendor_path=VENDOR_PATH):
    prepend_vendor_path(vendor_path=vendor_path)
    importlib.invalidate_caches()
    missing = []
    for requirement in requirements:
        module_name = REQUIREMENT_IMPORTS.get(requirement, requirement)
        spec = importlib.util.find_spec(module_name)
        if spec is None or not spec_uses_vendor_path(spec, vendor_path):
            missing.append(requirement)
    return missing


def is_git_lfs_pointer(path):
    try:
        with Path(path).open("r", encoding="utf-8") as file:
            return file.readline().strip() == "version https://git-lfs.github.com/spec/v1"
    except OSError:
        return True
    except UnicodeDecodeError:
        return False


def missing_data_files(base_dir=BASE_DIR):
    missing = []
    for file_name in REQUIRED_DATA_FILES:
        path = Path(base_dir) / file_name
        if not path.is_file() or is_git_lfs_pointer(path):
            missing.append(file_name)
    return missing


def sentence_dataset_errors(base_dir=BASE_DIR):
    dataset_dir = Path(base_dir) / DEFAULT_SENTENCE_DATA_DIR
    try:
        ensure_sentence_dataset(dataset_dir)
    except IndexUnavailableError as error:
        return [str(error) or "Sentence dataset is unavailable."]
    return []


def command_exists(command_name):
    return shutil.which(command_name) is not None


def run_command(command):
    return subprocess.run(command, cwd=BASE_DIR).returncode == 0


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


def prompt_yes_no(question, input_func=input, output_func=print):
    while True:
        answer = input_func(question + " [Y/N] ").strip().casefold()
        if answer in {"y", "yes"}:
            return True
        if answer in {"", "n", "no"}:
            return False
        output_func("Please answer Y or N.")


def dependency_failure_message(output_func=print):
    output_func("myKamus could not install or load its local Python packages.")
    output_func("Please send myKamus_setup.log to your internal support person.")


def ensure_dependencies(input_func=input, output_func=print, log_path=SETUP_LOG_PATH):
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

    if not install_local_dependencies(log_path=log_path):
        dependency_failure_message(output_func=output_func)
        return False

    still_missing = missing_dependency_imports(requirements)
    append_final_import_check(still_missing, log_path=log_path)
    if still_missing:
        output_func("Some local Python packages are still missing:")
        for package_name in still_missing:
            output_func("- " + package_name)
        dependency_failure_message(output_func=output_func)
        return False

    return True


def ensure_data_files(input_func=input, output_func=print):
    missing = missing_data_files()
    sentence_errors = sentence_dataset_errors()
    if not missing and not sentence_errors:
        return True

    if missing:
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

        sentence_errors = sentence_dataset_errors()

    if sentence_errors:
        output_func("myKamus needs the checked-in sharded sentence dataset before it can start:")
        for message in sentence_errors:
            output_func("- " + message)
        output_func("Restore the data/sentences folder from the repository.")
        return False

    return True


def main(input_func=input, output_func=print):
    if not ensure_dependencies(input_func=input_func, output_func=output_func):
        return 1
    if not ensure_data_files(input_func=input_func, output_func=output_func):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
