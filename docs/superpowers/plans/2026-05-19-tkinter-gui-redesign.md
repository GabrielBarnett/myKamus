# Tkinter GUI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the PySide6 GUI with a Tkinter GUI that preserves myKamus behavior, removes the third-party GUI toolkit dependency, and ships a calmer search-first layout.

**Architecture:** Keep `gui_app/app.py` as the stable entry point, but move GUI logic into a toolkit-neutral core, a small threading/queue runtime layer, and a new `gui_app/tk/` package for the Tkinter presentation layer. Reuse the existing search/indexing code in `search_functions.py`, preserve launcher/config/data behavior, and migrate tests toward pure core logic plus small Tk smoke tests.

**Tech Stack:** Python standard library (`tkinter`, `tkinter.ttk`, `threading`, `queue`, `dataclasses`, `json`, `pathlib`, `unittest`, `unittest.mock`), existing repository modules (`search_functions.py`, `red_book_index.py`, `search_index.py`), Markdown docs.

---

## File Structure

- Create `gui_app/core/__init__.py`
  - Package marker for the toolkit-neutral core modules.
- Create `gui_app/core/view_model.py`
  - Pure GUI helpers extracted from `gui_app/app.py`: sentence-limit resolution, history, result shaping, status text, responsive breakpoint, and window-geometry parsing.
- Create `gui_app/core/config_store.py`
  - GUI settings dataclass and config read/write helpers around `config.json`.
- Create `gui_app/core/backend.py`
  - Toolkit-neutral adapters for config loading, index readiness, index building, and word search using existing `search_functions.py`.
- Create `gui_app/runtime/__init__.py`
  - Package marker for runtime helpers.
- Create `gui_app/runtime/tasks.py`
  - Background thread runner with queue-based result/progress/error messages and cancellation flags.
- Create `gui_app/tk/__init__.py`
  - Package marker for the Tkinter presentation layer.
- Create `gui_app/tk/theme.py`
  - Shared fonts, spacing, colors, and `ttk.Style` configuration.
- Create `gui_app/tk/widgets.py`
  - Reusable Tk widgets: scrollable results frame, selectable text block, section header, status strip, and recent-query row.
- Create `gui_app/tk/loading_view.py`
  - First-run indexing progress view.
- Create `gui_app/tk/main_window.py`
  - Main Tkinter window/controller with command strip, tools panel, results rendering, clipboard polling, search/index orchestration, and shutdown handling.
- Modify `gui_app/app.py`
  - Replace the PySide6 entry point with a Tkinter launcher and dependency guard for missing `tkinter`.
- Modify `gui_app/preflight.py`
  - Remove PySide6-specific dependency assumptions from launcher preflight text and requirement mapping.
- Modify `requirements.txt`
  - Remove `PySide6` while preserving non-GUI dependencies still used elsewhere.
- Modify `README.md`
  - Rewrite GUI sections to describe the Tkinter app, stable launch commands, and updated dependency story.
- Modify `tests/test_gui_app.py`
  - Retire Qt-specific smoke tests and move pure helper tests to the new core modules.
- Create `tests/test_gui_core.py`
  - Unit tests for view-model and config-store behavior.
- Create `tests/test_gui_runtime.py`
  - Tests for the thread/queue task runner.
- Create `tests/test_gui_tk.py`
  - Small Tk smoke and wiring tests for the loading view and main window.
- Modify `tests/test_gui_preflight.py`
  - Stop asserting PySide6-specific package behavior and verify the launcher/preflight no longer depends on Qt.

Do not change search semantics, data-file handling, CLI behavior, or the existing `Start myKamus.bat` / `python -m gui_app.app` entry points.

---

### Task 1: Extract Toolkit-Neutral View Models

**Files:**
- Create: `gui_app/core/__init__.py`
- Create: `gui_app/core/view_model.py`
- Create: `tests/test_gui_core.py`
- Modify: `tests/test_gui_app.py`

- [ ] **Step 1: Write failing core-view-model tests**

Create `tests/test_gui_core.py` with:

```python
import unittest

from gui_app.core import view_model


class ViewModelTests(unittest.TestCase):
    def test_load_all_uses_gui_cap(self):
        config = {"sentence_limit": 4, "gui": {"load_all_sentence_limit": 25}}
        self.assertEqual(
            25,
            view_model.resolve_sentence_limit(config, compact_mode=False, load_all=True),
        )

    def test_search_history_deduplicates_and_caps_results(self):
        history = []
        for index in range(14):
            history = view_model.add_search_history(history, f"word{index}", limit=12)
        history = view_model.add_search_history(history, "word7", limit=12)
        self.assertEqual("word7", history[0])
        self.assertEqual(12, len(history))
        self.assertEqual(1, history.count("word7"))

    def test_result_view_model_orders_sections_for_rendering(self):
        result = {
            "query": "mengatakan",
            "definitions": ["mengatakan say"],
            "red_book_definitions": [{"headword": "mengatakan", "definition": "to say", "page": 475}],
            "sentences": [{"index": 1, "match": "Saya mengatakan hal itu.", "translation": "I said that."}],
            "message": None,
            "sentence_limit": 1,
            "sentences_truncated": False,
        }
        model = view_model.build_result_view_model(result)
        self.assertEqual(
            ["red_book", "definitions", "sentences"],
            [section["kind"] for section in model["sections"]],
        )

    def test_window_size_parser_respects_minimums(self):
        self.assertEqual((520, 420), view_model.parse_window_size("300x200"))
```

Trim `tests/test_gui_app.py` down to a placeholder import-coverage file:

```python
import unittest

from gui_app import app as gui_app


class GuiEntryPointImportTests(unittest.TestCase):
    def test_module_exposes_main(self):
        self.assertTrue(callable(gui_app.main))
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_core.py
```

Expected: `ModuleNotFoundError` for `gui_app.core.view_model`.

- [ ] **Step 3: Implement `gui_app/core/view_model.py`**

Create `gui_app/core/__init__.py`:

```python
"""Toolkit-neutral GUI core helpers for myKamus."""
```

Create `gui_app/core/view_model.py`:

