import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sentence_data import builder, layout


def parse_args():
    parser = argparse.ArgumentParser(description="Build or verify the sharded sentence dataset.")
    parser.add_argument(
        "--source",
        type=Path,
        help="Path to the legacy sentence text file used for builds.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=layout.DEFAULT_SENTENCE_DATA_DIR,
        help="Directory containing the sharded sentence dataset.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify an existing dataset instead of rebuilding it.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if args.verify:
        verification = builder.verify_sentence_dataset(args.output)
        print(
            f"Verified {verification['sentence_count']} sentence pairs across "
            f"{verification['shard_count']} shards."
        )
        return 0

    if args.source is None:
        raise SystemExit("--source is required unless --verify is used.")

    result = builder.build_sentence_dataset(args.source, args.output)
    print(
        f"Built {result['sentence_count']} sentence pairs into "
        f"{len(result['manifest']['shards'])} shards."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
