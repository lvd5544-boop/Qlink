#!/usr/bin/env python3
"""Run the isolated synthetic C5 hypothesis evaluation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.hypothesis_evaluation import (  # noqa: E402
    load_hypothesis_dataset,
    run_hypothesis_evaluation,
)


def main() -> int:
    path = BACKEND_ROOT / "evaluation_data" / "hypothesis_eval_synthetic_v1.json"
    result = run_hypothesis_evaluation(load_hypothesis_dataset(path, expected_pool="synthetic"))
    sys.stdout.write(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
