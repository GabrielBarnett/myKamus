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
    return str(byte_count) + " bytes"


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
