import json
import sys
from pathlib import Path

import pyperclip

from search_functions import (
    ensure_red_book_index,
    ensure_sentence_index,
    is_red_book_index_valid,
    is_sentence_index_valid,
    load_config,
    normalize_query,
    search_for_word_data,
)


try:
    from PySide6.QtCore import QTimer, QThread, Qt, Signal
    from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QPalette, QShortcut
    from PySide6.QtWidgets import (
        QApplication,
        QCheckBox,
        QFrame,
        QGridLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QPushButton,
        QProgressBar,
        QScrollArea,
        QSizePolicy,
        QSplitter,
        QStatusBar,
        QVBoxLayout,
        QWidget,
    )
    QT_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by dependency-free imports
    QT_AVAILABLE = False


BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = BASE_DIR / "config.json"
HISTORY_LIMIT = 12
NARROW_LAYOUT_WIDTH = 760
QT_MAX_SIZE = 16777215


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
    return str(byte_count) + " bytes"


def indexes_are_ready():
    return is_sentence_index_valid() and is_red_book_index_valid()


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
            "counts": {
                "definitions": 0,
                "red_book": 0,
                "sentences": 0,
            },
            "sentences_truncated": False,
            "sentence_limit": result.get("sentence_limit"),
        }

    red_book_items = []
    for item in result.get("red_book_definitions", []):
        red_book_items.append(
            {
                "kind": "red_book_definition",
                "headword": item.get("headword", ""),
                "definition": item.get("definition", ""),
                "page": item.get("page"),
                "copy_text": (
                    item.get("headword", "")
                    + "\n"
                    + item.get("definition", "")
                ).strip(),
            }
        )
    sections = []
    if red_book_items:
        sections.append(
            {
                "kind": "red_book",
                "title": "Red Book Results",
                "items": red_book_items,
            }
        )

    sections.append(
        {
            "kind": "definitions",
            "title": "Word Translations",
            "items": [
                {
                    "kind": "translation",
                    "index": index,
                    "text": definition,
                    "copy_text": definition,
                }
                for index, definition in enumerate(result["definitions"], start=1)
            ],
            "empty_text": "No dictionary entries found.",
        }
    )

    sentence_title = "All Example Sentences" if load_all else "Example Sentences"
    sections.append(
        {
            "kind": "sentences",
            "title": sentence_title,
            "items": [
                {
                    "kind": "sentence",
                    "index": item["index"],
                    "match": item.get("match", ""),
                    "translation": item.get("translation", ""),
                    "matched_language": item.get("matched_language"),
                    "copy_text": (
                        item.get("match", "")
                        + "\n"
                        + item.get("translation", "")
                    ).strip(),
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


def require_qt():
    if not QT_AVAILABLE:
        raise RuntimeError(
            "PySide6 is required for the modern GUI. Install dependencies with: "
            "pip install -r requirements.txt"
        )


if QT_AVAILABLE:
    def connect_signal(signal, callback):
        signal.connect(lambda *args: callback(*args))


    class IndexWorker(QThread):
        progress_changed = Signal(dict)
        completed = Signal(object, object)

        def run(self):
            def emit_progress(progress):
                self.progress_changed.emit(progress)

            try:
                ensure_sentence_index(
                    progress_callback=lambda progress: emit_progress(
                        {
                            **progress,
                            "title": "Building sentence search index...",
                        }
                    )
                )
                ensure_red_book_index(
                    progress_callback=lambda progress: emit_progress(
                        {
                            **progress,
                            "title": "Building Red Book index...",
                        }
                    )
                )
                self.completed.emit(None, None)
            except Exception as exc:  # pragma: no cover - defensive UI boundary
                self.completed.emit(None, exc)


    class SearchWorker(QThread):
        completed = Signal(int, object, object, bool, str)

        def __init__(self, generation, query, sentence_limit, load_all, origin, parent=None):
            super().__init__(parent)
            self.generation = generation
            self.query = query
            self.sentence_limit = sentence_limit
            self.load_all = load_all
            self.origin = origin

        def run(self):
            try:
                result = search_for_word_data(
                    self.query,
                    sentence_limit=self.sentence_limit,
                )
                self.completed.emit(
                    self.generation,
                    result,
                    None,
                    self.load_all,
                    self.origin,
                )
            except Exception as exc:  # pragma: no cover - defensive UI boundary
                self.completed.emit(
                    self.generation,
                    None,
                    exc,
                    self.load_all,
                    self.origin,
                )


    class LoadingView(QWidget):
        def __init__(self, parent=None):
            super().__init__(parent)
            layout = QVBoxLayout(self)
            layout.setContentsMargins(48, 48, 48, 48)
            layout.setSpacing(16)
            layout.addStretch(1)

            self.title_label = QLabel("Building search index...")
            self.title_label.setObjectName("loadingTitle")
            self.percent_label = QLabel("0%")
            self.percent_label.setObjectName("loadingPercent")
            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)
            self.detail_label = QLabel("Preparing corpus...")
            self.detail_label.setObjectName("mutedLabel")
            self.status_label = QLabel("This only happens when the data changes.")
            self.status_label.setObjectName("mutedLabel")

            layout.addWidget(self.title_label)
            layout.addWidget(self.percent_label)
            layout.addWidget(self.progress_bar)
            layout.addWidget(self.detail_label)
            layout.addWidget(self.status_label)
            layout.addStretch(2)

        def update_progress(self, progress):
            percent = float(progress.get("percent", 0.0))
            self.title_label.setText(progress.get("title", "Building search index..."))
            self.percent_label.setText(f"{percent:.0f}%")
            self.progress_bar.setValue(int(round(percent)))
            processed_pages = progress.get("processed_pages")
            total_pages = progress.get("total_pages")
            if processed_pages is not None and total_pages is not None:
                self.detail_label.setText(
                    "Processed page "
                    + str(processed_pages)
                    + " of "
                    + str(total_pages)
                )
            else:
                self.detail_label.setText(
                    "Processed "
                    + format_bytes(int(progress.get("processed_bytes", 0)))
                    + " of "
                    + format_bytes(int(progress.get("total_bytes", 0)))
                )

        def show_error(self):
            self.status_label.setText("Index build failed. Searches will use fallback mode.")

        def show_ready(self):
            self.percent_label.setText("100%")
            self.progress_bar.setValue(100)
            self.status_label.setText("Search index ready.")


    class MyKamusGUI(QMainWindow):
        def __init__(self):
            super().__init__()
            self.config = load_config()
            self.gui_config = self.config.get("gui", {})
            self.clipboard_value = self._safe_clipboard_text()
            self.paused = False
            self.main_ui_ready = False
            self.search_generation = 0
            self.search_workers = {}
            self.search_history = []
            self.index_worker = None
            self.poll_interval_ms = int(float(self.config.get("poll_interval", 0.1)) * 1000)
            self.narrow_layout = None

            self.setWindowTitle("myKamus")
            self.setMinimumSize(520, 420)
            self.search_status_timer = QTimer(self)
            self.search_status_timer.setSingleShot(True)
            connect_signal(self.search_status_timer.timeout, self._show_searching_status)
            self.pending_status_generation = None

            if indexes_are_ready():
                self._show_main_ui()
            else:
                self.loading_view = LoadingView(self)
                self.setCentralWidget(self.loading_view)
                self._start_index_build()

        def _show_main_ui(self):
            if self.main_ui_ready:
                return
            self._build_ui()
            self._apply_window_settings()
            self.main_ui_ready = True
            self._set_responsive_layout(should_use_narrow_layout(self.width()))
            self._update_clipboard_label(self.clipboard_value)
            self._run_search(self.clipboard_value, origin="startup")
            self._focus_search_entry(select_text=True)
            self.clipboard_timer = QTimer(self)
            connect_signal(self.clipboard_timer.timeout, self._poll_clipboard)
            self.clipboard_timer.start(max(100, self.poll_interval_ms))

        def _build_ui(self):
            root = QWidget(self)
            root.setObjectName("appRoot")
            root_layout = QVBoxLayout(root)
            root_layout.setContentsMargins(18, 18, 18, 12)
            root_layout.setSpacing(12)

            self._build_command_bar(root_layout)
            self._build_main_area(root_layout)

            status_bar = QStatusBar(self)
            status_bar.setSizeGripEnabled(False)
            self.status_label = QLabel("")
            self.status_label.setObjectName("statusLabel")
            status_bar.addWidget(self.status_label, 1)
            self.setStatusBar(status_bar)
            self.setCentralWidget(root)
            self._install_shortcuts()

        def _build_command_bar(self, root_layout):
            command_bar = QFrame()
            command_bar.setObjectName("commandBar")
            self.command_layout = QGridLayout(command_bar)
            self.command_layout.setContentsMargins(14, 12, 14, 12)
            self.command_layout.setHorizontalSpacing(10)
            self.command_layout.setVerticalSpacing(10)

            self.search_entry = QLineEdit()
            self.search_entry.setObjectName("searchEntry")
            self.search_entry.setPlaceholderText("Search Indonesian or English")
            connect_signal(self.search_entry.returnPressed, self._on_manual_search)

            self.search_button = QPushButton("Search")
            self.search_button.setObjectName("primaryButton")
            connect_signal(self.search_button.clicked, lambda _checked=False: self._on_manual_search())

            self.load_all_button = QPushButton("Load All")
            connect_signal(self.load_all_button.clicked, lambda _checked=False: self._on_load_all())

            self.clear_button = QPushButton("Clear")
            connect_signal(self.clear_button.clicked, lambda _checked=False: self._clear_search())

            root_layout.addWidget(command_bar)
            self._arrange_command_bar(False)

        def _arrange_command_bar(self, narrow):
            for widget in (
                self.search_entry,
                self.search_button,
                self.load_all_button,
                self.clear_button,
            ):
                self.command_layout.removeWidget(widget)
            if narrow:
                self.command_layout.addWidget(self.search_entry, 0, 0, 1, 3)
                self.command_layout.addWidget(self.search_button, 1, 0)
                self.command_layout.addWidget(self.load_all_button, 1, 1)
                self.command_layout.addWidget(self.clear_button, 1, 2)
                for button in (self.search_button, self.load_all_button, self.clear_button):
                    button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                self.command_layout.setColumnStretch(0, 1)
                self.command_layout.setColumnStretch(1, 1)
                self.command_layout.setColumnStretch(2, 1)
                self.command_layout.setColumnStretch(3, 0)
            else:
                self.command_layout.addWidget(self.search_entry, 0, 0)
                self.command_layout.addWidget(self.search_button, 0, 1)
                self.command_layout.addWidget(self.load_all_button, 0, 2)
                self.command_layout.addWidget(self.clear_button, 0, 3)
                for button in (self.search_button, self.load_all_button, self.clear_button):
                    button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
                self.command_layout.setColumnStretch(0, 1)
                self.command_layout.setColumnStretch(1, 0)
                self.command_layout.setColumnStretch(2, 0)
                self.command_layout.setColumnStretch(3, 0)

        def _build_main_area(self, root_layout):
            self.splitter = QSplitter(Qt.Horizontal)
            self.splitter.setChildrenCollapsible(False)

            self.sidebar = QFrame()
            self.sidebar.setObjectName("sidebar")
            self.sidebar.setMinimumWidth(230)
            self.sidebar.setMaximumWidth(300)
            sidebar_layout = QVBoxLayout(self.sidebar)
            sidebar_layout.setContentsMargins(14, 14, 14, 14)
            sidebar_layout.setSpacing(12)

            sidebar_layout.addWidget(self._section_label("Clipboard"))
            self.clipboard_label = QLabel("")
            self.clipboard_label.setObjectName("clipboardValue")
            self.clipboard_label.setWordWrap(True)
            sidebar_layout.addWidget(self.clipboard_label)

            self.pause_button = QPushButton("Pause Monitoring")
            self.pause_button.setMinimumHeight(36)
            connect_signal(self.pause_button.clicked, lambda _checked=False: self._toggle_pause())
            sidebar_layout.addWidget(self.pause_button)

            self.always_on_top_check = QCheckBox("Always on top")
            self.always_on_top_check.setChecked(self.gui_config.get("always_on_top", True))
            connect_signal(self.always_on_top_check.toggled, self._toggle_always_on_top)
            sidebar_layout.addWidget(self.always_on_top_check)

            self.compact_mode_check = QCheckBox("Compact mode")
            self.compact_mode_check.setChecked(self.gui_config.get("compact_mode", False))
            connect_signal(self.compact_mode_check.toggled, lambda _checked=False: self._on_compact_mode())
            sidebar_layout.addWidget(self.compact_mode_check)

            sidebar_layout.addSpacing(8)
            self.recent_label = self._section_label("Recent")
            sidebar_layout.addWidget(self.recent_label)
            self.history_list = QListWidget()
            self.history_list.setObjectName("historyList")
            connect_signal(self.history_list.itemActivated, self._on_history_item)
            connect_signal(self.history_list.itemClicked, self._on_history_item)
            sidebar_layout.addWidget(self.history_list, 1)

            self.splitter.addWidget(self.sidebar)

            self.results_scroll = QScrollArea()
            self.results_scroll.setObjectName("resultsScroll")
            self.results_scroll.setWidgetResizable(True)
            self.results_container = QWidget()
            self.results_container.setObjectName("resultsContainer")
            self.results_layout = QVBoxLayout(self.results_container)
            self.results_layout.setContentsMargins(4, 0, 4, 12)
            self.results_layout.setSpacing(12)
            self.results_scroll.setWidget(self.results_container)
            self.splitter.addWidget(self.results_scroll)
            self.splitter.setStretchFactor(0, 0)
            self.splitter.setStretchFactor(1, 1)

            root_layout.addWidget(self.splitter, 1)
            self._set_responsive_layout(should_use_narrow_layout(self.width()))

        def _set_responsive_layout(self, narrow):
            if self.narrow_layout == narrow:
                return
            self.narrow_layout = narrow
            self._arrange_command_bar(narrow)
            if narrow:
                self.splitter.setOrientation(Qt.Vertical)
                self.sidebar.setMinimumWidth(0)
                self.sidebar.setMaximumWidth(QT_MAX_SIZE)
                self.sidebar.setMaximumHeight(230)
                self.recent_label.setVisible(False)
                self.history_list.setVisible(False)
            else:
                self.splitter.setOrientation(Qt.Horizontal)
                self.sidebar.setMinimumWidth(230)
                self.sidebar.setMaximumWidth(300)
                self.sidebar.setMaximumHeight(QT_MAX_SIZE)
                self.recent_label.setVisible(True)
                self.history_list.setVisible(True)
                self.history_list.setMaximumHeight(QT_MAX_SIZE)

        def _install_shortcuts(self):
            escape_shortcut = QShortcut(QKeySequence("Escape"), self)
            connect_signal(escape_shortcut.activated, self._clear_search)
            ctrl_l_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
            connect_signal(ctrl_l_shortcut.activated, self._focus_and_select_search)
            meta_l_shortcut = QShortcut(QKeySequence("Meta+L"), self)
            connect_signal(meta_l_shortcut.activated, self._focus_and_select_search)
            self.shortcuts = [escape_shortcut, ctrl_l_shortcut, meta_l_shortcut]

            focus_action = QAction(self)
            focus_action.setShortcut(QKeySequence("Ctrl+F"))
            connect_signal(
                focus_action.triggered,
                lambda _checked=False: self._focus_and_select_search(),
            )
            self.addAction(focus_action)

        def _section_label(self, text):
            label = QLabel(text.upper())
            label.setObjectName("sectionKicker")
            return label

        def _start_index_build(self):
            self.index_worker = IndexWorker(self)
            connect_signal(self.index_worker.progress_changed, self._update_index_progress)
            connect_signal(self.index_worker.completed, self._finish_index_build)
            self.index_worker.start()

        def _update_index_progress(self, progress):
            if hasattr(self, "loading_view"):
                self.loading_view.update_progress(progress)

        def _finish_index_build(self, _result, error):
            if error is not None:
                self.loading_view.show_error()
                QTimer.singleShot(1500, self._show_main_ui)
                return
            self.loading_view.show_ready()
            QTimer.singleShot(250, self._show_main_ui)

        def _apply_window_settings(self):
            width, height = parse_window_size(self.gui_config.get("window_size", "900x700"))
            x, y = parse_window_position(self.gui_config.get("window_position", "+100+100"))
            self.resize(width, height)
            self.move(x, y)
            self._set_always_on_top(
                self.always_on_top_check.isChecked(),
                show=self.isVisible(),
            )

        def _toggle_always_on_top(self, checked):
            self._set_always_on_top(checked, show=True)
            self._set_status("Always on top: " + ("on" if checked else "off"))

        def _set_always_on_top(self, enabled, show=True):
            flags = self.windowFlags()
            if enabled:
                flags |= Qt.WindowStaysOnTopHint
            else:
                flags &= ~Qt.WindowStaysOnTopHint
            self.setWindowFlags(flags)
            if show:
                self.show()

        def _toggle_pause(self):
            self.paused = not self.paused
            self.pause_button.setText(
                "Resume Monitoring" if self.paused else "Pause Monitoring"
            )
            self._set_status("Monitoring paused." if self.paused else "Monitoring resumed.")

        def _on_compact_mode(self):
            self._set_status(
                "Compact mode: "
                + ("on" if self.compact_mode_check.isChecked() else "off")
            )
            self._run_search(self.clipboard_value, origin="control")

        def _on_manual_search(self):
            query = self.search_entry.text().strip()
            self._update_clipboard_label(query or self.clipboard_value)
            self._run_search(query, origin="manual")

        def _on_load_all(self):
            query = self.search_entry.text().strip() or self.clipboard_value
            self._update_clipboard_label(query)
            self._run_search(query, load_all=True, origin="load_all")

        def _on_history_item(self, item):
            query = item.text()
            self.search_entry.setText(query)
            self._run_search(query, origin="history")

        def _clear_search(self):
            self.search_entry.clear()
            self._focus_search_entry(select_text=False)

        def _focus_and_select_search(self):
            self._focus_search_entry(select_text=True)

        def _update_clipboard_label(self, text):
            display = text.strip() if text else "(empty)"
            self.clipboard_label.setText(display)

        def _safe_clipboard_text(self):
            try:
                return pyperclip.paste()
            except Exception:
                return ""

        def _poll_clipboard(self):
            if self.paused:
                return
            current = self._safe_clipboard_text()
            if current != self.clipboard_value:
                self.clipboard_value = current
                self._update_clipboard_label(current)
                self._run_search(current, origin="clipboard")

        def _run_search(self, query, load_all=False, origin="manual"):
            sentence_limit = resolve_sentence_limit(
                self.config,
                self.compact_mode_check.isChecked(),
                load_all,
            )
            self.search_generation += 1
            generation = self.search_generation
            self._schedule_searching_status(generation)
            worker = SearchWorker(
                generation,
                query,
                sentence_limit,
                load_all,
                origin,
                self,
            )
            connect_signal(worker.completed, self._finish_search)
            connect_signal(worker.finished, lambda gen=generation: self._cleanup_search_worker(gen))
            self.search_workers[generation] = worker
            worker.start()

        def _schedule_searching_status(self, generation):
            if self.search_status_timer.isActive():
                self.search_status_timer.stop()
            self.pending_status_generation = generation
            delay_ms = int(self.gui_config.get("search_status_delay_ms", 200))
            if delay_ms <= 0:
                self._show_searching_status()
            else:
                self.search_status_timer.start(delay_ms)

        def _show_searching_status(self):
            if self.pending_status_generation != self.search_generation:
                return
            self._set_status("Searching...")

        def _cancel_searching_status(self):
            if self.search_status_timer.isActive():
                self.search_status_timer.stop()
            self.pending_status_generation = None

        def _cleanup_search_worker(self, generation):
            worker = self.search_workers.pop(generation, None)
            if worker is not None:
                worker.deleteLater()

        def _finish_search(self, generation, result, error, load_all, origin):
            if generation != self.search_generation:
                return
            self._cancel_searching_status()
            if error is not None:
                self._render_error(error)
                self._restore_search_entry_focus(origin)
                return

            if origin in {"manual", "button", "load_all", "history"}:
                self.search_history = add_search_history(self.search_history, result["query"])
                self._render_history()
            self._render_results(result, load_all=load_all)
            self._restore_search_entry_focus(origin)

        def _render_error(self, error):
            self._clear_results()
            self.results_layout.addWidget(self._message_card("Search failed: " + str(error)))
            self.results_layout.addStretch(1)
            self._set_status("Search failed.")

        def _render_results(self, result, load_all=False):
            self._clear_results()
            view_model = build_result_view_model(result, load_all=load_all)
            if view_model["message"]:
                self.results_layout.addWidget(self._message_card(view_model["message"]))
                self.results_layout.addStretch(1)
                self._set_status(status_text_for_result(view_model, load_all=load_all))
                return

            for section in view_model["sections"]:
                self._add_section(section)
            self.results_layout.addStretch(1)
            self._set_status(status_text_for_result(view_model, load_all=load_all))

        def _clear_results(self):
            while self.results_layout.count():
                item = self.results_layout.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.deleteLater()

        def _add_section(self, section):
            header = QFrame()
            header.setObjectName("sectionHeader")
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(0, 4, 0, 0)
            title = QLabel(section["title"])
            title.setObjectName("sectionTitle")
            count = QLabel(str(len(section["items"])))
            count.setObjectName("countBadge")
            header_layout.addWidget(title)
            header_layout.addWidget(count)
            header_layout.addStretch(1)
            self.results_layout.addWidget(header)

            if not section["items"]:
                self.results_layout.addWidget(self._message_card(section.get("empty_text", "")))
                return

            for item in section["items"]:
                if item["kind"] == "red_book_definition":
                    self.results_layout.addWidget(self._red_book_definition_card(item))
                elif item["kind"] == "translation":
                    self.results_layout.addWidget(self._translation_row(item))
                elif item["kind"] == "sentence":
                    self.results_layout.addWidget(self._sentence_card(item))

        def _card(self):
            frame = QFrame()
            frame.setObjectName("card")
            frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
            return frame

        def _message_card(self, text):
            card = self._card()
            layout = QVBoxLayout(card)
            layout.setContentsMargins(16, 14, 16, 14)
            label = QLabel(text)
            label.setObjectName("mutedLabel")
            label.setWordWrap(True)
            layout.addWidget(label)
            return card

        def _red_book_definition_card(self, item):
            card = self._card()
            layout = QVBoxLayout(card)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(8)
            layout.addLayout(self._card_header(item["headword"], item.get("page"), item["copy_text"]))
            definition = QLabel(item["definition"])
            definition.setWordWrap(True)
            definition.setTextInteractionFlags(Qt.TextSelectableByMouse)
            definition.setObjectName("definitionText")
            layout.addWidget(definition)
            return card

        def _translation_row(self, item):
            row = QFrame()
            row.setObjectName("translationRow")
            layout = QHBoxLayout(row)
            layout.setContentsMargins(14, 10, 14, 10)
            index = QLabel(str(item["index"]))
            index.setObjectName("rowIndex")
            text = QLabel(item["text"])
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            copy_button = self._copy_button(item["copy_text"])
            layout.addWidget(index)
            layout.addWidget(text, 1)
            layout.addWidget(copy_button)
            return row

        def _sentence_card(self, item):
            card = self._card()
            layout = QVBoxLayout(card)
            layout.setContentsMargins(16, 14, 16, 14)
            layout.setSpacing(8)
            layout.addLayout(self._card_header("Example " + str(item["index"]), None, item["copy_text"]))
            layout.addWidget(self._labeled_text("Match", item["match"]))
            layout.addWidget(self._labeled_text("Translation", item["translation"]))
            return card

        def _card_header(self, title_text, page, copy_text):
            layout = QHBoxLayout()
            layout.setContentsMargins(0, 0, 0, 0)
            title = QLabel(title_text or "Result")
            title.setObjectName("cardTitle")
            title.setWordWrap(True)
            layout.addWidget(title, 1)
            if page:
                page_label = QLabel("Page " + str(page))
                page_label.setObjectName("pageBadge")
                layout.addWidget(page_label)
            layout.addWidget(self._copy_button(copy_text))
            return layout

        def _labeled_text(self, label, value):
            frame = QFrame()
            layout = QGridLayout(frame)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setHorizontalSpacing(12)
            name = QLabel(label)
            name.setObjectName("fieldLabel")
            text = QLabel(value)
            text.setWordWrap(True)
            text.setTextInteractionFlags(Qt.TextSelectableByMouse)
            layout.addWidget(name, 0, 0, Qt.AlignTop)
            layout.addWidget(text, 0, 1)
            layout.setColumnStretch(1, 1)
            return frame

        def _copy_button(self, text):
            button = QPushButton("Copy")
            button.setObjectName("smallButton")
            button.clicked.connect(lambda: self._copy_text(text))
            return button

        def _copy_text(self, text):
            QApplication.clipboard().setText(text)
            self._set_status("Copied result.")

        def _render_history(self):
            self.history_list.clear()
            for query in self.search_history:
                self.history_list.addItem(QListWidgetItem(query))

        def _set_status(self, message):
            self.status_label.setText(message)

        def _focus_search_entry(self, select_text=False):
            if not self.main_ui_ready:
                return
            self.search_entry.setFocus(Qt.ShortcutFocusReason)
            if select_text:
                self.search_entry.selectAll()

        def _restore_search_entry_focus(self, origin):
            if not should_refocus_search(origin):
                return
            QTimer.singleShot(0, lambda: self._focus_search_entry(select_text=True))

        def resizeEvent(self, event):
            super().resizeEvent(event)
            if self.main_ui_ready:
                self._set_responsive_layout(should_use_narrow_layout(event.size().width()))

        def closeEvent(self, event):
            self._cancel_searching_status()
            if hasattr(self, "clipboard_timer"):
                self.clipboard_timer.stop()
            self._write_window_config()
            super().closeEvent(event)

        def _write_window_config(self):
            if not self.main_ui_ready:
                return
            config = dict(self.config)
            gui_config = dict(config.get("gui", {}))
            gui_config.update(
                {
                    "always_on_top": self.always_on_top_check.isChecked(),
                    "compact_mode": self.compact_mode_check.isChecked(),
                    "window_size": f"{self.width()}x{self.height()}",
                    "window_position": f"+{self.x()}+{self.y()}",
                }
            )
            config["gui"] = gui_config
            with CONFIG_PATH.open("w", encoding="utf-8") as config_file:
                json.dump(config, config_file, indent=2)
                config_file.write("\n")


    def apply_theme(app):
        app.setFont(QFont("Arial", 10))
        palette = app.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#f6f7f4"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#17201b"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#eef2ee"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#17201b"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#17201b"))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#17201b"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#2f7a67"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
        app.setPalette(palette)
        app.setStyleSheet(
            """
            QWidget {
                background-color: #f6f7f4;
                color: #17201b;
                font-family: "Inter", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
                font-size: 14px;
            }
            QLabel {
                background: transparent;
                color: #17201b;
            }
            QPushButton, QCheckBox, QListWidget, QLineEdit, QStatusBar {
                color: #17201b;
            }
            QWidget#appRoot {
                background: #f6f7f4;
                color: #17201b;
            }
            QFrame#commandBar, QFrame#sidebar, QFrame#card {
                background: #ffffff;
                border: 1px solid #d8ded6;
                border-radius: 8px;
            }
            QFrame#commandBar {
                border-color: #cfd8d1;
            }
            QFrame#sidebar {
                background: #eef2ee;
            }
            QLineEdit#searchEntry {
                background: #ffffff;
                color: #17201b;
                placeholder-text-color: #68766d;
                border: 1px solid #b8c4bb;
                border-radius: 8px;
                padding: 10px 12px;
                font-size: 18px;
                selection-background-color: #2f7a67;
                selection-color: #ffffff;
            }
            QLineEdit#searchEntry:focus {
                border: 2px solid #2f7a67;
                padding: 9px 11px;
            }
            QPushButton {
                background: #ffffff;
                color: #17201b;
                border: 1px solid #b8c4bb;
                border-radius: 8px;
                padding: 9px 12px;
            }
            QPushButton:hover {
                background: #f1f5f2;
            }
            QPushButton#primaryButton {
                background: #2f7a67;
                border-color: #2f7a67;
                color: #ffffff;
                font-weight: 600;
            }
            QPushButton#primaryButton:hover {
                background: #286b5a;
            }
            QPushButton#smallButton {
                padding: 5px 9px;
                font-size: 12px;
            }
            QCheckBox {
                background: transparent;
                color: #17201b;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #8fa196;
                border-radius: 4px;
                background: #ffffff;
            }
            QCheckBox::indicator:checked {
                background: #2f7a67;
                border-color: #2f7a67;
            }
            QLabel#sectionKicker {
                color: #607166;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#clipboardValue {
                color: #17201b;
                font-size: 16px;
                font-weight: 600;
            }
            QLabel#sectionTitle {
                font-size: 18px;
                font-weight: 700;
            }
            QLabel#countBadge, QLabel#pageBadge {
                background: #e3ede8;
                color: #2b604f;
                border-radius: 8px;
                padding: 3px 8px;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#cardTitle {
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#definitionText {
                font-size: 16px;
                line-height: 130%;
            }
            QLabel#fieldLabel, QLabel#rowIndex {
                color: #607166;
                font-size: 12px;
                font-weight: 700;
            }
            QLabel#mutedLabel, QLabel#statusLabel {
                color: #607166;
            }
            QFrame#translationRow {
                background: #ffffff;
                border: 1px solid #d8ded6;
                border-radius: 8px;
            }
            QListWidget#historyList {
                background: #ffffff;
                color: #17201b;
                border: 1px solid #d8ded6;
                border-radius: 8px;
                padding: 4px;
            }
            QListWidget#historyList::item {
                border-radius: 6px;
                padding: 7px;
            }
            QListWidget#historyList::item:selected {
                background: #d7e7df;
                color: #17201b;
            }
            QScrollArea#resultsScroll {
                border: none;
                background: transparent;
            }
            QWidget#resultsContainer {
                background: transparent;
            }
            QScrollArea#resultsScroll > QWidget > QWidget {
                background: transparent;
            }
            QLabel#loadingTitle {
                font-size: 24px;
                font-weight: 700;
            }
            QLabel#loadingPercent {
                font-size: 34px;
                font-weight: 800;
                color: #2f7a67;
            }
            QProgressBar {
                border: 1px solid #b8c4bb;
                border-radius: 8px;
                height: 14px;
                background: #ffffff;
            }
            QProgressBar::chunk {
                border-radius: 7px;
                background: #2f7a67;
            }
            QStatusBar {
                background: #f6f7f4;
                color: #17201b;
                border-top: 1px solid #d8ded6;
            }
            QStatusBar QLabel {
                color: #607166;
            }
            """
        )

else:
    class MyKamusGUI:  # pragma: no cover - trivial dependency guard
        def __init__(self, *args, **kwargs):
            require_qt()


def main():
    require_qt()
    app = QApplication(sys.argv)
    apply_theme(app)
    window = MyKamusGUI()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