```python
from search_functions import normalize_query


HISTORY_LIMIT = 12
NARROW_LAYOUT_WIDTH = 760


def resolve_sentence_limit(config, compact_mode, load_all):
    if load_all:
        gui_config = config.get("gui", {})
        return gui_config.get("load_all_sentence_limit", 200)
    if compact_mode:
        return 1
    return config.get("sentence_limit")


def should_refocus_search(origin):
    return origin in {"manual", "button", "load_all", "history"}


def should_use_narrow_layout(width):
    return int(width) < NARROW_LAYOUT_WIDTH


def format_bytes(byte_count):
    if byte_count >= 1024 * 1024:
        return f"{byte_count / (1024 * 1024):.1f} MB"
    if byte_count >= 1024:
        return f"{byte_count / 1024:.1f} KB"
    return f"{byte_count} bytes"


def add_search_history(history, query, limit=HISTORY_LIMIT):
    normalized = normalize_query(query)
    if not normalized:
        return list(history)
    next_history = [item for item in history if item.casefold() != normalized.casefold()]
    next_history.insert(0, normalized)
    return next_history[:limit]


def build_result_view_model(result, load_all=False):
    if result["message"]:
        return {
            "query": result["query"],
            "message": result["message"],
            "sections": [],
            "counts": {"definitions": 0, "red_book": 0, "sentences": 0},
            "sentences_truncated": False,
            "sentence_limit": result.get("sentence_limit"),
        }

    red_book_items = [
        {
            "kind": "red_book_definition",
            "headword": item.get("headword", ""),
            "definition": item.get("definition", ""),
            "page": item.get("page"),
            "copy_text": f"{item.get('headword', '')}\n{item.get('definition', '')}".strip(),
        }
        for item in result.get("red_book_definitions", [])
    ]
    sections = []
    if red_book_items:
        sections.append({"kind": "red_book", "title": "Red Book Results", "items": red_book_items})
    sections.append(
        {
            "kind": "definitions",
            "title": "Word Translations",
            "items": [
                {"kind": "translation", "index": index, "text": text, "copy_text": text}
                for index, text in enumerate(result["definitions"], start=1)
            ],
            "empty_text": "No dictionary entries found.",
        }
    )
    sections.append(
        {
            "kind": "sentences",
            "title": "All Example Sentences" if load_all else "Example Sentences",
            "items": [
                {
                    "kind": "sentence",
                    "index": item["index"],
                    "match": item.get("match", ""),
                    "translation": item.get("translation", ""),
                    "matched_language": item.get("matched_language"),
                    "copy_text": f"{item.get('match', '')}\n{item.get('translation', '')}".strip(),
                }
                for item in result["sentences"]
            ],
            "empty_text": "No example sentences found.",
        }
    )
    return {
        "query": result["query"],
        "message": None,
        "sections": sections,
        "counts": {
            "definitions": len(result["definitions"]),
            "red_book": len(red_book_items),
            "sentences": len(result["sentences"]),
        },
        "sentences_truncated": result["sentences_truncated"],
        "sentence_limit": result["sentence_limit"],
    }


def status_text_for_result(view_model, load_all=False):
    if view_model["message"]:
        return view_model["message"]
    counts = view_model["counts"]
    if view_model["sentences_truncated"]:
        return (
            "Showing the first "
            + str(view_model["sentence_limit"])
            + " matching sentence pairs. Narrow the query for fewer results."
        )
    if load_all:
        return "Loaded " + str(counts["sentences"]) + " matching sentence pairs."
    return (
        "Found "
        + str(counts["red_book"])
        + " Red Book results, "
        + str(counts["definitions"])
        + " dictionary entries, and "
        + str(counts["sentences"])
        + " sentence pairs."
    )


def parse_window_size(value, default=(900, 700)):
    try:
        width, height = str(value).lower().split("x", 1)
        return max(520, int(width)), max(420, int(height))
    except (TypeError, ValueError):
        return default


def parse_window_position(value, default=(100, 100)):
    try:
        text = str(value)
        if not text.startswith("+"):
            return default
        x_text, y_text = text[1:].split("+", 1)
        return int(x_text), int(y_text)
    except (TypeError, ValueError):
        return default
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_core.py
python -B -m unittest discover -s tests -p test_gui_app.py
```

Expected: both test files pass.

- [ ] **Step 5: Commit the view-model extraction**

Run:

```bash
git add gui_app/core/__init__.py gui_app/core/view_model.py tests/test_gui_core.py tests/test_gui_app.py
git commit -m "feat: extract GUI view models"
```

Expected: commit contains only the new core module and test migration.

---

### Task 2: Add Config And Backend Boundaries

**Files:**
- Create: `gui_app/core/config_store.py`
- Create: `gui_app/core/backend.py`
- Modify: `tests/test_gui_core.py`

- [ ] **Step 1: Add failing tests for config persistence and backend wrappers**

Append to `tests/test_gui_core.py`:

```python
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from gui_app.core import backend, config_store


class ConfigStoreTests(unittest.TestCase):
    def test_build_gui_config_update_preserves_existing_keys(self):
        config = {"sentence_limit": 4, "gui": {"load_all_sentence_limit": 25}}
        updated = config_store.build_gui_config_update(
            config,
            always_on_top=True,
            compact_mode=False,
            window_size="900x700",
            window_position="+100+100",
        )
        self.assertEqual(25, updated["gui"]["load_all_sentence_limit"])
        self.assertTrue(updated["gui"]["always_on_top"])

    def test_write_config_persists_trailing_newline(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            config_store.write_config(path, {"gui": {"always_on_top": True}})
            text = path.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"))


class BackendTests(unittest.TestCase):
    def test_backend_search_delegates_to_search_functions(self):
        service = backend.GuiBackend(
            load_config_func=lambda: {"sentence_limit": 4},
            indexes_are_ready_func=lambda: True,
            ensure_sentence_index_func=lambda progress_callback=None: None,
            ensure_red_book_index_func=lambda progress_callback=None: None,
            search_for_word_data_func=lambda query, sentence_limit: {"query": query, "sentence_limit": sentence_limit},
        )
        result = service.search("kata", sentence_limit=4)
        self.assertEqual("kata", result["query"])
        self.assertEqual(4, result["sentence_limit"])
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_core.py
```

Expected: import failures for `config_store` and `backend`.

