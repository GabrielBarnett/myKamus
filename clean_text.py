import re


def remove_tags(string):
    clean_text = re.sub('<.*?>', '', string)
    return clean_text

with open("en-id.tmx", encoding="UTF-8") as dic:
    dictionary = dic.readlines()


def operate_on_all_lines(file):
    file_as_list = []

    for line in file:
        clean_text = remove_tags(line)
        file_as_list.append(clean_text)
    return file_as_list

# for line in dictionary:
#     print(line)

if __name__ == "__main__":
    print(operate_on_all_lines(dictionary))
    with open('en-id_sentences.txt', 'w', encoding="utf-8") as newdict:
        for definition in operate_on_all_lines(dictionary):
            newdict.write(definition)
