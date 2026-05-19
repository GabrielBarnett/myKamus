import importlib
import unittest

gui_app = importlib.import_module("gui_app.app")


class GuiAppImportCoverageTests(unittest.TestCase):
    def test_main_is_callable(self):
        self.assertTrue(callable(gui_app.main))


if __name__ == "__main__":
    unittest.main()