- [ ] **Step 3: Implement config and backend modules**

Create `gui_app/core/config_store.py`:

```python
import json
from pathlib import Path


def build_gui_config_update(config, *, always_on_top, compact_mode, window_size, window_position):
    next_config = dict(config)
    gui_config = dict(next_config.get("gui", {}))
    gui_config.update(
        {
            "always_on_top": always_on_top,
            "compact_mode": compact_mode,
            "window_size": window_size,
            "window_position": window_position,
        }
    )
    next_config["gui"] = gui_config
    return next_config


def write_config(path, config):
    with Path(path).open("w", encoding="utf-8") as config_file:
        json.dump(config, config_file, indent=2)
        config_file.write("\n")
```

Create `gui_app/core/backend.py`:

```python
from dataclasses import dataclass

from search_functions import (
    ensure_red_book_index,
    ensure_sentence_index,
    is_red_book_index_valid,
    is_sentence_index_valid,
    load_config,
    search_for_word_data,
)


@dataclass
class GuiBackend:
    load_config_func: callable = load_config
    indexes_are_ready_func: callable = lambda: is_sentence_index_valid() and is_red_book_index_valid()
    ensure_sentence_index_func: callable = ensure_sentence_index
    ensure_red_book_index_func: callable = ensure_red_book_index
    search_for_word_data_func: callable = search_for_word_data

    def load_config(self):
        return self.load_config_func()

    def indexes_are_ready(self):
        return self.indexes_are_ready_func()

    def build_indexes(self, progress_callback):
        self.ensure_sentence_index_func(progress_callback=progress_callback)
        self.ensure_red_book_index_func(progress_callback=progress_callback)

    def search(self, query, sentence_limit):
        return self.search_for_word_data_func(query, sentence_limit=sentence_limit)
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_core.py
```

Expected: all `test_gui_core.py` tests pass.

- [ ] **Step 5: Commit config/backend boundaries**

Run:

```bash
git add gui_app/core/config_store.py gui_app/core/backend.py tests/test_gui_core.py
git commit -m "feat: add GUI config and backend adapters"
```

Expected: commit contains only config/backend boundary work.

---

### Task 3: Build The Background Task Runner

**Files:**
- Create: `gui_app/runtime/__init__.py`
- Create: `gui_app/runtime/tasks.py`
- Create: `tests/test_gui_runtime.py`

- [ ] **Step 1: Write failing runtime tests**

Create `tests/test_gui_runtime.py`:

```python
import queue
import threading
import unittest

from gui_app.runtime import tasks


class BackgroundTaskRunnerTests(unittest.TestCase):
    def test_runner_emits_result_message(self):
        message_queue = queue.Queue()
        runner = tasks.BackgroundTaskRunner(message_queue)

        runner.start(
            token=7,
            kind="search",
            target=lambda cancel_event, emit_progress: {"query": "kata"},
        )
        message = message_queue.get(timeout=2)

        self.assertEqual("result", message["event"])
        self.assertEqual(7, message["token"])
        self.assertEqual({"query": "kata"}, message["payload"])

    def test_runner_emits_progress_before_result(self):
        message_queue = queue.Queue()
        runner = tasks.BackgroundTaskRunner(message_queue)

        def task(cancel_event, emit_progress):
            emit_progress({"percent": 50.0})
            return "done"

        runner.start(token=8, kind="index", target=task)
        first = message_queue.get(timeout=2)
        second = message_queue.get(timeout=2)

        self.assertEqual("progress", first["event"])
        self.assertEqual("result", second["event"])

    def test_cancel_sets_event_for_running_task(self):
        message_queue = queue.Queue()
        runner = tasks.BackgroundTaskRunner(message_queue)
        cancelled = []
        gate = threading.Event()

        def task(cancel_event, emit_progress):
            gate.set()
            cancel_event.wait(timeout=2)
            cancelled.append(cancel_event.is_set())
            return "done"

        runner.start(token=9, kind="search", target=task)
        gate.wait(timeout=2)
        runner.cancel(9)
        message_queue.get(timeout=2)

        self.assertEqual([True], cancelled)

    def test_join_all_waits_for_running_threads(self):
        message_queue = queue.Queue()
        runner = tasks.BackgroundTaskRunner(message_queue)
        gate = threading.Event()

        def task(cancel_event, emit_progress):
            gate.set()
            cancel_event.wait(timeout=1)
            return "done"

        runner.start(token=10, kind="search", target=task)
        gate.wait(timeout=2)
        runner.cancel(10)
        runner.join_all(timeout=2)

        self.assertEqual({}, runner._threads)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_runtime.py
```

Expected: `ModuleNotFoundError` for `gui_app.runtime.tasks`.

- [ ] **Step 3: Implement the queue-based task runner**

Create `gui_app/runtime/__init__.py`:

```python
"""Runtime helpers for Tk background work."""
```

Create `gui_app/runtime/tasks.py`:

```python
import queue
import threading
import traceback


class BackgroundTaskRunner:
    def __init__(self, message_queue=None):
        self.message_queue = message_queue or queue.Queue()
        self._cancel_events = {}
        self._threads = {}

    def start(self, *, token, kind, target):
        cancel_event = threading.Event()
        self._cancel_events[token] = cancel_event

        def emit_progress(payload):
            self.message_queue.put(
                {"event": "progress", "token": token, "kind": kind, "payload": payload}
            )

        def run():
            try:
                payload = target(cancel_event, emit_progress)
                self.message_queue.put(
                    {"event": "result", "token": token, "kind": kind, "payload": payload}
                )
            except Exception as exc:
                self.message_queue.put(
                    {
                        "event": "error",
                        "token": token,
                        "kind": kind,
                        "error": exc,
                        "traceback": traceback.format_exc(),
                    }
                )
            finally:
                self._cancel_events.pop(token, None)
                self._threads.pop(token, None)

        thread = threading.Thread(target=run, daemon=True)
        self._threads[token] = thread
        thread.start()
        return thread

    def cancel(self, token):
        cancel_event = self._cancel_events.get(token)
        if cancel_event is not None:
            cancel_event.set()

    def cancel_all(self):
        for token in list(self._cancel_events):
            self.cancel(token)

    def join_all(self, timeout=1.0):
        for token, thread in list(self._threads.items()):
            thread.join(timeout=timeout)
            if not thread.is_alive():
                self._threads.pop(token, None)
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_runtime.py
```

