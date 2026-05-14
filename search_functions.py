"""
Search helpers for myKamus.
"""

from collections import defaultdict
import copy
import json
import os
from pathlib import Path
import re
import textwrap

import red_book_index
import search_index


BASE_DIR = Path(__file__).resolve().parent
CONFIG_ENV_VAR = "MYKAMUS_CONFIG"
CONFIG_DEFAULTS = {
    "dictionary_path": "en-id_dict.txt",
    "sentences_path": "en-id_sentences.txt",
    "cache_path": ".mykamus_cache/search.sqlite",
    "red_book_pdf_path": "indonesiandictionary.pdf",
    "red_book_cache_path": ".mykamus_cache/red_book.sqlite",
    "red_book_results_limit": 3,
    "red_book_enabled": True,
    "sentence_limit": 4,
    "gui": {
        "always_on_top": True,
        "compact_mode": False,
        "window_size": "900x700",
        "window_position": "+100+100",
        "load_all_sentence_limit": 200,
        "search_status_delay_ms": 200,
    },
    "search": {
        "use_index": True,
    },
    "hotkeys": {
        "manual_search": "ctrl+s",
        "load_all_sentences": "l",
    },
    "poll_interval": 0.1,
}

_CONFIG = None
dictionary = None
dictionary_index = None
WRAP_WIDTH = 80

_DEFAULT_SENTENCE_LIMIT = object()


def _deep_update(base, overrides):
    merged = copy.deepcopy(base)
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_update(merged[key], value)
        else:
            merged[key] = value
    return merged


def _config_paths():
    env_path = os.environ.get(CONFIG_ENV_VAR)
    if env_path:
        return [Path(env_path)]
    return [BASE_DIR / "config.example.json", BASE_DIR / "config.json"]


def load_config():
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG

    config = copy.deepcopy(CONFIG_DEFAULTS)
    for config_path in _config_paths():
        if config_path.exists():
            with config_path.open(encoding="utf-8") as config_file:
                config = _deep_update(config, json.load(config_file))
    _CONFIG = config
    return config


def data_path(config_key):
    path = Path(load_config()[config_key])
    if path.is_absolute():
        return path
    return BASE_DIR / path


def sentences_path():
    return data_path("sentences_path")


def cache_path():
    return data_path("cache_path")


def red_book_pdf_path():
    return data_path("red_book_pdf_path")


def red_book_cache_path():
    return data_path("red_book_cache_path")


def red_book_enabled():
    return bool(load_config().get("red_book_enabled", True))


def should_index_red_book():
    return red_book_enabled() and red_book_pdf_path().exists()


def is_sentence_index_valid():
    return search_index.is_index_valid(sentences_path(), cache_path())


def is_red_book_index_valid():
    if not should_index_red_book():
        return True
    return red_book_index.is_red_book_index_valid(
        red_book_pdf_path(),
        red_book_cache_path(),
    )


def ensure_sentence_index(progress_callback=None):
    return search_index.ensure_sentence_index(
        sentences_path(),
        cache_path(),
        progress_callback=progress_callback,
    )


def ensure_red_book_index(progress_callback=None):
    if not should_index_red_book():
        return {
            "cache_path": str(red_book_cache_path()),
            "rebuilt": False,
            "skipped": True,
        }
    return red_book_index.ensure_red_book_index(
        red_book_pdf_path(),
        red_book_cache_path(),
        progress_callback=progress_callback,
    )


def build_index(lines):
    index = defaultdict(list)
    for i, line in enumerate(lines):
        tokens = set(re.findall(r"\b\w+\b", line.casefold()))
        for token in tokens:
            index[token].append(i)
    return index


def load_dictionary():
    global dictionary
    global dictionary_index

    if dictionary is None:
        with data_path("dictionary_path").open(encoding="utf-8") as dic:
            dictionary = dic.readlines()
        dictionary_index = build_index(dictionary)
    return dictionary


def load_data():
    """
    Backward-compatible loader.

    The dictionary is small enough to keep indexed in memory. The sentence
    corpus is deliberately streamed per search so app startup does not load the
    full 711 MB file.
    """
    return load_dictionary(), None


def normalize_query(string):
    return " ".join(str(string or "").strip().split())


