#!/usr/bin/env python3
"""Run the fixed C4-E ranking evaluation without network or database access."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.ranking_evaluation import load_ranking_dataset, run_ranking_evaluation  # noqa: E402

DEFAULT_DATASET = BACKEND_ROOT / "evaluation_data" / "ranking_eval_v1.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--output", type=Path, help="Optional JSON result path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.k <= 0:
        raise SystemExit("--k must be positive")
    result = run_ranking_evaluation(load_ranking_dataset(args.dataset), k=args.k)
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    sys.stdout.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
