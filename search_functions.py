"""
Module contains the functions necessary to search through the databases provided by the user.
"""

from collections import defaultdict
import json
from pathlib import Path
import re
import textwrap

print("myKamus is loading...\n")

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DEFAULTS = {
    "dictionary_path": "en-id_dict.txt",
    "sentences_path": "en-id_sentences.txt",
    "sentence_limit": 4,
    "hotkeys": {
        "manual_search": "ctrl+s",
        "load_all_sentences": "l",
    },
    "poll_interval": 0.1,
}

_CONFIG = None
dictionary = None
sentences = None
dictionary_index = None
sentences_index = None
WRAP_WIDTH = 80


def load_config():
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG
    config_path = BASE_DIR / "config.json"
    config = dict(CONFIG_DEFAULTS)
    if config_path.exists():
        with config_path.open(encoding="utf-8") as config_file:
            loaded = json.load(config_file)
        config.update(loaded)
        config["hotkeys"] = {**CONFIG_DEFAULTS["hotkeys"], **loaded.get("hotkeys", {})}
    _CONFIG = config
    return config


def build_index(lines):
    index = defaultdict(list)
    for i, line in enumerate(lines):
        tokens = set(re.findall(r"\b\w+\b", line.casefold()))
        for token in tokens:
            index[token].append(i)
    return index


def load_data():
    global dictionary
    global sentences
    global dictionary_index
    global sentences_index
    config = load_config()
    if dictionary is None:
        dictionary_path = BASE_DIR / config["dictionary_path"]
        with dictionary_path.open(encoding="utf-8") as dic:
            dictionary = dic.readlines()
        dictionary_index = build_index(dictionary)
    if sentences is None:
        sentences_path = BASE_DIR / config["sentences_path"]
        with sentences_path.open(encoding="utf-8") as sentences_file:
            sentences = sentences_file.readlines()
        sentences_index = build_index(sentences)
    return dictionary, sentences


def normalize_query(string):
    return string.strip()


def build_phrase_pattern(query):
    return re.compile(rf"\b{re.escape(query)}\b", re.IGNORECASE)


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


def iter_matching_sentence_indices(query):
    if " " in query:
        pattern = build_phrase_pattern(query)
        for i, line in enumerate(sentences):
            if pattern.search(line):
                yield i
    else:
        for i in sentences_index.get(query.casefold(), []):
            yield i


def iter_matching_dictionary_lines(query):
    if " " in query:
        pattern = build_phrase_pattern(query)
        for line in dictionary:
            if pattern.search(line):
                yield line
    else:
        for i in dictionary_index.get(query.casefold(), []):
            yield dictionary[i]


def search_for_word():
    """
    Not currently in use, defined for testing purposes and the
    :return: string(s)
    """
    load_data()
    # declaring the prev_line variable so that we do not run into issues
    prev_line = ""
    print("We are ready to take your word, please type it below:")
    user_input = input()
    query = normalize_query(user_input)
    if not query:
        print("No word provided. Please enter a word or phrase.")
        return
    print("Word translations below:")
    config = load_config()
    sentence_count = config["sentence_limit"]
    sentence_index = 1
    def_index = 1
    for line in iter_matching_dictionary_lines(query):
        print(str(def_index) + ": " + line)
        def_index += 1
    print("Example sentences below:")
    emitted = set()
    for i in iter_matching_sentence_indices(query):
        if sentence_count <= 0:
            break
        line = sentences[i]
        prev_line = sentences[i - 1] if i > 0 else ""
        if line not in emitted:
            print(str(sentence_index) + ": " + line)
            emitted.add(line)
        if prev_line and prev_line not in emitted:
            print(str(sentence_index) + ": " + prev_line)
            emitted.add(prev_line)
        sentence_index += 1
        sentence_count -= 1


def search_for_word_clip(string):
    load_data()
    query = normalize_query(string)
    if not query:
        print("No word provided. Please enter a word or phrase.")
        return
    config = load_config()
    sentence_count = config["sentence_limit"]
    sentence_index = 1
    def_index = 1
    print("Your input: " + query.casefold())
    print("Word translations for " + query.casefold() + " below:")
    for line in iter_matching_dictionary_lines(query):
        formatted_line = format_dictionary_line(line)
        if not formatted_line:
            continue
        print(textwrap.fill(f"{def_index}: {formatted_line}", width=WRAP_WIDTH))
        def_index += 1
    print("Example sentences for " + query.casefold() + " below:")
    emitted = set()
    for i in iter_matching_sentence_indices(query):
        if sentence_count <= 0:
            break
        line = sentences[i].strip()
        prev_line = sentences[i - 1].strip() if i > 0 else ""
        pair_key = (line, prev_line)
        if pair_key in emitted:
            continue
        print(format_sentence_block(sentence_index, line, prev_line))
        print()
        emitted.add(pair_key)
        sentence_index += 1
        sentence_count -= 1


def load_all_sentences(string):
    """
    :param string: word that is to be searched
    :return: returns all of the sentences that are in the sentence file for the string
    """
    load_data()
    query = normalize_query(string)
    if not query:
        print("No word provided. Please enter a word or phrase.")
        return
    index = 0
    found_any = False
    emitted = set()
    for i in iter_matching_sentence_indices(query):
        line = sentences[i].strip()
        prev_line = sentences[i - 1].strip() if i > 0 else ""
        pair_key = (line, prev_line)
        if pair_key in emitted:
            continue
        print(format_sentence_block(index, line, prev_line))
        print()
        emitted.add(pair_key)
        index += 1
        found_any = True
    if found_any:
        print('All example sentences for the word ' + query + " have been loaded.")
