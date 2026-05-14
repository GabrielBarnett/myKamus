import tempfile
import sys
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


if __name__ == "__main__":
    unittest.main()
