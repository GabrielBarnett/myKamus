import sys

from gui_app.core.backend import GuiBackend

try:
    import tkinter as tk
except ImportError:  # pragma: no cover - depends on interpreter build
    tk = None
    TK_AVAILABLE = False
    MyKamusTkWindow = None
else:
    TK_AVAILABLE = True
    from gui_app.tk.main_window import MyKamusTkWindow


def require_tk():
    if not TK_AVAILABLE:
        raise RuntimeError(
            "tkinter is required to start the myKamus GUI. "
            "Install Python with tkinter support and try again."
        )


def main():
    require_tk()
    root = tk.Tk()
    backend = GuiBackend()
    MyKamusTkWindow(root, backend)
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
