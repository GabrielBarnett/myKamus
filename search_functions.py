"""
Module contains the functions necessary to search through the databases provided byt the user.
"""

print("myKamus is loading...\n")

with open('en-id_dict.txt', encoding="utf-8") as dic:
    dictionary = dic.readlines()

with open('en-id_sentences.txt', encoding='utf-8') as sentences:
    sentences = sentences.readlines()
def search_for_word():
    """
    Not currently in use, defined for testing purposes and the
    :return: string(s)
    """
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
def load_all_sentences(string):
    """
    :param string: word that is to be searched
    :return: returns all of the sentences that are in the sentence file for the string
    """
    index = 0
    for line in sentences:
        if string.lower() in line:
            print(str(index) + ": " + line)
            print(str(index) + ": " + prev_line)
            index += 1
        prev_line = line