import tempfile
import sys
import unittest
from pathlib import Path
from unittest import mock

from gui_app import preflight


class PreflightDetectionTests(unittest.TestCase):
    def test_windows_launcher_sets_vendor_pythonpath_before_gui_start(self):
        launcher_text = (preflight.BASE_DIR / "Start myKamus.bat").read_text(encoding="utf-8")
        pythonpath_index = launcher_text.find("PYTHONPATH")
        delayed_pythonpath_index = launcher_text.find("!PYTHONPATH!")
        gui_index = launcher_text.find("-m gui_app.app")

        self.assertIn("setlocal EnableDelayedExpansion", launcher_text)
        self.assertIn("%~dp0", launcher_text)
        self.assertIn(".mykamus_vendor", launcher_text)
        self.assertIn("!PYTHONPATH!", launcher_text)
        self.assertIn("!ERRORLEVEL!", launcher_text)
        self.assertNotIn("%ERRORLEVEL%", launcher_text)
        self.assertGreaterEqual(pythonpath_index, 0)
        self.assertGreaterEqual(delayed_pythonpath_index, 0)
        self.assertGreater(gui_index, pythonpath_index)
        self.assertGreater(gui_index, delayed_pythonpath_index)

    def test_requirement_imports_align_with_checked_in_requirements(self):
        checked_in_requirements = preflight.read_requirements(preflight.REQUIREMENTS_PATH)

        self.assertEqual(checked_in_requirements, list(preflight.REQUIREMENT_IMPORTS))
        self.assertTrue(all(preflight.REQUIREMENT_IMPORTS[requirement] for requirement in checked_in_requirements))

    def test_read_requirements_ignores_blank_lines_and_comments(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            requirements_path = Path(temp_dir) / "requirements.txt"
            requirements_path.write_text(
                "\n# comment\nkeyboard\npypdf\npyperclip\n",
                encoding="utf-8",
            )

            self.assertEqual(
                ["keyboard", "pypdf", "pyperclip"],
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

        with tempfile.TemporaryDirectory() as temp_dir:
            vendor_path = Path(temp_dir) / ".mykamus_vendor"
            keyboard_dir = vendor_path / "keyboard"

            class FakeSpec:
                origin = str(keyboard_dir / "__init__.py")
                submodule_search_locations = [str(keyboard_dir)]

            def fake_find_spec(module_name):
                calls.append((module_name, list(sys.path)))
                if module_name == "pyperclip":
                    return None
                return FakeSpec()

            python_path = ["global-packages"]
            with mock.patch.object(preflight.importlib.util, "find_spec", side_effect=fake_find_spec), \
                    mock.patch.object(preflight.sys, "path", python_path):
                missing = preflight.missing_dependency_imports(
                    ["keyboard", "pyperclip"],
                    vendor_path=vendor_path,
                )

        self.assertEqual(["pyperclip"], missing)
        self.assertTrue(all(call_path[0] == str(vendor_path) for _module, call_path in calls))
        self.assertEqual([str(vendor_path), "global-packages"], python_path)

    def test_missing_dependency_imports_rejects_global_only_package(self):
        class FakeSpec:
            origin = str(Path("C:/global/site-packages/pyperclip/__init__.py"))
            submodule_search_locations = [str(Path("C:/global/site-packages/pyperclip"))]

        with tempfile.TemporaryDirectory() as temp_dir:
            vendor_path = Path(temp_dir) / ".mykamus_vendor"
            with mock.patch.object(preflight.importlib.util, "find_spec", return_value=FakeSpec()):
                missing = preflight.missing_dependency_imports(["pyperclip"], vendor_path=vendor_path)

        self.assertEqual(["pyperclip"], missing)

    def test_missing_dependency_imports_accepts_vendor_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vendor_path = Path(temp_dir) / ".mykamus_vendor"
            package_dir = vendor_path / "pyperclip"
            package_dir.mkdir(parents=True)

            class FakeSpec:
                origin = str(package_dir / "__init__.py")
                submodule_search_locations = [str(package_dir)]

            with mock.patch.object(preflight.importlib.util, "find_spec", return_value=FakeSpec()):
                missing = preflight.missing_dependency_imports(["pyperclip"], vendor_path=vendor_path)

        self.assertEqual([], missing)

    def test_missing_dependency_imports_invalidates_cache_after_vendor_created(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            vendor_path = Path(temp_dir) / ".mykamus_vendor"
            module_name = "cacheprobe_mykamus"

            try:
                first_missing = preflight.missing_dependency_imports([module_name], vendor_path=vendor_path)
                package_dir = vendor_path / module_name
                package_dir.mkdir(parents=True)
                (package_dir / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
                second_missing = preflight.missing_dependency_imports([module_name], vendor_path=vendor_path)
            finally:
                while str(vendor_path) in sys.path:
                    sys.path.remove(str(vendor_path))
                sys.modules.pop(module_name, None)

        self.assertEqual([module_name], first_missing)
        self.assertEqual([], second_missing)

    def test_missing_data_files_no_longer_requires_en_id_sentences_txt(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            (base_dir / "en-id_dict.txt").write_text("dict", encoding="utf-8")
            (base_dir / "indonesiandictionary.pdf").write_text("pdf", encoding="utf-8")

            missing = preflight.missing_data_files(base_dir)

        self.assertEqual([], missing)

    def test_missing_data_files_reports_required_files_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            (base_dir / "en-id_dict.txt").write_text("dict", encoding="utf-8")

            missing = preflight.missing_data_files(base_dir)

        self.assertEqual(["indonesiandictionary.pdf"], missing)

    def test_sentence_dataset_errors_reports_missing_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)

            errors = preflight.sentence_dataset_errors(base_dir)

        self.assertTrue(any("manifest.json" in message for message in errors))

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

    def test_ensure_dependencies_does_not_install_when_local_imports_pass(self):
        messages = []
        with mock.patch.object(preflight, "read_requirements", return_value=["keyboard", "pypdf", "pyperclip"]), \
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
        missing_results = [["keyboard", "pypdf", "pyperclip"], []]

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "myKamus_setup.log"
            with mock.patch.object(preflight, "read_requirements", return_value=["keyboard", "pypdf", "pyperclip"]), \
                    mock.patch.object(
                        preflight,
                        "missing_dependency_imports",
                        side_effect=lambda _requirements: missing_results.pop(0),
                    ), \
                    mock.patch.object(preflight, "install_local_dependencies", return_value=True) as install:
                result = preflight.ensure_dependencies(
                    input_func=lambda _question: "y",
                    output_func=messages.append,
                    log_path=log_path,
                )

        self.assertTrue(result)
        install.assert_called_once_with(log_path=log_path)
        self.assertTrue(any("local Python packages" in message for message in messages))

    def test_ensure_dependencies_fails_when_user_declines_local_install(self):
        messages = []

        with mock.patch.object(preflight, "read_requirements", return_value=["keyboard", "pypdf", "pyperclip"]), \
                mock.patch.object(preflight, "missing_dependency_imports", return_value=["pyperclip"]), \
                mock.patch.object(preflight, "install_local_dependencies") as install:
            result = preflight.ensure_dependencies(
                input_func=lambda _question: "n",
                output_func=messages.append,
            )

        self.assertFalse(result)
        install.assert_not_called()
        self.assertTrue(any(
            "--target .mykamus_vendor --upgrade --force-reinstall" in message
            for message in messages
        ))

    def test_ensure_dependencies_failure_mentions_setup_log(self):
        messages = []

        with mock.patch.object(preflight, "read_requirements", return_value=["keyboard", "pypdf", "pyperclip"]), \
                mock.patch.object(preflight, "missing_dependency_imports", return_value=["pyperclip"]), \
                mock.patch.object(preflight, "install_local_dependencies", return_value=False):
            result = preflight.ensure_dependencies(
                input_func=lambda _question: "y",
                output_func=messages.append,
            )

        self.assertFalse(result)
        self.assertTrue(any("myKamus_setup.log" in message for message in messages))

    def test_ensure_dependencies_fails_when_packages_remain_missing_after_local_install(self):
        messages = []
        missing_results = [["keyboard", "pypdf", "pyperclip"], ["pyperclip"]]

        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "myKamus_setup.log"
            with mock.patch.object(preflight, "read_requirements", return_value=["keyboard", "pypdf", "pyperclip"]), \
                    mock.patch.object(
                        preflight,
                        "missing_dependency_imports",
                        side_effect=lambda _requirements: missing_results.pop(0),
                    ), \
                    mock.patch.object(preflight, "install_local_dependencies", return_value=True):
                result = preflight.ensure_dependencies(
                    input_func=lambda _question: "y",
                    output_func=messages.append,
                    log_path=log_path,
                )

            log_text = log_path.read_text(encoding="utf-8")

        self.assertFalse(result)
        self.assertTrue(any("- pyperclip" in message for message in messages))
        self.assertTrue(any("myKamus_setup.log" in message for message in messages))
        self.assertIn("Final local import check", log_text)
        self.assertIn("Missing packages: pyperclip", log_text)

    def test_install_dependencies_deletes_vendor_and_uses_force_reinstall_target(self):
        commands = []
        with tempfile.TemporaryDirectory() as temp_dir:
            base_dir = Path(temp_dir)
            vendor_path = base_dir / ".mykamus_vendor"
            vendor_path.mkdir()
            (vendor_path / "stale.txt").write_text("old", encoding="utf-8")
            requirements_path = base_dir / "requirements.txt"
            requirements_path.write_text("keyboard\npypdf\npyperclip\n", encoding="utf-8")

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

    def test_ensure_data_files_returns_true_when_files_exist(self):
        with mock.patch.object(preflight, "missing_data_files", return_value=[]), \
                mock.patch.object(preflight, "sentence_dataset_errors", return_value=[]):
            result = preflight.ensure_data_files(
                input_func=lambda _question: "n",
                output_func=lambda _message: None,
            )

        self.assertTrue(result)

    def test_ensure_data_files_fails_when_git_is_unavailable(self):
        messages = []

        with mock.patch.object(preflight, "missing_data_files", return_value=["en-id_dict.txt"]), \
                mock.patch.object(preflight, "sentence_dataset_errors", return_value=[]), \
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
        missing_results = [["en-id_dict.txt"], []]

        with mock.patch.object(
            preflight,
            "missing_data_files",
            side_effect=lambda: missing_results.pop(0),
        ), \
                mock.patch.object(preflight, "sentence_dataset_errors", return_value=[]), \
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

        with mock.patch.object(preflight, "missing_data_files", return_value=["en-id_dict.txt"]), \
                mock.patch.object(preflight, "sentence_dataset_errors", return_value=[]), \
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

        with mock.patch.object(preflight, "missing_data_files", return_value=["en-id_dict.txt"]), \
                mock.patch.object(preflight, "sentence_dataset_errors", return_value=[]), \
                mock.patch.object(preflight, "command_exists", return_value=True), \
                mock.patch.object(preflight, "run_command") as run_command:
            result = preflight.ensure_data_files(
                input_func=lambda _question: "n",
                output_func=messages.append,
            )

        self.assertFalse(result)
        run_command.assert_not_called()
        self.assertTrue(any("Cannot start until these data files are present" in message for message in messages))

    def test_ensure_data_files_reports_sentence_dataset_errors_without_git_lfs_pull(self):
        messages = []

        with mock.patch.object(preflight, "missing_data_files", return_value=[]), \
                mock.patch.object(preflight, "sentence_dataset_errors", return_value=["Sentence dataset is missing manifest.json."]), \
                mock.patch.object(preflight, "command_exists") as command_exists, \
                mock.patch.object(preflight, "run_command") as run_command:
            result = preflight.ensure_data_files(
                input_func=lambda _question: "y",
                output_func=messages.append,
            )

        self.assertFalse(result)
        command_exists.assert_not_called()
        run_command.assert_not_called()
        self.assertTrue(any("data/sentences" in message for message in messages))
        self.assertTrue(any("manifest.json" in message for message in messages))

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
