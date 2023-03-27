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
email me at gabrielcbarnett@gmail.com. There will be no cost involved for a license to use in a corporate, government
or military environment, it is so we can discuss any needs you might have for updates, specific vocabulary
or language requirements. Again, it will be free but a representative from your organisation must make contact with
me first.

If you like this program and have found it useful for your work, feel free to email with your success story or any
improvements that you might suggest.
"""

print("Loading...")

with open('en-id_dict.txt', encoding="utf-8") as dic:
    dictionary = dic.readlines()

with open('en-id_sentences.txt', encoding='utf-8') as sentences:
    sentences = sentences.readlines()

print("Finished loading")
print("Welcome to myKamus")
print("With help from:")
print("P. Lison and J. Tiedemann, 2016, OpenSubtitles2016: Extracting Large Parallel Corpora from Movie and TV "
      "Subtitles. ""In Proceedings of the 10th International Conference on "
      "Language Resources and Evaluation (LREC 2016)")


def search_for_word():
    print("We are ready to take your word, please type it below:")
    user_input = input()
    de_capitalised = user_input.lower()
    print("Word translations below:")
    sentence_count = 4
    sentence_index = 1
    def_index = 1
    for line in dictionary:
        if de_capitalised in line:
            print(str(def_index) + ": " + line)
            def_index += 1
    print("Example sentences below:")
    for line in sentences:
        if de_capitalised in line and sentence_count > 0:
            print(str(sentence_index) + ": " + line)
            print(str(sentence_index) + ": " + prev_line)
            sentence_index += 1
            sentence_count -= 1
        prev_line = line
    print("Searching finished, would you like to search again? y/n")


def search_for_word_clip(string):
    de_capitalised = string.lower()
    sentence_count = 4
    sentence_index = 1
    def_index = 1
    print("Your input: " + de_capitalised)
    print("Word translations for " + de_capitalised + " below:")
    for line in dictionary:
        if de_capitalised in line:
            print(str(def_index) + ": " + line)
            def_index += 1
    print("Example sentences for " + de_capitalised + " below:")
    for line in sentences:
        if de_capitalised in line and sentence_count > 0:
            print(str(sentence_index) + ": " + line)
            print(str(sentence_index) + ": " + prev_line)
            sentence_index += 1
            sentence_count -= 1
        prev_line = line
