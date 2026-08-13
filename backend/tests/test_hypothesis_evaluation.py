from copy import deepcopy
from pathlib import Path

import pytest

from app.hypothesis_evaluation import load_hypothesis_dataset, run_hypothesis_evaluation

DATA_DIR = Path(__file__).resolve().parents[1] / "evaluation_data"


def test_synthetic_hypothesis_pool_passes_without_real_samples():
    dataset = load_hypothesis_dataset(
        DATA_DIR / "hypothesis_eval_synthetic_v1.json", expected_pool="synthetic"
    )
    result = run_hypothesis_evaluation(dataset)
    assert result["passed"] is True
    assert result["sample_count"] == 3
    assert result["real_confirmed_samples_used"] == 0
    assert max(item["hypothesis_count"] for item in result["results"]) <= 2


def test_real_confirmed_manifest_is_empty_and_separate():
    manifest = load_hypothesis_dataset(
        DATA_DIR / "hypothesis_eval_real_confirmed_manifest.json",
        expected_pool="real_confirmed",
    )
    assert manifest["samples"] == []
    with pytest.raises(ValueError, match="only the isolated synthetic pool"):
        run_hypothesis_evaluation(manifest)


def test_synthetic_pool_rejects_identity_fields(tmp_path):
    dataset = load_hypothesis_dataset(
        DATA_DIR / "hypothesis_eval_synthetic_v1.json", expected_pool="synthetic"
    )
    unsafe = deepcopy(dataset)
    unsafe["samples"][0]["user_id"] = "real-user"
    path = tmp_path / "unsafe.json"
    path.write_text(__import__("json").dumps(unsafe), encoding="utf-8")
    with pytest.raises(ValueError, match="identity keys"):
        load_hypothesis_dataset(path, expected_pool="synthetic")


def test_pool_mismatch_is_rejected():
    with pytest.raises(ValueError, match="pool mismatch"):
        load_hypothesis_dataset(
            DATA_DIR / "hypothesis_eval_synthetic_v1.json",
            expected_pool="real_confirmed",
        )
