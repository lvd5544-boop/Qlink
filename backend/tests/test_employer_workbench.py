from __future__ import annotations

import pytest

from app.models import JobInfo


pytestmark = pytest.mark.asyncio


async def test_post_job_returns_editable_job_id_and_keeps_raw_text(
    client,
    auth_header,
    employer_a,
    monkeypatch,
):
    monkeypatch.setattr(
        "app.main.parse_job_with_llm",
        lambda _text: JobInfo(
            title="平台工程师",
            responsibilities=["维护服务"],
            requirements="熟悉 Python",
        ),
    )
    response = await client.post(
        "/post-job",
        headers=auth_header(employer_a),
        params={"description_text": "原始 JD 文本"},
    )
    assert response.status_code == 200
    created = response.json()
    assert created["job_id"]
    assert created["title"] == "平台工程师"
    assert created["publication_status"] == "draft"

    browse_before = await client.get("/browse-jobs")
    assert created["job_id"] not in {item["id"] for item in browse_before.json()}
    detail_before = await client.get(f"/job/{created['job_id']}")
    assert detail_before.status_code == 404

    jobs = await client.get("/jobs/mine", headers=auth_header(employer_a))
    assert jobs.status_code == 200
    assert jobs.json()[0]["id"] == created["job_id"]
    assert jobs.json()[0]["raw_text"] == "原始 JD 文本"

    edited = {
        **jobs.json()[0]["parsed"],
        "responsibilities": ["维护服务", "优化发布流程"],
        "soft_skills": ["跨团队协作"],
    }
    update = await client.put(
        f"/jobs/{created['job_id']}",
        headers=auth_header(employer_a),
        json={"parsed_json": edited},
    )
    assert update.status_code == 200
    refreshed = await client.get("/jobs/mine", headers=auth_header(employer_a))
    assert refreshed.json()[0]["parsed"]["responsibilities"] == ["维护服务", "优化发布流程"]
    assert refreshed.json()[0]["parsed"]["requirements"] == "熟悉 Python"

    profile = await client.get(
        f"/advisor/jobs/{created['job_id']}/profile",
        headers=auth_header(employer_a),
    )
    requirements = profile.json()["layers"]["target_role"]["requirements"]
    decisions = [
        {
            "requirement_id": item["id"],
            "classification": "hard" if index == 0 else "preferred",
        }
        for index, item in enumerate(requirements)
    ]
    published = await client.post(
        f"/advisor/jobs/{created['job_id']}/profile/confirm",
        headers={**auth_header(employer_a), "Idempotency-Key": "publish-workbench-job"},
        json={"requirements": decisions},
    )
    assert published.status_code == 200, published.text
    published_requirements = published.json()["layers"]["target_role"]["requirements"]
    assert published_requirements[0]["is_hard_constraint"] is True
    assert all(item["employer_confirmed"] for item in published_requirements)
    browse_after = await client.get("/browse-jobs")
    assert created["job_id"] in {item["id"] for item in browse_after.json()}


async def test_employer_application_center_and_materials_are_authorized_snapshots(
    client,
    auth_header,
    employer_a,
    employer_b,
    candidate_a,
    application_a,
):
    center = await client.get("/applications/employer/all", headers=auth_header(employer_a))
    assert center.status_code == 200
    assert [item["id"] for item in center.json()] == [str(application_a.id)]
    assert center.json()[0]["candidate_name"] == "Candidate A"

    materials = await client.get(
        f"/applications/{application_a.id}/materials",
        headers=auth_header(employer_a),
    )
    assert materials.status_code == 200
    payload = materials.json()
    assert payload["initial_submission"]["raw_text"] == "Candidate A resume"
    assert payload["initial_submission"]["parsed_json"]["name"] == "Candidate A"
    assert payload["versions"][0]["version_id"] == "v1"

    other_employer = await client.get(
        f"/applications/{application_a.id}/materials",
        headers=auth_header(employer_b),
    )
    assert other_employer.status_code in {403, 404}

    candidate = await client.get(
        f"/applications/{application_a.id}/materials",
        headers=auth_header(candidate_a),
    )
    assert candidate.status_code == 200
