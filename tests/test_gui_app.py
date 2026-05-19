import importlib
import unittest
from unittest import mock

gui_app = importlib.import_module("gui_app.app")


class GuiAppImportCoverageTests(unittest.TestCase):
    def test_main_is_callable(self):
        self.assertTrue(callable(gui_app.main))

    def test_require_tk_raises_clear_error_when_tkinter_missing(self):
        with mock.patch.object(gui_app, "TK_AVAILABLE", False):
            with self.assertRaisesRegex(RuntimeError, "tkinter is required"):
                gui_app.require_tk()

    def test_main_creates_tk_root_backend_window_and_enters_mainloop(self):
        root = mock.Mock()

        with mock.patch.object(gui_app, "require_tk") as require_tk, \
                mock.patch.object(gui_app.tk, "Tk", return_value=root) as tk_constructor, \
                mock.patch.object(gui_app, "GuiBackend", autospec=True) as backend_class, \
                mock.patch.object(gui_app, "MyKamusTkWindow", autospec=True) as window_class:
            gui_app.main()

        require_tk.assert_called_once_with()
        tk_constructor.assert_called_once_with()
        backend_class.assert_called_once_with()
        window_class.assert_called_once_with(root, backend_class.return_value)
        root.mainloop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