Expected: all runtime tests pass.

- [ ] **Step 5: Commit the runtime layer**

Run:

```bash
git add gui_app/runtime/__init__.py gui_app/runtime/tasks.py tests/test_gui_runtime.py
git commit -m "feat: add Tk background task runner"
```

Expected: commit contains only the runtime layer and its tests.

---

### Task 4: Add Tk Theme, Shared Widgets, And Loading View

**Files:**
- Create: `gui_app/tk/__init__.py`
- Create: `gui_app/tk/theme.py`
- Create: `gui_app/tk/widgets.py`
- Create: `gui_app/tk/loading_view.py`
- Create: `tests/test_gui_tk.py`

- [ ] **Step 1: Write failing Tk smoke tests**

Create `tests/test_gui_tk.py`:

```python
import tkinter as tk
import unittest
from unittest import mock

from gui_app.tk import loading_view, theme, widgets


class TkSmokeTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()

    def tearDown(self):
        if hasattr(self, "root"):
            self.root.destroy()

    def test_theme_configures_app_style(self):
        style = theme.apply_theme(self.root)
        self.assertIsNotNone(style)

    def test_loading_view_updates_percent_and_status(self):
        view = loading_view.LoadingView(self.root)
        view.update_progress({"title": "Building sentence search index...", "percent": 50.0, "processed_pages": 5, "total_pages": 10})
        self.assertEqual("50%", view.percent_var.get())
        view.show_ready()
        self.assertEqual("Search index ready.", view.status_var.get())

    def test_selectable_text_renders_text(self):
        block = widgets.SelectableText(self.root, text="Saya mengatakan hal itu.")
        self.assertIn("mengatakan", block.text.get("1.0", "end"))
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_tk.py
```

Expected: `ModuleNotFoundError` for `gui_app.tk`.

- [ ] **Step 3: Implement theme, widgets, and loading view**

Create `gui_app/tk/__init__.py`:

```python
"""Tkinter presentation layer for the myKamus GUI."""
```

Create `gui_app/tk/theme.py`:

```python
from tkinter import ttk


def apply_theme(root):
    root.option_add("*Font", "TkDefaultFont 10")
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")
    style.configure("App.TFrame", background="#f6f7f4")
    style.configure("Surface.TFrame", background="#ffffff")
    style.configure("SectionTitle.TLabel", background="#f6f7f4", foreground="#17201b", font=("TkDefaultFont", 11, "bold"))
    style.configure("Muted.TLabel", background="#f6f7f4", foreground="#5f6a64")
    style.configure("Primary.TButton", padding=(12, 8))
    style.configure("Tool.TButton", padding=(10, 6))
    return style
```

Create `gui_app/tk/widgets.py`:

```python
import tkinter as tk
from tkinter import ttk


class ScrollableFrame(ttk.Frame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0, background="#f6f7f4")
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas, style="App.TFrame")
        self.window_id = self.canvas.create_window((0, 0), window=self.content, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.content.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self.window_id, width=event.width))


class SelectableText(ttk.Frame):
    def __init__(self, master, text, height=2, **kwargs):
        super().__init__(master, **kwargs)
        self.text = tk.Text(self, wrap="word", height=height, borderwidth=0, highlightthickness=0)
        self.text.insert("1.0", text)
        self.text.configure(state="disabled", background="#ffffff", foreground="#17201b")
        self.text.pack(fill="both", expand=True)


class SectionHeader(ttk.Frame):
    def __init__(self, master, title, count, **kwargs):
        super().__init__(master, **kwargs)
        ttk.Label(self, text=title, style="SectionTitle.TLabel").pack(side="left")
        ttk.Label(self, text=str(count), style="Muted.TLabel").pack(side="left", padx=(8, 0))
```

Create `gui_app/tk/loading_view.py`:

```python
import tkinter as tk
from tkinter import ttk

from gui_app.core.view_model import format_bytes


class LoadingView(ttk.Frame):
    def __init__(self, master):
        super().__init__(master, style="App.TFrame", padding=24)
        self.title_var = tk.StringVar(value="Building search index...")
        self.percent_var = tk.StringVar(value="0%")
        self.detail_var = tk.StringVar(value="Preparing corpus...")
        self.status_var = tk.StringVar(value="This only happens when the data changes.")
        ttk.Label(self, textvariable=self.title_var, style="SectionTitle.TLabel").pack(anchor="w")
        ttk.Label(self, textvariable=self.percent_var, style="SectionTitle.TLabel").pack(anchor="w", pady=(8, 0))
        self.progress = ttk.Progressbar(self, maximum=100)
        self.progress.pack(fill="x", pady=(12, 12))
        ttk.Label(self, textvariable=self.detail_var, style="Muted.TLabel").pack(anchor="w")
        ttk.Label(self, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w", pady=(4, 0))

    def update_progress(self, progress):
        percent = float(progress.get("percent", 0.0))
        self.title_var.set(progress.get("title", "Building search index..."))
        self.percent_var.set(f"{percent:.0f}%")
        self.progress["value"] = percent
        processed_pages = progress.get("processed_pages")
        total_pages = progress.get("total_pages")
        if processed_pages is not None and total_pages is not None:
            self.detail_var.set(f"Processed page {processed_pages} of {total_pages}")
        else:
            self.detail_var.set(
                "Processed "
                + format_bytes(int(progress.get("processed_bytes", 0)))
                + " of "
                + format_bytes(int(progress.get("total_bytes", 0)))
            )

    def show_error(self):
        self.status_var.set("Index build failed. Searches will use fallback mode.")

    def show_ready(self):
        self.percent_var.set("100%")
        self.progress["value"] = 100
        self.status_var.set("Search index ready.")
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_tk.py
```

Expected: Tk tests pass or skip cleanly when no display is available.

- [ ] **Step 5: Commit Tk building blocks**

Run:

```bash
git add gui_app/tk/__init__.py gui_app/tk/theme.py gui_app/tk/widgets.py gui_app/tk/loading_view.py tests/test_gui_tk.py
git commit -m "feat: add Tk theme and shared widgets"
```