def build_phrase_pattern(query):
    return re.compile(rf"(?<!\w){re.escape(query)}(?!\w)", re.IGNORECASE)


def build_query_matcher(query):
    pattern = build_phrase_pattern(query)

    def matches(text):
        return bool(pattern.search(text))

    return matches


def format_dictionary_line(line):
    tokens = line.strip().split()
    if not tokens:
        return ""
    tokens = ["·" if token == "." else token for token in tokens]
    return " ".join(tokens)


def format_labeled_line(label, text):
    cleaned = " ".join(text.strip().split())
    indent = " " * (len(label) + 1)
    return textwrap.fill(
        cleaned,
        width=WRAP_WIDTH,
        initial_indent=f"{label} ",
        subsequent_indent=indent,
    )


def format_sentence_block(index, match_line, translation_line):
    lines = [f"{index}:"]
    if match_line:
        lines.append(format_labeled_line("Match:", match_line))
    if translation_line:
        lines.append(format_labeled_line("Translation:", translation_line))
    return "\n".join(lines)


def format_red_book_definition_block(index, result):
    lines = [f"{index}:"]
    if result.get("headword"):
        lines.append(format_labeled_line("Headword:", result["headword"]))
    lines.append(format_labeled_line("Definition:", result["definition"]))
    if result.get("page"):
        lines.append(format_labeled_line("Page:", str(result["page"])))
    return "\n".join(lines)


def _iter_non_empty_sentence_lines():
    with data_path("sentences_path").open(encoding="utf-8", errors="replace") as sentences_file:
        for line in sentences_file:
            cleaned = " ".join(line.strip().split())
            if cleaned:
                yield cleaned


def iter_sentence_pairs():
    pending_english = None
    for line in _iter_non_empty_sentence_lines():
        if pending_english is None:
            pending_english = line
        else:
            yield {
                "english": pending_english,
                "indonesian": line,
            }
            pending_english = None


def iter_matching_sentence_pairs(query):
    matcher = build_query_matcher(query)
    for pair in iter_sentence_pairs():
        english = pair["english"]
        indonesian = pair["indonesian"]
        english_matches = matcher(english)
        indonesian_matches = matcher(indonesian)
        if not english_matches and not indonesian_matches:
            continue

        if indonesian_matches:
            yield {
                "match": indonesian,
                "translation": english,
                "matched_language": "indonesian",
                "english": english,
                "indonesian": indonesian,
            }
        else:
            yield {
                "match": english,
                "translation": indonesian,
                "matched_language": "english",
                "english": english,
                "indonesian": indonesian,
            }


def iter_matching_indexed_sentence_pairs(query, limit):
    yield from search_index.search_sentence_index(
        query,
        limit,
        sentences_path(),
        cache_path(),
    )


def search_matching_red_book_definitions(query, limit):
    if not should_index_red_book():
        return []
    if not red_book_index.is_red_book_index_valid(red_book_pdf_path(), red_book_cache_path()):
        return []
    return red_book_index.search_red_book_definitions(
        query,
        limit,
        red_book_pdf_path(),
        red_book_cache_path(),
    )


def iter_matching_dictionary_lines(query):
    load_dictionary()
    if " " in query:
        pattern = build_phrase_pattern(query)
        for line in dictionary:
            if pattern.search(line):
                yield line
    else:
        for i in dictionary_index.get(query.casefold(), []):
            yield dictionary[i]


def _coerce_sentence_limit(value):
    if value is None:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return CONFIG_DEFAULTS["sentence_limit"]


