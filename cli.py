"""
Command-line interface for myKamus searches.
"""

import argparse

from search_functions import load_all_sentences, load_data, search_for_word_clip


def parse_args():
    parser = argparse.ArgumentParser(
        description="Search the myKamus dictionary and sentence corpus.",
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Word or phrase to search for.",
    )
    parser.add_argument(
        "--all-sentences",
        action="store_true",
        help="Load all example sentences for the query.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    load_data()
    if not args.query:
        print("Please provide a word or phrase to search for.")
        return
    if args.all_sentences:
        load_all_sentences(args.query)
    else:
        search_for_word_clip(args.query)


if __name__ == "__main__":
    main()
