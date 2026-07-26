from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.application_state import (
    APPLICATION_TRANSITIONS,
    BUSINESS_ACTION_ONLY_STATUSES,
    StatusTransitionError,
    allowed_application_actions,
    capture_resume_snapshot,
    change_application_resume,
    get_resume_snapshot,
    set_application_status,
    validate_transition,
)


def _application(status: str = "submitted", resume_id: str = "resume-v1"):
    return SimpleNamespace(
        id="application-1",
        status=status,
        resume_id=resume_id,
        pipeline_meta={},
    )


def _resume(resume_id: str, parsed_json: dict):
    return SimpleNamespace(id=resume_id, parsed_json=parsed_json)


@pytest.mark.parametrize(
    ("current", "target", "action", "actor_role"),
    [
        ("submitted", "viewed", "employer_view", "employer"),
        ("submitted", "needs_clarification", "create_claim_request", "employer"),
        ("viewed", "needs_clarification", "create_claim_request", "employer"),
        (
            "needs_clarification",
            "needs_clarification",
            "create_claim_request",
            "employer",
        ),
        ("needs_clarification", "needs_clarification", "candidate_answers_some", "candidate"),
        ("needs_clarification", "clarified", "candidate_answers_all", "candidate"),
        (
            "needs_clarification",
            "clarification_closed",
            "employer_closes_clarification",
            "employer",
        ),
        ("clarified", "interview_invited", "create_invitation", "employer"),
        ("clarification_closed", "interview_invited", "create_invitation", "employer"),
        ("interview_invited", "rejected", "employer_rejects", "employer"),
        ("viewed", "accepted", "employer_accepts", "employer"),
    ],
)
def test_application_transition_table_allows_required_edges(current, target, action, actor_role):
    assert APPLICATION_TRANSITIONS
    validate_transition(current, target, action, actor_role)


@pytest.mark.parametrize("terminal", ["accepted", "rejected"])
@pytest.mark.parametrize("target", ["submitted", "viewed", "accepted", "rejected"])
def test_terminal_statuses_have_no_write_edges(terminal, target):
    with pytest.raises(StatusTransitionError) as exc:
        validate_transition(terminal, target, "employer_view", "employer")
    assert exc.value.code == 409


@pytest.mark.parametrize(
    "derived",
    [
        "needs_clarification",
        "clarified",
        "clarification_closed",
        "interview_invited",
    ],
)
def test_generic_patch_cannot_set_business_action_status(derived):
    assert derived in BUSINESS_ACTION_ONLY_STATUSES
    with pytest.raises(StatusTransitionError):
        validate_transition("viewed", derived, "status_patch", "employer")


def test_idempotent_transition_does_not_append_history():
    application = _application(status="viewed")
    set_application_status(
        application,
        "viewed",
        action="employer_view",
        actor_id="employer-1",
        actor_role="employer",
        request_key="request-1",
    )
    assert application.pipeline_meta.get("status_history", []) == []


def test_allowed_actions_are_derived_from_transition_graph_and_claim_state():
    application = _application(status="clarified")
    assert allowed_application_actions(
        application,
        actor_role="employer",
        open_claim_count=0,
        answered_unreviewed_count=1,
    ) == [
        "accept",
        "invite_interview",
        "mark_reviewed",
        "reject",
        "request_clarification",
        "send_message",
    ]
    blocked_invite = allowed_application_actions(
        application,
        actor_role="employer",
        open_claim_count=1,
    )
    assert "invite_interview" not in blocked_invite


def test_candidate_reply_capability_requires_open_claim():
    application = _application(status="needs_clarification")
    assert "reply_clarification" in allowed_application_actions(
        application,
        actor_role="candidate",
        open_claim_count=1,
    )
    assert "reply_clarification" not in allowed_application_actions(
        application,
        actor_role="candidate",
        open_claim_count=0,
    )


def test_status_history_contains_required_audit_fields():
    application = _application()
    set_application_status(
        application,
        "viewed",
        action="employer_view",
        actor_id="employer-1",
        actor_role="employer",
        reason="opened application",
        request_key="request-1",
    )
    history = application.pipeline_meta["status_history"]
    assert len(history) == 1
    assert {
        "from",
        "to",
        "action",
        "source",
        "actor_id",
        "actor_role",
        "reason",
        "timestamp",
        "request_key",
    } <= set(history[0])


def test_capture_resume_snapshot_is_deep_copy_and_creates_first_version():
    parsed = {"work_experience": [{"description": "original"}]}
    application = _application()
    capture_resume_snapshot(
        application,
        _resume("resume-v1", parsed),
        actor_id="candidate-1",
    )

    parsed["work_experience"][0]["description"] = "mutated"
    initial = application.pipeline_meta["initial_submission_snapshot"]
    version = application.pipeline_meta["resume_versions"][0]
    assert initial["parsed_json"]["work_experience"][0]["description"] == "original"
    assert version["snapshot_json"]["work_experience"][0]["description"] == "original"
    assert initial["content_hash"] == version["content_hash"]
    assert application.pipeline_meta["current_resume_version_id"] == version["version_id"]


def test_explicit_resume_change_appends_version_without_overwriting_initial():
    initial_json = {"summary": "initial"}
    application = _application()
    capture_resume_snapshot(
        application,
        _resume("resume-v1", initial_json),
        actor_id="candidate-1",
    )
    initial_before = deepcopy(application.pipeline_meta["initial_submission_snapshot"])

    change_application_resume(
        application,
        new_resume=_resume("resume-v2", {"summary": "replacement"}),
        actor_id="candidate-1",
        reason="candidate confirmed",
    )

    assert application.pipeline_meta["initial_submission_snapshot"] == initial_before
    assert [v["resume_id"] for v in application.pipeline_meta["resume_versions"]] == [
        "resume-v1",
        "resume-v2",
    ]
    current = get_resume_snapshot(application)
    assert current["resume_id"] == "resume-v2"
    assert current["parsed_json"]["summary"] == "replacement"
    assert application.resume_id == "resume-v2"
    change = application.pipeline_meta["resume_change_history"][-1]
    assert change["from_hash"] == initial_before["content_hash"]
    assert change["to_hash"] == current["content_hash"]


def test_legacy_resume_snapshot_is_read_without_claiming_reliable_initial_history():
    application = _application()
    application.pipeline_meta = {
        "resume_snapshot": {
            "resume_id": "resume-v1",
            "parsed_json": {"summary": "legacy"},
            "captured_at": "2026-01-01T00:00:00+00:00",
        }
    }

    snapshot = get_resume_snapshot(application)
    assert snapshot["resume_id"] == "resume-v1"
    assert snapshot["snapshot_status"] == "legacy_unverified"
    assert snapshot["migration_uncertain"] is True
