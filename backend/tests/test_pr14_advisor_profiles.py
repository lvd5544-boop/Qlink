from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models_db import (
    DataSource,
    DataSourceVersion,
    JobRequirement,
    OptimizationIssue,
    TargetRoleProfileSnapshot,
)

pytestmark = pytest.mark.asyncio


def _headers(auth_header, user, key: str | None = None):
    headers = auth_header(user)
    if key:
        headers["Idempotency-Key"] = key
    return headers


async def _source(
    db,
    *,
    layer: str,
    status: str = "approved",
    facts: list[str] | None = None,
    company: str | None = None,
):
    source = DataSource(
        id=str(uuid.uuid4()),
        name=f"PR14 source {layer}",
        owner_organization="Test Publisher",
        acquisition_method="licensed_api",
        license_name="test-license",
        allowed_product_uses=["formal_profile"],
        training_allowed=False,
        contains_personal_data=False,
        processing_region="cn-beijing",
        attribution_text=f"Attribution {layer}",
        status=status,
        layer=layer,
        scope={"company_names": [company]} if company else {},
    )
    db.add(source)
    await db.flush()
    version = DataSourceVersion(
        id=str(uuid.uuid4()),
        source_id=str(source.id),
        external_version="2026-07-29",
        retrieved_at=datetime.now(timezone.utc),
        effective_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
        checksum=f"checksum-{layer}",
        parser_version="test-v1",
        validation_report={"facts": facts or []},
        status="published",
    )
    db.add(version)
    await db.commit()
    return source, version


async def test_four_layers_remain_separate_and_snapshot_is_reproducible(
    client,
    db_session,
    candidate_a,
    job_a,
    auth_header,
):
    job_a.parsed_json = {
        **job_a.parsed_json,
        "company_name": "Example Co",
        "responsibilities": ["建设 Python API", "处理复杂业务背景：" + ("细节" * 180)],
        "required_skills": [{"name": "Python"}, {"name": "Redis"}],
    }
    await db_session.commit()
    await _source(
        db_session,
        layer="C",
        company="Example Co",
        facts=["公司公开年报提到正在建设数字化业务。"],
    )
    await _source(
        db_session,
        layer="D",
        facts=["经许可聚合岗位中 Python 出现频率较高。"],
    )
    await _source(
        db_session,
        layer="E",
        facts=["论坛用户说这家公司只喜欢名校。"],
    )

    first = await client.get(
        f"/advisor/jobs/{job_a.id}/profile",
        headers=_headers(auth_header, candidate_a),
    )
    assert first.status_code == 200, first.text
    payload = first.json()
    assert set(payload["layers"]) == {
        "target_role",
        "occupation",
        "company_context",
        "market_signal",
    }
    target_text = " ".join(
        item["text"] for item in payload["layers"]["target_role"]["requirements"]
    )
    assert "建设 Python API" in target_text
    assert all(
        len(item["canonical_label"]) <= 255
        for item in payload["layers"]["target_role"]["requirements"]
    )
    assert "公司公开年报" not in target_text
    assert "论坛用户" not in str(payload)
    assert "不能覆盖企业明确要求" in payload["layers"]["occupation"]["caveat"]
    assert "不代表该公司偏好" in payload["layers"]["company_context"]["caveat"]

    second = await client.get(
        f"/advisor/jobs/{job_a.id}/profile",
        headers=_headers(auth_header, candidate_a),
    )
    assert second.status_code == 200
    assert second.json()["snapshot"]["id"] == payload["snapshot"]["id"]
    assert second.json()["snapshot"]["snapshot_hash"] == payload["snapshot"]["snapshot_hash"]


