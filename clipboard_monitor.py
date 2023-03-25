import time
import pyperclip
from main import searchForWord_clip


recent_value = ""
while True:
    tmp_value = pyperclip.paste()
    if tmp_value != recent_value:
        recent_value = tmp_value
        searchForWord_clip(recent_value)
    time.sleep(0.1)