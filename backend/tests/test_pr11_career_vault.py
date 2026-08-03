"""PR11 gates for long-lived claims, Vault authorization and immutable versions."""

from __future__ import annotations

from sqlalchemy import select

from app.claim_passport import sync_resume_claims
from app.models_db import CareerExperience, EvidenceArtifact, ResumeClaim, ResumeVersion
from app.career_vault_routes import EVIDENCE_FILE_EXTENSIONS
from app.safe_upload import ALLOWED_MIME


async def _sync_one(db_session, resume, actor_id):
    claims = await sync_resume_claims(
        db_session, resume, actor_id=str(actor_id), reason="pr11_test"
    )
    await db_session.commit()
    return claims[0]


async def test_claim_id_stays_stable_and_owner_is_backfilled(
    db_session, resume_a, candidate_a
):
    first = await _sync_one(db_session, resume_a, candidate_a.id)
    stable_id = str(first.id)
    second = await _sync_one(db_session, resume_a, candidate_a.id)
    assert str(second.id) == stable_id
    stored = await db_session.get(ResumeClaim, stable_id)
    assert stored.user_id == str(candidate_a.id)
    assert stored.source_object_id == str(resume_a.id)


async def test_resume_sections_seed_long_lived_experiences_and_link_claims(
    db_session, resume_a, candidate_a
):
    claims = await sync_resume_claims(
        db_session, resume_a, actor_id=str(candidate_a.id), reason="memory_network_test"
    )
    await db_session.commit()

    experiences = (
        await db_session.execute(
            select(CareerExperience).where(
                CareerExperience.user_id == str(candidate_a.id)
            )
        )
    ).scalars().all()
    linked = [claim for claim in claims if claim.section in {"projects", "work_experience"}]

    assert experiences
    assert linked
    assert all(claim.career_experience_id for claim in linked)


def test_evidence_vault_accepts_safe_text_code_files_without_expanding_resume_uploads():
    for extension in {".py", ".ipynb", ".js", ".ts", ".sql"}:
        assert extension in EVIDENCE_FILE_EXTENSIONS
        assert extension in ALLOWED_MIME


async def test_cross_tenant_claim_and_map_are_not_readable(
    client, db_session, resume_a, candidate_a, candidate_b, employer_a, auth_header
):
    claim = await _sync_one(db_session, resume_a, candidate_a.id)

    denied = await client.get(
        f"/career-passport/claims/{claim.id}/history",
        headers=auth_header(candidate_b),
    )
    assert denied.status_code == 404

    employer_denied = await client.get(
        "/career-passport/map?view=evidence",
        headers=auth_header(employer_a),
    )
    assert employer_denied.status_code == 403


async def test_map_filters_other_owner_nodes_and_paginates(
    client, db_session, resume_a, resume_b, candidate_a, candidate_b, auth_header
):
    claim_a = await _sync_one(db_session, resume_a, candidate_a.id)
    claim_b = await _sync_one(db_session, resume_b, candidate_b.id)
    artifact_a = EvidenceArtifact(
        owner_user_id=str(candidate_a.id),
        artifact_type="user_statement",
        title="A private evidence",
        allowed_uses=["resume_assistance"],
    )
    artifact_b = EvidenceArtifact(
        owner_user_id=str(candidate_b.id),
        artifact_type="user_statement",
        title="B hidden evidence",
        allowed_uses=["resume_assistance"],
    )
    db_session.add_all([artifact_a, artifact_b])
    await db_session.commit()

    linked = await client.post(
        f"/evidence-vault/claims/{claim_a.id}/links",
        json={"artifact_id": str(artifact_a.id), "relationship": "supports"},
        headers=auth_header(candidate_a),
    )
    assert linked.status_code == 200, linked.text
    other_linked = await client.post(
        f"/evidence-vault/claims/{claim_b.id}/links",
        json={"artifact_id": str(artifact_b.id), "relationship": "supports"},
        headers=auth_header(candidate_b),
    )
    assert other_linked.status_code == 200

    response = await client.get(
        "/career-passport/map?view=evidence&limit=100",
        headers=auth_header(candidate_a),
    )
    assert response.status_code == 200
    payload = response.json()
    labels = {node["label"] for node in payload["nodes"]}
    assert "A private evidence" in labels
    assert "B hidden evidence" not in labels
    assert payload["privacy_boundary"] == "owner_authorized_server_projection"

    page = await client.get(
        "/career-passport/map?view=evidence&limit=1",
        headers=auth_header(candidate_a),
    )
    assert page.json()["page"]["limit"] == 1
    assert page.json()["page"]["has_more"] is True


async def test_withdrawn_artifact_cannot_be_linked_again(
    client, db_session, resume_a, candidate_a, auth_header
):
    claim = await _sync_one(db_session, resume_a, candidate_a.id)
    initialized = await client.post(
        "/evidence-vault/artifacts/init-upload",
        json={
            "artifact_type": "user_statement",
            "title": "可撤回说明",
            "allowed_uses": ["resume_assistance"],
            "default_visibility": "private",
        },
        headers=auth_header(candidate_a),
    )
    assert initialized.status_code == 200
    artifact_id = initialized.json()["artifact"]["id"]
    removed = await client.delete(
        f"/evidence-vault/artifacts/{artifact_id}",
        headers=auth_header(candidate_a),
    )
    assert removed.status_code == 200
    relink = await client.post(
        f"/evidence-vault/claims/{claim.id}/links",
        json={"artifact_id": artifact_id, "relationship": "supports"},
        headers=auth_header(candidate_a),
    )
    assert relink.status_code in {404, 409}


