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

    def test_missing_data_files_reports_required_files_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            (base_dir / "en-id_dict.txt").write_text("dict", encoding="utf-8")

            missing = preflight.missing_data_files(base_dir)

        self.assertEqual(
            ["en-id_sentences.txt", "indonesiandictionary.pdf"],
            missing,
        )

    def test_missing_data_files_reports_git_lfs_pointer_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            for file_name in preflight.REQUIRED_DATA_FILES:
                (base_dir / file_name).write_text("data", encoding="utf-8")
            (base_dir / "en-id_dict.txt").write_text(
                "version https://git-lfs.github.com/spec/v1\n"
                "oid sha256:1234567890abcdef\n"
                "size 123\n",
                encoding="utf-8",
            )

            missing = preflight.missing_data_files(base_dir)

        self.assertEqual(["en-id_dict.txt"], missing)

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

    def test_ensure_dependencies_fails_when_packages_remain_missing_after_install(self):
        messages = []
        missing_results = [["PySide6"], ["PySide6"]]

        with mock.patch.object(preflight, "read_requirements", return_value=["PySide6"]), \
                mock.patch.object(
                    preflight,
                    "missing_dependency_imports",
                    side_effect=lambda _requirements: missing_results.pop(0),
                ), \
                mock.patch.object(preflight, "run_command", return_value=True):
            result = preflight.ensure_dependencies(
                input_func=lambda _question: "y",
                output_func=messages.append,
            )

        self.assertFalse(result)
        self.assertTrue(any("Some Python packages are still missing" in message for message in messages))
        self.assertTrue(any("- PySide6" in message for message in messages))

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
                mock.patch.object(preflight, "command_exists", return_value=False), \
                mock.patch.object(preflight, "run_command") as run_command:
            result = preflight.ensure_data_files(
                input_func=lambda _question: "n",
                output_func=messages.append,
            )

        self.assertFalse(result)
        run_command.assert_not_called()
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
                mock.patch.object(preflight, "command_exists", return_value=True), \
                mock.patch.object(preflight, "run_command") as run_command:
            result = preflight.ensure_data_files(
                input_func=lambda _question: "n",
                output_func=messages.append,
            )

        self.assertFalse(result)
        run_command.assert_not_called()
        self.assertTrue(any("Cannot start until these data files are present" in message for message in messages))

    def test_main_returns_zero_when_dependencies_and_data_are_ready(self):
        input_func = mock.Mock(return_value="n")
        output_func = mock.Mock()

        with mock.patch.object(preflight, "ensure_dependencies", return_value=True) as ensure_dependencies, \
                mock.patch.object(preflight, "ensure_data_files", return_value=True) as ensure_data_files:
            result = preflight.main(
                input_func=input_func,
                output_func=output_func,
            )

        self.assertEqual(0, result)
        ensure_dependencies.assert_called_once_with(input_func=input_func, output_func=output_func)
        ensure_data_files.assert_called_once_with(input_func=input_func, output_func=output_func)

    def test_main_returns_one_when_dependencies_are_not_ready(self):
        input_func = mock.Mock(return_value="n")
        output_func = mock.Mock()

        with mock.patch.object(preflight, "ensure_dependencies", return_value=False) as ensure_dependencies, \
                mock.patch.object(preflight, "ensure_data_files", return_value=True) as ensure_data_files:
            result = preflight.main(
                input_func=input_func,
                output_func=output_func,
            )

        self.assertEqual(1, result)
        ensure_dependencies.assert_called_once_with(input_func=input_func, output_func=output_func)
        ensure_data_files.assert_not_called()

    def test_main_returns_one_when_data_files_are_not_ready(self):
        input_func = mock.Mock(return_value="n")
        output_func = mock.Mock()

        with mock.patch.object(preflight, "ensure_dependencies", return_value=True) as ensure_dependencies, \
                mock.patch.object(preflight, "ensure_data_files", return_value=False) as ensure_data_files:
            result = preflight.main(
                input_func=input_func,
                output_func=output_func,
            )

        self.assertEqual(1, result)
        ensure_dependencies.assert_called_once_with(input_func=input_func, output_func=output_func)
        ensure_data_files.assert_called_once_with(input_func=input_func, output_func=output_func)


if __name__ == "__main__":
    unittest.main()