Expected: commit contains only the new Tk foundation.

---

### Task 5: Build The Main Tk Window Shell

**Files:**
- Create: `gui_app/tk/main_window.py`
- Modify: `tests/test_gui_tk.py`

- [ ] **Step 1: Add failing main-window shell tests**

Append to `tests/test_gui_tk.py`:

```python
from gui_app.core.backend import GuiBackend
from gui_app.tk import main_window


class TkMainWindowShellTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.root.withdraw()

    def tearDown(self):
        if hasattr(self, "root"):
            self.root.destroy()

    def test_main_window_builds_search_first_layout(self):
        backend = GuiBackend(
            load_config_func=lambda: {
                "sentence_limit": 4,
                "poll_interval": 0.1,
                "gui": {"always_on_top": False, "compact_mode": False, "window_size": "900x700", "window_position": "+100+100", "load_all_sentence_limit": 25, "search_status_delay_ms": 200},
            },
            indexes_are_ready_func=lambda: True,
        )
        window = main_window.MyKamusTkWindow(self.root, backend=backend)
        self.assertEqual("myKamus", self.root.title())
        self.assertTrue(hasattr(window, "search_entry"))
        self.assertTrue(hasattr(window, "tools_button"))
        self.assertTrue(hasattr(window, "results_frame"))

    def test_tools_panel_toggles_visibility(self):
        backend = GuiBackend(load_config_func=lambda: {"sentence_limit": 4, "poll_interval": 0.1, "gui": {}}, indexes_are_ready_func=lambda: True)
        window = main_window.MyKamusTkWindow(self.root, backend=backend)
        before = window.tools_visible
        window.toggle_tools()
        self.assertNotEqual(before, window.tools_visible)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_tk.py
```

Expected: import failure for `gui_app.tk.main_window`.

- [ ] **Step 3: Implement the main window shell**

Create `gui_app/tk/main_window.py` with an initial shell:

```python
import queue
import tkinter as tk
from tkinter import ttk

from gui_app.core import view_model
from gui_app.runtime.tasks import BackgroundTaskRunner
from gui_app.tk.loading_view import LoadingView
from gui_app.tk.theme import apply_theme
from gui_app.tk.widgets import ScrollableFrame


class MyKamusTkWindow:
    def __init__(self, root, backend):
        self.root = root
        self.backend = backend
        self.config = backend.load_config()
        self.gui_config = self.config.get("gui", {})
        self.message_queue = queue.Queue()
        self.runner = BackgroundTaskRunner(self.message_queue)
        self.tools_visible = False
        self.root.title("myKamus")
        self.root.minsize(520, 420)
        apply_theme(root)
        if backend.indexes_are_ready():
            self.build_main_ui()
        else:
            self.loading_view = LoadingView(root)
            self.loading_view.pack(fill="both", expand=True)

    def build_main_ui(self):
        self.container = ttk.Frame(self.root, style="App.TFrame", padding=16)
        self.container.pack(fill="both", expand=True)
        command = ttk.Frame(self.container, style="Surface.TFrame", padding=12)
        command.pack(fill="x")
        self.search_entry = ttk.Entry(command)
        self.search_entry.grid(row=0, column=0, sticky="ew")
        self.search_button = ttk.Button(command, text="Search")
        self.search_button.grid(row=0, column=1, padx=(8, 0))
        self.tools_button = ttk.Button(command, text="Tools", command=self.toggle_tools)
        self.tools_button.grid(row=0, column=2, padx=(8, 0))
        command.grid_columnconfigure(0, weight=1)
        self.status_var = tk.StringVar(value="")
        ttk.Label(self.container, textvariable=self.status_var, style="Muted.TLabel").pack(anchor="w", pady=(8, 0))
        self.recent_row = ttk.Frame(self.container, style="App.TFrame")
        self.recent_row.pack(fill="x", pady=(8, 0))
        self.body = ttk.Frame(self.container, style="App.TFrame")
        self.body.pack(fill="both", expand=True, pady=(12, 0))
        self.tools_panel = ttk.Frame(self.body, style="Surface.TFrame", padding=12)
        self.results_frame = ScrollableFrame(self.body)
        self.results_frame.pack(side="left", fill="both", expand=True)

    def toggle_tools(self):
        self.tools_visible = not self.tools_visible
        if self.tools_visible:
            self.tools_panel.pack(side="right", fill="y", padx=(12, 0))
        else:
            self.tools_panel.pack_forget()
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_tk.py
```

Expected: shell tests pass.

- [ ] **Step 5: Commit the Tk shell**

Run:

```bash
git add gui_app/tk/main_window.py tests/test_gui_tk.py
git commit -m "feat: build Tk main window shell"
```

Expected: commit contains only the initial main-window shell.

---

### Task 6: Wire Search, History, Clipboard, And Results

**Files:**
- Modify: `gui_app/tk/main_window.py`
- Modify: `gui_app/tk/widgets.py`
- Modify: `tests/test_gui_tk.py`

- [ ] **Step 1: Add failing behavior tests for search and history**

Append to `tests/test_gui_tk.py`:

```python
    def test_manual_search_updates_recent_history_and_status(self):
        search_calls = []
        backend = GuiBackend(
            load_config_func=lambda: {
                "sentence_limit": 4,
                "poll_interval": 0.1,
                "gui": {"always_on_top": False, "compact_mode": False, "window_size": "900x700", "window_position": "+100+100", "load_all_sentence_limit": 25, "search_status_delay_ms": 0},
            },
            indexes_are_ready_func=lambda: True,
            search_for_word_data_func=lambda query, sentence_limit: {
                "query": query,
                "definitions": ["mengatakan say"],
                "red_book_definitions": [],
                "sentences": [],
                "message": None,
                "sentence_limit": sentence_limit,
                "sentences_truncated": False,
            },
        )
        window = main_window.MyKamusTkWindow(self.root, backend=backend)
        window.search_entry.insert(0, "mengatakan")
        window.on_manual_search()
        self.root.update()
        self.root.update()
        self.assertIn("Found", window.status_var.get())
        self.assertEqual(["mengatakan"], window.search_history)

    def test_clipboard_poll_triggers_search_when_value_changes(self):
        calls = []
        backend = GuiBackend(
            load_config_func=lambda: {"sentence_limit": 4, "poll_interval": 0.1, "gui": {}},
            indexes_are_ready_func=lambda: True,
            search_for_word_data_func=lambda query, sentence_limit: calls.append((query, sentence_limit)) or {
                "query": query,
                "definitions": [],
                "red_book_definitions": [],
                "sentences": [],
                "message": "No matches found.",
                "sentence_limit": sentence_limit,
                "sentences_truncated": False,
            },
        )
        window = main_window.MyKamusTkWindow(self.root, backend=backend)
        window.clipboard_value = ""
        window.read_clipboard = lambda: "kata"
        window.poll_clipboard()
        self.root.update()
        self.assertEqual("kata", calls[0][0])
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_tk.py
```