async def test_resume_version_snapshot_is_immutable(
    client, db_session, resume_a, candidate_a, auth_header
):
    claim = await _sync_one(db_session, resume_a, candidate_a.id)
    created = await client.post(
        f"/career-passport/resumes/{resume_a.id}/versions",
        json={"created_reason": "manual_edit"},
        headers=auth_header(candidate_a),
    )
    assert created.status_code == 200, created.text
    version_id = created.json()["version"]["id"]
    original_hash = created.json()["version"]["content_hash"]

    resume_a.parsed_json = {**resume_a.parsed_json, "summary": "later mutation"}
    claim.current_text = "later claim mutation"
    await db_session.commit()

    version = await db_session.get(ResumeVersion, version_id)
    assert version.content_hash == original_hash
    assert version.parsed_json_snapshot.get("summary") != "later mutation"


async def test_application_snapshot_remains_only_employer_view(
    client, application_a, employer_a, candidate_b, auth_header
):
    allowed = await client.get(
        f"/applications/{application_a.id}/claim-passport",
        headers=auth_header(employer_a),
    )
    assert allowed.status_code == 200
    denied = await client.get(
        f"/applications/{application_a.id}/claim-passport",
        headers=auth_header(candidate_b),
    )
    assert denied.status_code == 404


async def test_job_map_is_requirement_to_claim_projection(
    client, db_session, resume_a, candidate_a, job_a, auth_header
):
    await _sync_one(db_session, resume_a, candidate_a.id)
    response = await client.get(
        f"/career-passport/map?view=job&job_id={job_a.id}&limit=100",
        headers=auth_header(candidate_a),
    )
    assert response.status_code == 200
    payload = response.json()
    requirement_nodes = [node for node in payload["nodes"] if node["type"] == "requirement"]
    assert {node["label"] for node in requirement_nodes} >= {"Python", "SQL"}
    assert all(node["meta"]["job_id"] == str(job_a.id) for node in requirement_nodes)


async def test_capability_map_uses_skills_and_projects_not_claim_types_or_dates(
    client, db_session, resume_a, candidate_a, auth_header
):
    resume_a.parsed_json = {
        **resume_a.parsed_json,
        "projects": [
            {
                "name": "Air quality forecasting",
                "duration": "2024.01 - 2024.06",
                "description": "Used Python and SQL to evaluate forecasting models.",
            }
        ],
    }
    await db_session.commit()
    await _sync_one(db_session, resume_a, candidate_a.id)

    response = await client.get(
        "/career-passport/map?view=capability&limit=100",
        headers=auth_header(candidate_a),
    )
    assert response.status_code == 200
    payload = response.json()
    capabilities = [node for node in payload["nodes"] if node["type"] == "capability"]
    assert {node["label"] for node in capabilities} >= {"Python", "SQL"}
    assert not {"action", "title", "identity"} & {node["label"] for node in capabilities}
    projects = [node for node in payload["nodes"] if node["type"] == "project"]
    assert any(node["label"] == "Air quality forecasting" for node in projects)
    assert all("2024.01 - 2024.06" != node["label"] for node in payload["nodes"])
    assert any(edge["relationship"] == "在该项目/经历中使用" for edge in payload["edges"])


async def test_evidence_map_only_contains_claims_with_material_relationships(
    client, db_session, resume_a, candidate_a, auth_header
):
    claims = await sync_resume_claims(
        db_session, resume_a, actor_id=str(candidate_a.id), reason="evidence-map-test"
    )
    await db_session.commit()
    target = next(claim for claim in claims if claim.claim_type != "entry")
    artifact = EvidenceArtifact(
        owner_user_id=str(candidate_a.id),
        artifact_type="user_statement",
        title="Performance note",
        allowed_uses=["resume_assistance"],
    )
    db_session.add(artifact)
    await db_session.commit()
    linked = await client.post(
        f"/evidence-vault/claims/{target.id}/links",
        json={"artifact_id": str(artifact.id), "relationship": "supports"},
        headers=auth_header(candidate_a),
    )
    assert linked.status_code == 200

    response = await client.get(
        "/career-passport/map?view=evidence&limit=100",
        headers=auth_header(candidate_a),
    )
    payload = response.json()
    claim_nodes = [node for node in payload["nodes"] if node["type"] == "claim"]
    assert [node["id"] for node in claim_nodes] == [f"claim:{target.id}"]
    assert any(node["label"] == "Performance note" for node in payload["nodes"])


async def test_claim_split_and_merge_preserve_supersession_events(
    client, db_session, resume_a, candidate_a, auth_header
):
    original = await _sync_one(db_session, resume_a, candidate_a.id)
    split = await client.post(
        f"/career-passport/claims/{original.id}/split",
        json={"texts": ["负责订单模块", "完成性能优化"]},
        headers=auth_header(candidate_a),
    )
    assert split.status_code == 200, split.text
    child_ids = split.json()["claim_ids"]
    stored_original = await db_session.get(ResumeClaim, str(original.id))
    await db_session.refresh(stored_original)
    assert stored_original.workflow_state == "withdrawn"
    assert stored_original.superseded_by_claim_id == child_ids[0]

    merged = await client.post(
        "/career-passport/claims/merge",
        json={"claim_ids": child_ids, "text": "负责订单模块并完成性能优化"},
        headers=auth_header(candidate_a),
    )
    assert merged.status_code == 200, merged.text
    assert merged.json()["source_claim_ids"] == child_ids
