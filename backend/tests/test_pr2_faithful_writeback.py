"""
PR2：忠实写回与多 Claim 绑定回归测试。
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_malicious_append_to_fill_field_rejected(
    client, auth_header, candidate_a, resume_a, db_session
):
    """恶意客户端把 append_quantification 改成 fill_field 仍应 4xx，原简历不变。"""
    from app.models_db import ResumeSuggestion
    from app.resume_suggestion_store import sync_suggestions_for_source

    original = resume_a.parsed_json["work_experience"][0]["description"]
    await sync_suggestions_for_source(
        db_session,
        resume_a.id,
        "health_check",
        [
            {
                "id": "quant_work_0",
                "source": "health_check",
                "title": "补充量化",
                "description": "需证据",
                "requires_evidence": True,
                "needs_followup": True,
                "original_text": original,
                "suggested_text": "（需先完成证据追问，填入真实数据后再预览改写）",
                "patch": {
                    "action": "append_quantification",
                    "section": "work_experience",
                    "index": 0,
                    "value": None,
                    "requires_evidence": True,
                },
            }
        ],
    )

    from sqlalchemy import select

    row = (
        (
            await db_session.execute(
                select(ResumeSuggestion).where(
                    ResumeSuggestion.resume_id == resume_a.id,
                    ResumeSuggestion.suggestion_key == "quant_work_0",
                )
            )
        )
        .scalars()
        .first()
    )
    assert row is not None

    res = await client.post(
        f"/resumes/{resume_a.id}/apply-suggestion",
        headers=auth_header(candidate_a),
        json={
            "suggestion_id": row.id,
            "patch": {
                "action": "fill_field",
                "section": "work_experience",
                "index": 0,
                "field": "description",
                "value": "（需先完成证据追问，填入真实数据后再预览改写）",
            },
        },
    )
    assert res.status_code in {400, 422}

    detail = await client.get(
        f"/resume/{resume_a.id}",
        headers=auth_header(candidate_a),
    )
    assert detail.json()["parsed"]["work_experience"][0]["description"] == original

    await db_session.refresh(row)
    assert row.status == "pending"


@pytest.mark.asyncio
async def test_multi_claim_with_claim_id_only_closes_one(
    client, auth_header, candidate_a, application_a
):
    """显式 claim_id 只关闭对应线程，申请仍为 needs_clarification。"""
    res = await client.post(
        f"/applications/{application_a.id}/clarification-response",
        headers=auth_header(candidate_a),
        json={
            "body": "第一个指标是 P99 从 200ms 降到 120ms",
            "claim_id": "work_experience_0_action_0",
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data.get("claim_id") == "work_experience_0_action_0"
    assert data.get("open_claim_count") == 1
    assert data["application"]["status"] == "needs_clarification"


def test_consistency_explicit_tech_title_may_reframe_without_inventing():
    """职位已是技术岗时，可用原职位名忠实重组，仍不得注入负责人/主导研发。"""
    from app.resume_consistency import diagnose_resume_consistency

    resume = {
        "expected_job_title": "后端工程师",
        "work_experience": [
            {
                "company": "示例公司",
                "position": "后端工程师",
                "description": "负责需求调研与产品规划，推动迭代上线",
            }
        ],
    }
    result = diagnose_resume_consistency(resume)
    joined = " ".join(
        str(i.get("example_rewrite") or "") + str((i.get("patch") or {}).get("value") or "")
        for i in (result.get("issues") or [])
    )
    assert "技术负责人" not in joined
    assert "主导研发" not in joined