async def test_only_owning_employer_can_confirm_job_requirements(
    client,
    db_session,
    candidate_a,
    employer_a,
    employer_b,
    job_a,
    auth_header,
):
    profile = await client.get(
        f"/advisor/jobs/{job_a.id}/profile",
        headers=_headers(auth_header, candidate_a),
    )
    assert profile.status_code == 200

    denied = await client.post(
        f"/advisor/jobs/{job_a.id}/profile/confirm",
        headers=_headers(auth_header, employer_b, "wrong-owner"),
    )
    assert denied.status_code == 404

    confirmed = await client.post(
        f"/advisor/jobs/{job_a.id}/profile/confirm",
        headers=_headers(auth_header, employer_a, "owner-confirm"),
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["snapshot"]["status"] == "employer_confirmed"
    assert all(
        item["employer_confirmed"]
        for item in confirmed.json()["layers"]["target_role"]["requirements"]
    )
    rows = (
        await db_session.execute(select(JobRequirement))
    ).scalars().all()
    assert rows and all(row.employer_confirmed for row in rows)


async def test_employer_explicitly_selects_hard_requirements(
    client,
    db_session,
    employer_a,
    job_a,
    auth_header,
):
    job_a.parsed_json = {
        **(job_a.parsed_json or {}),
        "required_skills": [{"name": "Python"}, {"name": "SQL"}],
        "experience_years": 3,
    }
    await db_session.commit()
    profile = await client.get(
        f"/advisor/jobs/{job_a.id}/profile",
        headers=_headers(auth_header, employer_a),
    )
    requirements = profile.json()["layers"]["target_role"]["requirements"]
    assert requirements
    assert not any(item["is_hard_constraint"] for item in requirements)

    incomplete = await client.post(
        f"/advisor/jobs/{job_a.id}/profile/confirm",
        headers=_headers(auth_header, employer_a, "explicit-incomplete"),
        json={
            "requirements": [
                {
                    "requirement_id": requirements[0]["id"],
                    "classification": "hard",
                }
            ]
        },
    )
    assert incomplete.status_code == 422

    decisions = [
        {
            "requirement_id": item["id"],
            "classification": (
                "hard"
                if item["type"] == "skill" and item["text"] == "Python"
                else "preferred"
            ),
        }
        for item in requirements
    ]
    confirmed = await client.post(
        f"/advisor/jobs/{job_a.id}/profile/confirm",
        headers=_headers(auth_header, employer_a, "explicit-complete"),
        json={"requirements": decisions},
    )
    assert confirmed.status_code == 200, confirmed.text
    rows = confirmed.json()["layers"]["target_role"]["requirements"]
    hard = [item for item in rows if item["is_hard_constraint"]]
    assert [(item["type"], item["text"]) for item in hard] == [("skill", "Python")]


async def test_advisor_facts_always_have_citations(
    client,
    candidate_a,
    resume_a,
    job_a,
    auth_header,
):
    response = await client.post(
        f"/advisor/jobs/{job_a.id}/chat/messages",
        json={"message": "我应该优先准备什么？", "resume_id": str(resume_a.id)},
        headers=_headers(auth_header, candidate_a, "advisor-citations"),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["statements"]
    assert all(statement["citations"] for statement in body["statements"])
    assert all(
        citation["source_id"] and citation["source_version_id"]
        for statement in body["statements"]
        for citation in statement["citations"]
    )
    inference = [item for item in body["statements"] if item["is_inference"]]
    assert inference
    assert body["response_trace"]["snapshot_hash"]
    assert "简历未出现某项技能" in body["response_trace"]["alternative_explanations"][0]


async def test_revoked_source_is_removed_from_future_profile(
    client,
    db_session,
    candidate_a,
    job_a,
    auth_header,
):
    source, _ = await _source(
        db_session,
        layer="D",
        facts=["这一条只能在撤销前出现。"],
    )
    first = await client.get(
        f"/advisor/jobs/{job_a.id}/profile",
        headers=_headers(auth_header, candidate_a),
    )
    assert first.status_code == 200
    first_payload = first.json()
    assert "这一条只能在撤销前出现" in str(first_payload)

    source.status = "revoked"
    await db_session.commit()
    second = await client.get(
        f"/advisor/jobs/{job_a.id}/profile",
        headers=_headers(auth_header, candidate_a),
    )
    assert second.status_code == 200
    second_payload = second.json()
    assert "这一条只能在撤销前出现" not in str(second_payload)
    assert second_payload["snapshot"]["id"] != first_payload["snapshot"]["id"]
    old = await db_session.get(
        TargetRoleProfileSnapshot,
        first_payload["snapshot"]["id"],
    )
    await db_session.refresh(old)
    assert old.status == "superseded"


async def test_diagnostic_creation_is_idempotent_and_conflict_safe(
    client,
    db_session,
    candidate_a,
    resume_a,
    resume_b,
    job_a,
    auth_header,
):
    route = f"/advisor/jobs/{job_a.id}/diagnostics"
    headers = _headers(auth_header, candidate_a, "diagnostic-once")
    first = await client.post(
        route,
        json={"resume_id": str(resume_a.id)},
        headers=headers,
    )
    assert first.status_code == 200, first.text
    first_payload = first.json()
    initial_issue_count = len(
        (
            await db_session.execute(
                select(OptimizationIssue).where(
                    OptimizationIssue.diagnostic_id
                    == first_payload["diagnostic_id"]
                )
            )
        ).scalars().all()
    )

    replay = await client.post(
        route,
        json={"resume_id": str(resume_a.id)},
        headers=headers,
    )
    assert replay.status_code == 200
    assert replay.json() == first_payload
    all_issues = (
        await db_session.execute(select(OptimizationIssue))
    ).scalars().all()
    assert len(all_issues) == initial_issue_count

    conflict = await client.post(
        route,
        json={"resume_id": str(resume_b.id)},
        headers=headers,
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["error"] == "idempotency_conflict"
