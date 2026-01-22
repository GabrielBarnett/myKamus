"""
myKamus by Gabriel Barnett

myKamus is An open source instant translation software for Indonesian that provides the user
with complex Indonesian-English translation capabilities.

To run the program you cna either do it from inside an IDE of your choice, or with Python installed either:
    a) Run clipboard_monitor through IDLE
    b) Launch a Powershell session through the directory and run clipboard_monitor through it

It utilises several open source bitext corpus to provide access to over 50 million example sentences and words for
the purposes of translation.

The program is free to use for academic and non-commercial applicaitons, if you wish to use it for something else
email me at gabrielcbarnett@gmail.com. There will be no cost involved, it is so we can discuss any needs you might have
for updates, specific vocabulary or language requirements. Again, it will be free but a representative from your
organisation must make contact with me first.

If you like this program and have found it useful for your work, feel free to email with your success story or any
improvements that you might suggest.

Bitext corpus for sentences sourced from:

P. Lison and J. Tiedemann, 2016, OpenSubtitles2016: Extracting Large Parallel Corpora from Movie and TV
Subtitles. In Proceedings of the 10th International Conference on Language Resources and Evaluation (LREC 2016)
"""

import importlib.util
import subprocess
import sys
import time


def ensure_dependencies():
    missing = []
    for module_name in ("pyperclip", "keyboard"):
        if importlib.util.find_spec(module_name) is None:
            missing.append(module_name)
    if not missing:
        return
    print("Missing dependencies: " + ", ".join(missing))
    print("Not installing these dependencies will cause the program to not run.")
    consent = input("Install missing dependencies now? (y/n): ").strip().lower()
    if consent == "y":
        subprocess.run([sys.executable, "-m", "pip", "install", *missing], check=False)
    else:
        print("Dependencies not installed. The program may not run correctly.")


ensure_dependencies()

import pyperclip
import keyboard
from search_functions import load_all_sentences, load_data, search_for_word_clip

warned_hotkeys = set()


def safe_is_pressed(hotkey):
    try:
        return keyboard.is_pressed(hotkey)
    except ValueError as error:
        if hotkey not in warned_hotkeys:
            print("Warning: hotkey '" + hotkey + "' could not be read (" + str(error) + ").")
            print("This may be due to OS-level keyboard limitations or missing permissions.")
            warned_hotkeys.add(hotkey)
        return False

print("Welcome to myKamus by Gabriel Barnett\n")
print("Instructions:\n")
print("1: Highlight an Indonesian word or short phrase and copy it (ctrl+c)\n"
      "2: Watch your translations come up in real time, if there are no sentences or word translations then the word may be too unique  \n"
      "or niche to search. If this happens the recommendation is to search substrings within the Indonesian word itself. Ensure that you\n"
      "have not copied any spaces around single words or phrases\n"
      "3: If you would like to search for a specific word click on the console and press ctrl+s and then type in your desired word or phrase.\n"
      "5: If you wish to show the rest of the example sentences you may press the l key. WARNING: Depending on how common"
      "or simple the word is doing so may bring back many hundreds of thousands of results.")

load_data()

recent_value = pyperclip.paste()
tmp_value = pyperclip.paste()
ctrl_s_pressed = False
l_pressed = False

while True:
    tmp_value = pyperclip.paste()
    ctrl_s_current = safe_is_pressed('ctrl+s')
    l_current = safe_is_pressed('l')
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
    time.sleep(0.1)