Expected: failures for missing `on_manual_search`, `poll_clipboard`, history storage, and result rendering.

- [ ] **Step 3: Implement the search and clipboard flow**

In `gui_app/tk/main_window.py`, add the missing controller behavior.

Replace the import section with:

```python
from gui_app.core.config_store import build_gui_config_update, write_config
from gui_app.core.view_model import (
    add_search_history,
    build_result_view_model,
    parse_window_position,
    parse_window_size,
    resolve_sentence_limit,
    should_refocus_search,
    should_use_narrow_layout,
    status_text_for_result,
)
from gui_app.tk.widgets import ScrollableFrame, SectionHeader, SelectableText
```

At the end of `build_main_ui()`, append:

```python
        self.search_history = []
        self.clipboard_value = self.read_clipboard()
        self.compact_mode_var = tk.BooleanVar(value=self.gui_config.get("compact_mode", False))
        self.always_on_top_var = tk.BooleanVar(value=self.gui_config.get("always_on_top", True))
        self.results_content = self.results_frame.content
        self.search_button.configure(command=self.on_manual_search)
        self.search_entry.bind("<Return>", lambda _event: self.on_manual_search())
        self.root.bind("<Escape>", lambda _event: self.clear_search())
        self.root.bind("<Control-l>", lambda _event: self.focus_search(select_text=True))
        self.root.bind("<Control-f>", lambda _event: self.focus_search(select_text=True))
        self.root.bind("<Configure>", self.on_resize)
        self.root.after(max(100, int(float(self.config.get("poll_interval", 0.1)) * 1000)), self.poll_clipboard_loop)
        self.apply_window_settings()
        self.run_search(self.clipboard_value, origin="startup")
```

Add these methods below `build_main_ui()`:

```python
    def read_clipboard(self):
        try:
            return self.root.clipboard_get()
        except tk.TclError:
            return ""

    def on_manual_search(self):
        query = self.search_entry.get().strip()
        self.run_search(query, origin="manual")

    def clear_search(self):
        self.search_entry.delete(0, "end")
        self.focus_search(select_text=False)

    def focus_search(self, select_text):
        self.search_entry.focus_set()
        if select_text:
            self.search_entry.selection_range(0, "end")

    def poll_clipboard_loop(self):
        self.poll_clipboard()
        self.root.after(max(100, int(float(self.config.get("poll_interval", 0.1)) * 1000)), self.poll_clipboard_loop)

    def poll_clipboard(self):
        current = self.read_clipboard()
        if current != self.clipboard_value:
            self.clipboard_value = current
            self.run_search(current, origin="clipboard")

    def run_search(self, query, *, load_all=False, origin="manual"):
        sentence_limit = resolve_sentence_limit(self.config, self.compact_mode_var.get(), load_all)
        self.active_search_token = getattr(self, "active_search_token", 0) + 1
        token = self.active_search_token
        self.status_var.set("Searching...")
        self.runner.start(
            token=token,
            kind="search",
            target=lambda cancel_event, emit_progress: self.backend.search(query, sentence_limit=sentence_limit),
        )
        self.root.after(10, self.drain_messages)
        self._pending_origin = origin
        self._pending_load_all = load_all
```

Replace `drain_messages()` with:

```python
    def drain_messages(self):
        processed = False
        while True:
            try:
                message = self.message_queue.get_nowait()
            except queue.Empty:
                break
            processed = True
            if message["kind"] == "search" and message["token"] == self.active_search_token:
                if message["event"] == "result":
                    self.finish_search(message["payload"], origin=self._pending_origin, load_all=self._pending_load_all)
                elif message["event"] == "error":
                    self.status_var.set("Search failed.")
        if not processed:
            self.root.after(10, self.drain_messages)
```

Add the result-finalization and rendering methods below `drain_messages()`:

```python
    def finish_search(self, result, *, origin, load_all):
        if origin in {"manual", "button", "load_all", "history"}:
            self.search_history = add_search_history(self.search_history, result["query"])
        model = build_result_view_model(result, load_all=load_all)
        self.render_results(model)
        self.status_var.set(status_text_for_result(model, load_all=load_all))
        if should_refocus_search(origin):
            self.root.after(0, lambda: self.focus_search(select_text=True))

    def render_results(self, model):
        for child in self.results_content.winfo_children():
            child.destroy()
        if model["message"]:
            ttk.Label(self.results_content, text=model["message"], style="Muted.TLabel").pack(anchor="w", pady=(0, 12))
            return
        for section in model["sections"]:
            SectionHeader(self.results_content, section["title"], len(section["items"])).pack(fill="x", pady=(0, 8))
            if not section["items"]:
                ttk.Label(self.results_content, text=section.get("empty_text", ""), style="Muted.TLabel").pack(anchor="w", pady=(0, 12))
                continue
            for item in section["items"]:
                text = item.get("definition") or item.get("text") or f"{item.get('match', '')}\n{item.get('translation', '')}".strip()
                SelectableText(self.results_content, text=text).pack(fill="x", pady=(0, 8))
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_tk.py
```

Expected: new search/history/clipboard tests pass.

- [ ] **Step 5: Commit the search flow**

Run:

```bash
git add gui_app/tk/main_window.py gui_app/tk/widgets.py tests/test_gui_tk.py
git commit -m "feat: wire Tk search and clipboard flows"
```

Expected: commit contains only the Tk interaction flow.

---

### Task 7: Add Indexing Startup, Layout Responsiveness, And Shutdown

