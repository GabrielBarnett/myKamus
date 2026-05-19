"""Shared ttk theme helpers for Tk views."""

from tkinter import ttk


def apply_theme(root):
    style = ttk.Style(root)
    available_themes = set(style.theme_names())
    if "clam" in available_themes:
        style.theme_use("clam")

    background = "#f5f7fa"
    surface = "#ffffff"
    foreground = "#1f2933"
    muted = "#52606d"
    accent = "#3b82f6"
    border = "#d9e2ec"

    root.configure(background=background)

    style.configure(".", background=background, foreground=foreground)
    style.configure("TFrame", background=background)
    style.configure("App.TFrame", background=background)
    style.configure("Surface.TFrame", background=surface)
    style.configure("TLabel", background=background, foreground=foreground)
    style.configure("Muted.TLabel", background=background, foreground=muted)
    style.configure(
        "SectionTitle.TLabel",
        background=background,
        foreground=foreground,
        font=("TkDefaultFont", 11, "bold"),
    )
    style.configure(
        "Primary.TButton",
        background=accent,
        foreground="#ffffff",
        padding=(10, 6),
    )
    style.map(
        "Primary.TButton",
        background=[("active", "#2563eb")],
        foreground=[("disabled", "#dbeafe")],
    )
    style.configure(
        "Tool.TButton",
        background=surface,
        foreground=foreground,
        padding=(8, 4),
    )
    style.map(
        "Tool.TButton",
        background=[("active", "#e5edf5")],
    )
    style.configure(
        "TProgressbar",
        background=accent,
        troughcolor=surface,
        bordercolor=border,
        lightcolor=accent,
        darkcolor=accent,
    )
    style.configure(
        "Card.TFrame",
        background=surface,
        borderwidth=1,
        relief="solid",
    )
    return style