def search_for_word_data(query, sentence_limit=_DEFAULT_SENTENCE_LIMIT):
    cleaned_query = normalize_query(query)
    result = {
        "query": cleaned_query,
        "definitions": [],
        "red_book_definitions": [],
        "red_book_results": [],
        "sentences": [],
        "message": None,
        "sentence_limit": None,
        "sentences_truncated": False,
    }
    if not cleaned_query:
        result["message"] = "No word provided. Please enter a word or phrase."
        return result

    config = load_config()
    if sentence_limit is _DEFAULT_SENTENCE_LIMIT:
        sentence_limit = config["sentence_limit"]
    sentence_limit = _coerce_sentence_limit(sentence_limit)
    result["sentence_limit"] = sentence_limit

    for line in iter_matching_dictionary_lines(cleaned_query):
        formatted_line = format_dictionary_line(line)
        if formatted_line:
            result["definitions"].append(formatted_line)

    if red_book_enabled():
        red_book_limit = _coerce_sentence_limit(config.get("red_book_results_limit", 3))
        try:
            result["red_book_definitions"] = search_matching_red_book_definitions(
                cleaned_query,
                red_book_limit,
            )
        except red_book_index.RedBookUnavailableError:
            result["red_book_definitions"] = []
        except Exception:
            result["red_book_definitions"] = []

    sentence_index = 1
    search_limit = None if sentence_limit is None else sentence_limit + 1
    sentence_iter = iter_matching_sentence_pairs(cleaned_query)
    if config.get("search", {}).get("use_index", True):
        try:
            if is_sentence_index_valid():
                sentence_iter = iter_matching_indexed_sentence_pairs(cleaned_query, search_limit)
        except search_index.IndexUnavailableError:
            sentence_iter = iter_matching_sentence_pairs(cleaned_query)
        except Exception:
            sentence_iter = iter_matching_sentence_pairs(cleaned_query)

    emitted = set()
    for sentence in sentence_iter:
        pair_key = (sentence["english"], sentence["indonesian"])
        if pair_key in emitted:
            continue
        if sentence_limit is not None and len(result["sentences"]) >= sentence_limit:
            result["sentences_truncated"] = True
            break

        result["sentences"].append(
            {
                "index": sentence_index,
                "match": sentence["match"],
                "translation": sentence["translation"],
                "matched_language": sentence["matched_language"],
            }
        )
        emitted.add(pair_key)
        sentence_index += 1
    return result


def render_search_result(result):
    if result["message"]:
        return result["message"] + "\n"

    lines = [
        "Your input: " + result["query"].casefold(),
        "Word translations for " + result["query"].casefold() + " below:",
    ]
    if result["definitions"]:
        for index, line in enumerate(result["definitions"], start=1):
            lines.append(textwrap.fill(f"{index}: {line}", width=WRAP_WIDTH))
    else:
        lines.append("No dictionary entries found.")

    if result.get("red_book_definitions"):
        lines.append("")
        lines.append("Red Book Results:")
        for index, red_book_definition in enumerate(
            result.get("red_book_definitions", []),
            start=1,
        ):
            lines.append(format_red_book_definition_block(index, red_book_definition))
            lines.append("")

    lines.append("Example sentences for " + result["query"].casefold() + " below:")
    if result["sentences"]:
        for sentence in result["sentences"]:
            lines.append(
                format_sentence_block(
                    sentence["index"],
                    sentence["match"],
                    sentence["translation"],
                )
            )
            lines.append("")
    else:
        lines.append("No example sentences found.")

    if result["sentences_truncated"]:
        lines.append(
            "Showing the first "
            + str(result["sentence_limit"])
            + " matching sentence pairs. Narrow the query for fewer results."
        )
    return "\n".join(lines)


def search_for_word():
    """
    Interactive search helper kept for compatibility.
    """
    print("We are ready to take your word, please type it below:")
    search_for_word_clip(input())


def search_for_word_clip(string):
    print(render_search_result(search_for_word_data(string)))


def load_all_sentences(string, sentence_limit=None):
    """
    Print matching sentence pairs for a query.
    """
    query = normalize_query(string)
    if not query:
        print("No word provided. Please enter a word or phrase.")
        return

    emitted = set()
    found_any = False
    limit = _coerce_sentence_limit(sentence_limit)
    index = 1
    for sentence in iter_matching_sentence_pairs(query):
        pair_key = (sentence["english"], sentence["indonesian"])
        if pair_key in emitted:
            continue
        if limit is not None and len(emitted) >= limit:
            print(
                "Showing the first "
                + str(limit)
                + " matching sentence pairs. Narrow the query for fewer results."
            )
            break
        print(format_sentence_block(index, sentence["match"], sentence["translation"]))
        print()
        emitted.add(pair_key)
        found_any = True
        index += 1

    if found_any and (limit is None or len(emitted) < limit):
        print("All example sentences for the word " + query + " have been loaded.")
    elif not found_any:
        print("No example sentences found for the word " + query + ".")
