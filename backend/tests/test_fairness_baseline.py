"""PR7 fairness baseline unit + admin route checks."""

from __future__ import annotations

from app.fairness import (
    ASSISTIVE_ONLY_DISCLAIMER,
    compute_legal_group_impact,
    impact_ratio,
    wilson_interval,
)


def test_impact_ratio_underpowered():
    result = impact_ratio({"engineering": 0.2})
    assert result["status"] == "insufficient_groups"


def test_impact_ratio_computed():
    result = impact_ratio({"engineering": 0.5, "sales": 0.4})
    assert result["status"] == "computed"
    assert result["reference_group"] == "engineering"
    assert result["ratios"]["sales"] == 0.8


def test_wilson_interval_bounds():
    interval = wilson_interval(10, 40)
    assert interval["point"] == 0.25
    assert 0.0 <= interval["low"] <= interval["point"] <= interval["high"] <= 1.0


def test_legal_group_impact_requires_attestation():
    blocked = compute_legal_group_impact(
        [{"group_id": "a", "applicants": 40, "selected": 10}],
        legal_basis_attested=False,
    )
    assert blocked["status"] == "blocked"


def test_legal_group_impact_computes_when_attested():
    result = compute_legal_group_impact(
        [
            {"group_id": "a", "applicants": 40, "selected": 20},
            {"group_id": "b", "applicants": 40, "selected": 10},
        ],
        legal_basis_attested=True,
    )
    assert result["status"] == "computed"
    assert result["ratios"]["b"] == 0.5


async def test_fairness_baseline_requires_admin(client, auth_header, candidate_a):
    response = await client.get(
        "/analytics/fairness/baseline",
        headers=auth_header(candidate_a),
    )
    assert response.status_code == 403


async def test_fairness_baseline_admin_ok(client, auth_header, admin_user):
    response = await client.get(
        "/analytics/fairness/baseline",
        headers=auth_header(admin_user),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["disclaimer"] == ASSISTIVE_ONLY_DISCLAIMER
    assert body["policy"]["auto_reject_forbidden"] is True
    assert body["policy"]["sensitive_attribute_collection"] is False
    assert "by_role_family" in body
    assert body["impact_ratio"]["status"] == "not_computed"
    assert body["impact_ratio"]["ratios"] == {}
    assert "proxy_variable_audit" in body
    assert "school_tier" in body["proxy_variable_audit"]
    assert "model_versions" in body
    assert "human_review_and_appeals" in body
    assert body["overall"]["score_mean_ci"]["n"] >= 0
    assert body["pilot_disclosure"]["no_conclusion_when_underpowered"] is True
