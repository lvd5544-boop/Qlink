"""Runtime smoke acceptance against the local HTTP stack; never prints tokens."""

from __future__ import annotations

import json
import os
from urllib.error import HTTPError
from urllib.request import Request, urlopen

BASE = os.getenv("ACCEPTANCE_BASE_URL", "http://127.0.0.1:8081/api").rstrip("/")


def request(
    path: str,
    *,
    method: str = "GET",
    body=None,
    token: str | None = None,
    extra_headers: dict | None = None,
):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if extra_headers:
        headers.update(extra_headers)
    raw = json.dumps(body).encode() if body is not None else None
    try:
        with urlopen(
            Request(f"{BASE}{path}", data=raw, headers=headers, method=method), timeout=10
        ) as response:
            payload = json.loads(response.read().decode() or "{}")
            return response.status, payload
    except HTTPError as exc:
        payload = json.loads(exc.read().decode() or "{}")
        return exc.code, payload


def login(email: str, password: str) -> str:
    status, payload = request(
        "/auth/login", method="POST", body={"email": email, "password": password}
    )
    if status != 200 or not payload.get("access_token"):
        raise RuntimeError(f"login failed for {email}: status={status}")
    return payload["access_token"]


def main() -> None:
    admin_email = os.getenv("ACCEPTANCE_ADMIN_EMAIL", "admin.pr10@example.com")
    admin_password = os.environ["ACCEPTANCE_ADMIN_PASSWORD"]
    candidate_email = os.getenv("ACCEPTANCE_CANDIDATE_EMAIL", "candidate.pr11@example.com")
    candidate_password = os.getenv("ACCEPTANCE_CANDIDATE_PASSWORD", "CandidateTest9x!")

    status, ready = request("/ready")
    assert status == 200
    assert ready["checks"]["model"]["mode"] == "rules_only"
    print("PASS readiness rules_only + public banner contract")

    register_status, _ = request(
        "/auth/register",
        method="POST",
        body={"email": candidate_email, "password": candidate_password, "role": "candidate"},
    )
    assert register_status in {200, 409}
    admin_token = login(admin_email, admin_password)
    candidate_token = login(candidate_email, candidate_password)

    status, sources = request("/admin/data-sources", token=admin_token)
    assert status == 200
    forum = next(item for item in sources["sources"] if item["id"] == "ds_forum_statistical")
    assert forum["layer"] == "E" and forum["status"] == "restricted"
    assert "contract_ref" not in json.dumps(sources)
    print("PASS admin source registry: forum E/restricted, no contract_ref")

    status, _ = request("/admin/data-sources", token=candidate_token)
    assert status == 403
    print("PASS candidate denied from admin source registry")

    experience_body = {
        "experience_type": "project",
        "organization": "QLink acceptance",
        "title": "PR11 runtime smoke",
        "date_precision": "unknown",
        "description": "Runtime acceptance record",
        "source_kind": "manual",
        "workflow_state": "active",
    }
    status, created = request(
        "/career-passport/experiences",
        method="POST",
        token=candidate_token,
        body=experience_body,
        extra_headers={"Idempotency-Key": "pr11-runtime-experience-1"},
    )
    assert status == 200 and created["experience"]["id"]
    experience_id = created["experience"]["id"]
    status, replay = request(
        "/career-passport/experiences",
        method="POST",
        token=candidate_token,
        body=experience_body,
        extra_headers={"Idempotency-Key": "pr11-runtime-experience-1"},
    )
    assert status == 200 and replay["experience"]["id"] == experience_id
    print("PASS PR11 experience idempotent replay")

    status, map_payload = request(
        "/career-passport/map?view=timeline&limit=100", token=candidate_token
    )
    assert status == 200
    assert map_payload["privacy_boundary"] == "owner_authorized_server_projection"
    assert any(node["label"] == "PR11 runtime smoke" for node in map_payload["nodes"])
    print("PASS PR11 candidate experience + server-authorized map")

    status, overview = request("/career-passport/overview", token=candidate_token)
    assert status == 200
    assert "counts" in overview
    print("PASS PR11 career passport overview")

    init_body = {
        "artifact_type": "user_statement",
        "title": "PR11 idempotent evidence",
        "allowed_uses": ["resume_assistance"],
        "default_visibility": "private",
    }
    status, keyed = request(
        "/evidence-vault/artifacts/init-upload",
        method="POST",
        token=candidate_token,
        body=init_body,
        extra_headers={"Idempotency-Key": "pr11-runtime-init-1"},
    )
    assert status == 200 and keyed["artifact"]["upload_complete"] is True
    keyed_id = keyed["artifact"]["id"]
    status, keyed_replay = request(
        "/evidence-vault/artifacts/init-upload",
        method="POST",
        token=candidate_token,
        body=init_body,
        extra_headers={"Idempotency-Key": "pr11-runtime-init-1"},
    )
    assert status == 200 and keyed_replay["artifact"]["id"] == keyed_id
    print("PASS PR11 Evidence idempotent init replay")

    status, _ = request(
        f"/evidence-vault/artifacts/{keyed_id}",
        method="DELETE",
        token=candidate_token,
        extra_headers={"Idempotency-Key": "pr11-runtime-withdraw-1"},
    )
    assert status == 200
    print("PASS PR11 Evidence init + withdrawal")


if __name__ == "__main__":
    main()
