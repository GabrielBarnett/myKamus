import unittest

from gui_app.app import main


class GuiAppImportCoverageTests(unittest.TestCase):
    def test_main_is_callable(self):
        self.assertTrue(callable(main))


if __name__ == "__main__":
    unittest.main()