**Files:**
- Modify: `gui_app/tk/main_window.py`
- Modify: `tests/test_gui_tk.py`

- [ ] **Step 1: Add failing tests for loading flow, narrow layout, and close handling**

Append to `tests/test_gui_tk.py`:

```python
    def test_index_build_path_swaps_loading_view_for_main_ui(self):
        progress_messages = []

        def build_indexes(progress_callback):
            progress_callback({"title": "Building sentence search index...", "percent": 100.0, "processed_pages": 1, "total_pages": 1})

        backend = GuiBackend(
            load_config_func=lambda: {"sentence_limit": 4, "poll_interval": 0.1, "gui": {}},
            indexes_are_ready_func=lambda: False,
            ensure_sentence_index_func=lambda progress_callback=None: build_indexes(progress_callback),
            ensure_red_book_index_func=lambda progress_callback=None: None,
            search_for_word_data_func=lambda query, sentence_limit: {"query": query, "definitions": [], "red_book_definitions": [], "sentences": [], "message": "No matches found.", "sentence_limit": sentence_limit, "sentences_truncated": False},
        )
        window = main_window.MyKamusTkWindow(self.root, backend=backend)
        self.root.update()
        self.root.update()
        self.assertTrue(hasattr(window, "container"))

    def test_resize_sets_narrow_layout_flag(self):
        backend = GuiBackend(load_config_func=lambda: {"sentence_limit": 4, "poll_interval": 0.1, "gui": {}}, indexes_are_ready_func=lambda: True)
        window = main_window.MyKamusTkWindow(self.root, backend=backend)
        event = mock.Mock()
        event.width = 600
        window.on_resize(event)
        self.assertTrue(window.narrow_layout)

    def test_close_cancels_background_tasks_and_writes_config(self):
        backend = GuiBackend(load_config_func=lambda: {"sentence_limit": 4, "poll_interval": 0.1, "gui": {}}, indexes_are_ready_func=lambda: True)
        window = main_window.MyKamusTkWindow(self.root, backend=backend)
        calls = []
        window.runner.cancel_all = lambda: calls.append("cancel")
        window.runner.join_all = lambda timeout=2: calls.append("join")
        window.write_window_config = lambda: calls.append("write")
        window.on_close()
        self.assertEqual(["cancel", "join", "write"], calls)
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_tk.py
```

Expected: failures for missing index-build path, resize handling, or close handling.

- [ ] **Step 3: Implement loading, responsive layout, and shutdown behavior**

Extend `gui_app/tk/main_window.py`.

At the top of `__init__()`, after `self.runner = BackgroundTaskRunner(self.message_queue)`, add:

```python
        self.narrow_layout = False
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        if backend.indexes_are_ready():
            self.build_main_ui()
        else:
            self.loading_view = LoadingView(root)
            self.loading_view.pack(fill="both", expand=True)
            self.start_index_build()
```

Add these methods below `__init__()`:

```python
    def start_index_build(self):
        self.runner.start(
            token=1,
            kind="index",
            target=self._run_index_build,
        )
        self.root.after(10, self.drain_messages)

    def _run_index_build(self, cancel_event, emit_progress):
        def progress_callback(progress):
            emit_progress(progress)
        self.backend.build_indexes(progress_callback)
        return {"ready": True}
```

Replace `drain_messages()` with the combined index/search version:

```python
    def drain_messages(self):
        processed = False
        while True:
            try:
                message = self.message_queue.get_nowait()
            except queue.Empty:
                break
            processed = True
            if message["kind"] == "index":
                if message["event"] == "progress" and hasattr(self, "loading_view"):
                    self.loading_view.update_progress(message["payload"])
                elif message["event"] == "result":
                    if hasattr(self, "loading_view"):
                        self.loading_view.destroy()
                    self.build_main_ui()
                elif message["event"] == "error" and hasattr(self, "loading_view"):
                    self.loading_view.show_error()
                    self.root.after(1500, self.build_main_ui)
            elif message["kind"] == "search" and message["token"] == self.active_search_token:
                if message["event"] == "result":
                    self.finish_search(message["payload"], origin=self._pending_origin, load_all=self._pending_load_all)
                elif message["event"] == "error":
                    self.status_var.set("Search failed.")
        if not processed:
            self.root.after(10, self.drain_messages)
```

Add or replace the window-behavior methods with:

```python
    def apply_window_settings(self):
        width, height = parse_window_size(self.gui_config.get("window_size", "900x700"))
        x, y = parse_window_position(self.gui_config.get("window_position", "+100+100"))
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.set_always_on_top(self.always_on_top_var.get())

    def set_always_on_top(self, enabled):
        self.root.wm_attributes("-topmost", bool(enabled))

    def on_resize(self, event):
        width = event.width if hasattr(event, "width") else self.root.winfo_width()
        self.narrow_layout = should_use_narrow_layout(width)
        if self.tools_visible:
            self.tools_panel.pack_forget()
            if self.narrow_layout:
                self.tools_panel.pack(in_=self.container, fill="x", pady=(8, 0))
            else:
                self.tools_panel.pack(in_=self.body, side="right", fill="y", padx=(12, 0))

    def write_window_config(self):
        next_config = build_gui_config_update(
            self.config,
            always_on_top=self.always_on_top_var.get(),
            compact_mode=self.compact_mode_var.get(),
            window_size=f"{self.root.winfo_width()}x{self.root.winfo_height()}",
            window_position=f"+{self.root.winfo_x()}+{self.root.winfo_y()}",
        )
        write_config("config.json", next_config)

    def on_close(self):
        self.runner.cancel_all()
        self.runner.join_all(timeout=2)
        self.write_window_config()
        self.root.destroy()
```

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_tk.py
```

Expected: all Tk tests pass.

- [ ] **Step 5: Commit the startup and shutdown behavior**

Run:

```bash
git add gui_app/tk/main_window.py tests/test_gui_tk.py
git commit -m "feat: add Tk indexing and shutdown handling"
```

Expected: commit contains only startup/shutdown behavior work.

---

### Task 8: Replace The PySide6 Entry Point And Dependency Story

**Files:**
- Modify: `gui_app/app.py`
- Modify: `gui_app/preflight.py`
- Modify: `requirements.txt`
- Modify: `README.md`
- Modify: `tests/test_gui_preflight.py`
- Modify: `tests/test_gui_app.py`

- [ ] **Step 1: Add failing tests for the Tk entry point and preflight dependency list**

Update `tests/test_gui_app.py` to assert the new dependency guard:

```python
import builtins
from unittest import mock


