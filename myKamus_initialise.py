"""
Legacy clipboard monitor for myKamus.
"""

import importlib
import sys
import time

from search_functions import load_all_sentences, load_config, load_data, search_for_word_clip


def import_runtime_dependency(module_name):
    try:
        return importlib.import_module(module_name)
    except ImportError as error:
        raise RuntimeError(
            "Missing dependency '"
            + module_name
            + "'. Install dependencies with: pip install -r requirements.txt"
        ) from error


def print_instructions():
    print("Welcome to myKamus by Gabriel Barnett\n")
    print("Instructions:\n")
    print(
        "1: Highlight an Indonesian word or short phrase and copy it (ctrl+c)\n"
        "2: Watch your translations come up in real time. If there are no sentences "
        "or word translations, try searching substrings within the Indonesian word "
        "and ensure there are no surrounding spaces.\n"
        "3: To search manually, focus the console, press ctrl+s, and type your word "
        "or phrase.\n"
        "4: To show every matching example sentence in the console, press l. "
        "Common words may produce very large output."
    )


def safe_is_pressed(keyboard, hotkey, warned_hotkeys):
    try:
        return keyboard.is_pressed(hotkey)
    except ValueError as error:
        if hotkey not in warned_hotkeys:
            print("Warning: hotkey '" + hotkey + "' could not be read (" + str(error) + ").")
            print("This may be due to OS-level keyboard limitations or missing permissions.")
            warned_hotkeys.add(hotkey)
        return False


def main():
    try:
        pyperclip = import_runtime_dependency("pyperclip")
        keyboard = import_runtime_dependency("keyboard")
    except RuntimeError as error:
        print(error)
        return 1

    print_instructions()
    print("\nmyKamus is loading...\n")

    config = load_config()
    load_data()

    recent_value = pyperclip.paste()
    tmp_value = recent_value
    ctrl_s_pressed = False
    l_pressed = False
    warned_hotkeys = set()

    manual_search_hotkey = config["hotkeys"]["manual_search"]
    load_all_hotkey = config["hotkeys"]["load_all_sentences"]
    poll_interval = config["poll_interval"]

    while True:
        tmp_value = pyperclip.paste()
        ctrl_s_current = safe_is_pressed(keyboard, manual_search_hotkey, warned_hotkeys)
        l_current = safe_is_pressed(keyboard, load_all_hotkey, warned_hotkeys)
        if ctrl_s_current and not ctrl_s_pressed:
            print("What word would you like to search for?\n")
            tmp_value = input()
            search_for_word_clip(tmp_value)
        elif l_current and not l_pressed:
            load_all_sentences(tmp_value)
        elif tmp_value != recent_value:
            recent_value = tmp_value
            search_for_word_clip(recent_value)
        ctrl_s_pressed = ctrl_s_current
        l_pressed = l_current
        time.sleep(poll_interval)


if __name__ == "__main__":
    sys.exit(main())
