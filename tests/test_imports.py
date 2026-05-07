import importlib
import unittest


class ImportSafetyTests(unittest.TestCase):
    def test_legacy_launcher_import_has_no_side_effect_loop(self):
        module = importlib.import_module("myKamus_initialise")

        self.assertTrue(callable(module.main))

    def test_clean_text_import_does_not_require_tmx_file(self):
        module = importlib.import_module("clean_text")

        self.assertEqual("hello", module.remove_tags("<b>hello</b>"))


if __name__ == "__main__":
    unittest.main()
