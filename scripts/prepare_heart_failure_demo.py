"""Prepare the bundled HeartFailure demonstration without changing source data."""
import argparse
import json
from pathlib import Path

from memstara.heart_failure_demo import FEATURES, TARGET, prepare  # noqa: F401


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.corpus, args.destination), indent=2))
