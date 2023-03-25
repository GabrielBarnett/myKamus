# This is an experimental python project
print("Loading...")

with open('en-id_dict.txt', encoding="utf-8") as dic:
    dictionary = dic.readlines()

with open('en-id_sentences.txt', encoding='utf-8') as sentences:
    sentences = sentences.readlines()

print("Finished loading")
print("Welcome to myKamus")
print("With help from:")
print("P. Lison and J. Tiedemann, 2016, OpenSubtitles2016: Extracting Large Parallel Corpora from Movie and TV Subtitles. "
      "In Proceedings of the 10th International Conference on Language Resources and Evaluation (LREC 2016)")


def searchForWord():
    print("We are ready to take your word, please type it below:")
    user_input = input()
    de_capitalised = user_input.lower()
    print("Word translations below:")
    dic_count = 30
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
    print("Searching finsihed, would you like to search again? y/n")
    user_response = input()
    if user_response == 'y':
        searchForWord()
    else:
        return "Have a good day"

def searchForWord_clip(string):
    de_capitalised = string.lower()
    dic_count = 30
    sentence_count = 4
    sentence_index = 1
    def_index = 1
    print("Your input: " + de_capitalised)
    print("Word translations below:")
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

# searchForWord()