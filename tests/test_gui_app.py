import unittest
from types import SimpleNamespace

from gui_app.app import main

gui_app = SimpleNamespace(main=main)


class GuiAppImportCoverageTests(unittest.TestCase):
    def test_main_is_callable(self):
        self.assertTrue(callable(gui_app.main))


if __name__ == "__main__":
    unittest.main()
