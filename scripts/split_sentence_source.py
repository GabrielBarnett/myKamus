import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sentence_source.layout import SentenceSourceValidationError
from sentence_source.splitter import split_sentence_source, verify_sentence_source


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Split or verify the myKamus sentence source chunks."
    )
    parser.add_argument("--source", help="Legacy en-id_sentences.txt source file.")
    parser.add_argument("--output", required=True, help="Sentence source output directory.")
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify an existing sentence source directory instead of rebuilding it.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.verify:
            result = verify_sentence_source(args.output)
            print(
                "Verified {total_pair_count} sentence pairs across {chunk_count} chunks."
                .format(**result)
            )
            return 0

        if not args.source:
            print("--source is required unless --verify is used.", file=sys.stderr)
            return 2

        result = split_sentence_source(args.source, args.output)
        print(
            "Built {total_pair_count} sentence pairs into {chunk_count} chunks."
            .format(**result)
        )
        return 0
    except SentenceSourceValidationError as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
