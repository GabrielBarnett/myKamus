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
