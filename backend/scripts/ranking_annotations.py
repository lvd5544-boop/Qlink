#!/usr/bin/env python3
"""Prepare, validate, or compare independent C4-E ranking annotations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.ranking_annotations import (  # noqa: E402
    build_annotation_template,
    compare_annotations,
    validate_annotation,
)
from app.ranking_evaluation import load_ranking_dataset  # noqa: E402

DEFAULT_DATASET = BACKEND_ROOT / "evaluation_data" / "ranking_eval_v1.json"


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_or_print(payload: dict, output: Path | None) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    subparsers = parser.add_subparsers(dest="command", required=True)

    template = subparsers.add_parser("template")
    template.add_argument("--reviewer-alias", required=True)
    template.add_argument("--seed", type=int, required=True)
    template.add_argument("--output", type=Path)

    validate = subparsers.add_parser("validate")
    validate.add_argument("--annotation", type=Path, required=True)

    compare = subparsers.add_parser("compare")
    compare.add_argument("--reviewer-a", type=Path, required=True)
    compare.add_argument("--reviewer-b", type=Path, required=True)
    compare.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dataset = load_ranking_dataset(args.dataset)
    if args.command == "template":
        payload = build_annotation_template(
            dataset,
            reviewer_alias=args.reviewer_alias,
            pair_order_seed=args.seed,
        )
        _write_or_print(payload, args.output)
        return 0
    if args.command == "validate":
        annotation = _read_json(args.annotation)
        labels = validate_annotation(annotation, dataset, require_complete=True)
        _write_or_print(
            {
                "status": "valid",
                "reviewer_alias": annotation["reviewer_alias"],
                "pair_count": len(labels),
            },
            None,
        )
        return 0
    comparison = compare_annotations(
        _read_json(args.reviewer_a),
        _read_json(args.reviewer_b),
        dataset,
    )
    _write_or_print(comparison, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
