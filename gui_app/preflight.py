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


def main(input_func=input, output_func=print):
    if not ensure_dependencies(input_func=input_func, output_func=output_func):
        return 1
    if not ensure_data_files(input_func=input_func, output_func=output_func):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
