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