class GuiEntryPointImportTests(unittest.TestCase):
    def test_require_tk_error_is_clear_when_tkinter_is_missing(self):
        with mock.patch.object(gui_app, "TK_AVAILABLE", False):
            with self.assertRaisesRegex(RuntimeError, "tkinter is required"):
                gui_app.require_tk()
```

Update `tests/test_gui_preflight.py` requirement expectations from `PySide6` to the remaining GUI-launch dependencies:

```python
        self.assertEqual(
            ["keyboard", "pypdf", "pyperclip"],
            preflight.read_requirements(requirements_path),
        )
```

Change the dependency-import test to use `pyperclip` instead of `PySide6` by replacing the affected test body with:

```python
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
```

- [ ] **Step 2: Run tests and verify they fail**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_app.py
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: failures because `gui_app.app` still exposes the PySide6 path and `requirements.txt` / `preflight.py` still mention `PySide6`.

- [ ] **Step 3: Replace the entry point and dependency docs**

Replace `gui_app/app.py` with a thin Tk launcher:

```python
try:
    import tkinter as tk
    TK_AVAILABLE = True
except ImportError:  # pragma: no cover
    TK_AVAILABLE = False


def require_tk():
    if not TK_AVAILABLE:
        raise RuntimeError(
            "tkinter is required for the myKamus GUI. Install a Python build that includes tkinter."
        )


def main():
    require_tk()
    from gui_app.core.backend import GuiBackend
    from gui_app.tk.main_window import MyKamusTkWindow

    root = tk.Tk()
    MyKamusTkWindow(root, backend=GuiBackend())
    root.mainloop()


if __name__ == "__main__":
    main()
```

Update `gui_app/preflight.py`:

```python
REQUIREMENT_IMPORTS = {
    "keyboard": "keyboard",
    "pypdf": "pypdf",
    "pyperclip": "pyperclip",
}
```

Update `requirements.txt`:

```text
keyboard
pypdf
pyperclip
```

Update `README.md` to replace these exact lines:

- `- Modern PySide6 desktop GUI with manual search, clipboard monitoring, compact mode, recent searches, and always-on-top support.`
  with
  `- Tkinter desktop GUI with manual search, clipboard monitoring, compact mode, recent searches, and always-on-top support.`
- `The main app is the PySide6 GUI:`
  with
  `The main app is the Tkinter GUI:`
- `- A PySide6 GUI redesign with responsive layout, clear colors, search history, and background worker threads.`
  with
  `- A Tkinter GUI redesign with responsive layout, clear colors, search history, and background worker threads.`

- [ ] **Step 4: Run tests and verify they pass**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_app.py
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: both test files pass.

- [ ] **Step 5: Commit the Tk migration boundary**

Run:

```bash
git add gui_app/app.py gui_app/preflight.py requirements.txt README.md tests/test_gui_app.py tests/test_gui_preflight.py
git commit -m "chore: remove PySide6 GUI dependency"
```

Expected: commit contains the entry-point switch, dependency update, and docs/test updates.

---

### Task 9: Full Verification And Review

**Files:**
- Modify as needed: all changed files above

- [ ] **Step 1: Run focused GUI tests**

Run:

```bash
python -B -m unittest discover -s tests -p test_gui_core.py
python -B -m unittest discover -s tests -p test_gui_runtime.py
python -B -m unittest discover -s tests -p test_gui_tk.py
python -B -m unittest discover -s tests -p test_gui_app.py
python -B -m unittest discover -s tests -p test_gui_preflight.py
```

Expected: all focused GUI tests pass or skip cleanly where display-dependent.

- [ ] **Step 2: Run the full test suite**

Run:

```bash
python -B -m unittest discover -s tests
```

Expected: full suite passes.

- [ ] **Step 3: Compile changed Python modules**

Run:

```bash
python -m py_compile gui_app\app.py gui_app\core\view_model.py gui_app\core\config_store.py gui_app\core\backend.py gui_app\runtime\tasks.py gui_app\tk\theme.py gui_app\tk\widgets.py gui_app\tk\loading_view.py gui_app\tk\main_window.py gui_app\preflight.py
```

Expected: command exits `0`.

- [ ] **Step 4: Check git diff and runtime cleanliness**

Run:

```bash
git diff --check
git status --short --branch
```

Expected: no whitespace errors and a clean implementation branch aside from intentional runtime-local files ignored by Git.

- [ ] **Step 5: Request code review**

Use `superpowers:requesting-code-review` over the implementation range. Review should verify:

- Tkinter fully replaced PySide6 as the GUI toolkit.
- The calmer search-first layout is present.
- Search, indexing, clipboard monitoring, history, compact mode, and always-on-top still work.
- Background threads do not update Tk widgets directly from worker threads.
- Window close cancels background work and persists config cleanly.
- `Start myKamus.bat` and `python -m gui_app.app` still work.
- `requirements.txt`, `README.md`, and preflight text no longer require `PySide6`.

---

## Self-Review

Spec coverage:

- Toolkit-neutral architecture split: Tasks 1 through 5.
- Calmer Tkinter layout: Tasks 4 through 7.
- Full feature parity target: Tasks 6 through 8.
- Background threading, queue handoff, and shutdown behavior: Tasks 3 and 7.
- Cross-platform Tkinter and dependency boundary: Tasks 4, 7, and 8.
- Stable entry points, updated dependency story, and docs: Task 8.
- Testing and verification: Task 9.

Scope control:

- No search/index algorithm rewrite.
- No installer or packaging work.
- No launch-command changes.
- No CLI rewrite.

Placeholder scan:

- No `TODO`, `TBD`, or deferred implementation markers remain.

Type and name consistency:

- `MyKamusTkWindow`, `GuiBackend`, `BackgroundTaskRunner`, `build_result_view_model`, `build_gui_config_update`, `write_config`, `require_tk`, and the Tk widget names are introduced before later tasks depend on them.
