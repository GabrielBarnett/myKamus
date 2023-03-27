import time
import pyperclip
from main import search_for_word_clip, search_for_word
import keyboard



recent_value = ""
while True:
    tmp_value = pyperclip.paste()
    if keyboard.is_pressed('s'):
        print("What word would you like to search for?\n")
        tmp_value = input()
        search_for_word_clip(tmp_value)
    elif tmp_value != recent_value:
        recent_value = tmp_value
        search_for_word_clip(recent_value)
    time.sleep(0.1)
