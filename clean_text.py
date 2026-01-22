from pathlib import Path
import re


def remove_tags(string):
    # Strip XML-like tags from a TMX line.
    clean_text = re.sub('<.*?>', '', string)
    return clean_text

BASE_DIR = Path(__file__).resolve().parent

with (BASE_DIR / "en-id.tmx").open(encoding="UTF-8") as dic:
    # Raw TMX lines are processed into plain text sentence pairs.
    dictionary = dic.readlines()


def operate_on_all_lines(file):
    file_as_list = []

    for line in file:
        # Normalize each line by removing XML tags.
        clean_text = remove_tags(line)
        file_as_list.append(clean_text)
    return file_as_list

# for line in dictionary:
#     print(line)

if __name__ == "__main__":
    print(operate_on_all_lines(dictionary))
    with (BASE_DIR / "en-id_sentences.txt").open('w', encoding="utf-8") as newdict:
        for definition in operate_on_all_lines(dictionary):
            newdict.write(definition)
