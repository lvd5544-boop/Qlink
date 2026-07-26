"""
PR0：已确认 Findings 的回归骨架。

断言写的是「修复后应成立」的正确安全语义；在对应 PR 修复前以 xfail 记录为基线失败。
禁止为了让本文件变绿而削弱断言或修改业务规则。
"""

from __future__ import annotations

import pytest


pytestmark = pytest.mark.asyncio


async def test_employer_a_cannot_audit_resume_without_own_application(
    client, auth_header, employer_a, job_a, resume_b
):
    """仅有自己的岗位、无关联申请时，不得审计他人简历。"""
    res = await client.get(
        f"/applications/job/{job_a.id}/resume/{resume_b.id}/credibility-audit",
        headers=auth_header(employer_a),
    )
    assert res.status_code in {403, 404}


async def test_employer_a_cannot_submit_feedback_on_employer_b_audit(
    client, auth_header, employer_a, audit_record_b, application_b
):
    res = await client.post(
        "/applications/feedback/audit-finding",
        headers=auth_header(employer_a),
        json={
            "audit_record_id": str(audit_record_b.id),
            "application_id": str(application_b.id),
            "finding_id": "finding_x",
            "claim_id": "claim_x",
            "label": "useful",
            "note": "should be rejected",
        },
    )
    assert res.status_code in {403, 404}


async def test_consistency_rewrite_does_not_invent_tech_lead_role():
    from app.resume_consistency import diagnose_resume_consistency

    resume = {
        "expected_job_title": "后端工程师",
        "work_experience": [
            {
                "company": "示例公司",
                "position": "产品助理",
                "description": "负责需求调研与产品规划，推动迭代上线",
            }
        ],
    }
    result = diagnose_resume_consistency(resume)
    issues = result.get("issues") or []
    joined = " ".join(
        str(i.get("example_rewrite") or "") + str((i.get("patch") or {}).get("value") or "")
        for i in issues
    )
    assert "技术负责人" not in joined
    assert "主导研发" not in joined
    # 角色不明时应提问、不可直接采纳虚构角色 patch
    assert any(i.get("needs_followup") or i.get("clarification_question") for i in issues)
    assert all(not (i.get("patch") or {}).get("value") for i in issues)


async def test_apply_rejects_placeholder_fill_field_for_quantification(
    client, auth_header, candidate_a, resume_a
):
    original = resume_a.parsed_json["work_experience"][0]["description"]
    res = await client.post(
        f"/resumes/{resume_a.id}/apply-suggestion",
        headers=auth_header(candidate_a),
        json={
            "patch": {
                "action": "fill_field",
                "section": "work_experience",
                "index": 0,
                "field": "description",
                "value": "（需先完成证据追问，填入真实数据后再预览改写）",
            }
        },
    )
    assert res.status_code in {400, 422}
    # 重新读取确认未被覆盖（修复后）
    detail = await client.get(
        f"/resume/{resume_a.id}",
        headers=auth_header(candidate_a),
    )
    assert detail.status_code == 200
    assert detail.json()["parsed"]["work_experience"][0]["description"] == original


async def test_multi_claim_response_requires_claim_id(
    client, auth_header, candidate_a, application_a
):
    res = await client.post(
        f"/applications/{application_a.id}/clarification-response",
        headers=auth_header(candidate_a),
        json={"body": "指标是 P99 从 200ms 降到 120ms"},
    )
    assert res.status_code in {400, 422}


async def test_candidate_cannot_patch_clarified_directly(
    client, auth_header, candidate_a, application_a
):
    res = await client.patch(
        f"/applications/{application_a.id}/status",
        headers=auth_header(candidate_a),
        json={"status": "clarified"},
    )
    assert res.status_code in {400, 403, 422}
