"""
申请状态迁移领域服务（PR3）。

集中管理 JobApplication.status 变更与 resume_id 不可变规则，
避免在各路由散落 `app.status = ...` / 静默覆盖 `resume_id`。

规则要点：
- 以下状态只能由专用业务动作产生，通用 PATCH 不得直接设置：
  needs_clarification、clarified、clarification_closed、interview_invited。
- 通用 PATCH 招聘方仅可设置 viewed / rejected / accepted；候选人不可直接改状态。
- 已投递申请的 resume_id 不可静默变更；更换必须走显式接口并留痕。
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from typing import Any, Optional

from .application_status import APPLICATION_STATUSES


# 只能由专用业务动作产生的状态
BUSINESS_ACTION_ONLY_STATUSES = frozenset(
    {
        "needs_clarification",
        "clarified",
        "clarification_closed",
        "interview_invited",
    }
)

# 终态：不因澄清重算被改回
TERMINAL_STATUSES = frozenset({"accepted", "rejected"})

# 单一迁移图：路由不得复制当前态 → 动作 → 目标态规则。
APPLICATION_TRANSITIONS = {
    "submitted": {
        "employer_view": "viewed",
        "create_claim_request": "needs_clarification",
        "create_invitation": "interview_invited",
        "employer_rejects": "rejected",
        "employer_accepts": "accepted",
    },
    "viewed": {
        "employer_view": "viewed",
        "create_claim_request": "needs_clarification",
        "create_invitation": "interview_invited",
        "employer_rejects": "rejected",
        "employer_accepts": "accepted",
    },
    "needs_clarification": {
        "create_claim_request": "needs_clarification",
        "candidate_answers_some": "needs_clarification",
        "candidate_answers_all": "clarified",
        "employer_closes_clarification": "clarification_closed",
        "employer_rejects": "rejected",
        "employer_accepts": "accepted",
    },
    "clarified": {
        "create_claim_request": "needs_clarification",
        "create_invitation": "interview_invited",
        "employer_rejects": "rejected",
        "employer_accepts": "accepted",
    },
    "clarification_closed": {
        "create_claim_request": "needs_clarification",
        "create_invitation": "interview_invited",
        "employer_rejects": "rejected",
        "employer_accepts": "accepted",
    },
    "interview_invited": {
        "employer_view": "interview_invited",
        "employer_rejects": "rejected",
        "employer_accepts": "accepted",
    },
}

ACTION_ROLES = {
    "employer_view": frozenset({"employer"}),
    "create_claim_request": frozenset({"employer"}),
    "create_invitation": frozenset({"employer"}),
    "employer_rejects": frozenset({"employer"}),
    "employer_accepts": frozenset({"employer"}),
    "candidate_answers_some": frozenset({"candidate"}),
    "candidate_answers_all": frozenset({"candidate"}),
    "employer_closes_clarification": frozenset({"employer"}),
}

_PUBLIC_ACTION_NAMES = {
    "employer_view": "mark_viewed",
    "create_claim_request": "request_clarification",
    "create_invitation": "invite_interview",
    "employer_rejects": "reject",
    "employer_accepts": "accept",
    "candidate_answers_some": "reply_clarification",
    "candidate_answers_all": "reply_clarification",
    "employer_closes_clarification": "close_clarification",
}


def allowed_application_actions(
    application,
    *,
    actor_role: str,
    open_claim_count: int = 0,
    answered_unreviewed_count: int = 0,
) -> list[str]:
    """Return UI capabilities from the authoritative transition graph."""
    status = getattr(application, "status", None)
    if status in TERMINAL_STATUSES or status not in APPLICATION_TRANSITIONS:
        return []
    transition_actions = APPLICATION_TRANSITIONS.get(status, {})
    allowed = {
        _PUBLIC_ACTION_NAMES[action]
        for action in transition_actions
        if actor_role in ACTION_ROLES.get(action, frozenset()) and action in _PUBLIC_ACTION_NAMES
    }
    if actor_role == "employer":
        allowed.add("send_message")
        if open_claim_count:
            allowed.discard("invite_interview")
        else:
            allowed.discard("close_clarification")
        if answered_unreviewed_count:
            allowed.add("mark_reviewed")
    elif actor_role == "candidate":
        allowed.add("send_message")
        if not open_claim_count:
            allowed.discard("reply_clarification")
    return sorted(allowed)


class StatusTransitionError(Exception):
    """状态迁移不被允许。code 用于映射 HTTP 状态码。"""

    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.code = code


class ResumeImmutableError(Exception):
    """已投递申请的 resume_id 不可静默变更。code 用于映射 HTTP 状态码。"""

    def __init__(self, message: str, code: int = 409):
        super().__init__(message)
        self.code = code


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_meta(application) -> dict:
    meta = getattr(application, "pipeline_meta", None) or {}
    return dict(meta) if isinstance(meta, dict) else {}


def _set_meta(application, meta: dict) -> None:
    application.pipeline_meta = meta


def validate_transition(
    current: str,
    target: str,
    action: str,
    actor_role: Optional[str],
) -> None:
    """验证唯一迁移图、业务动作及角色；不修改对象。"""
    if current not in APPLICATION_STATUSES or target not in APPLICATION_STATUSES:
        raise StatusTransitionError("无效的申请状态", 400)
    if current in TERMINAL_STATUSES:
        raise StatusTransitionError("申请已处于终态，不能执行写操作", 409)

    if action == "status_patch":
        if actor_role != "employer":
            raise StatusTransitionError("当前角色不能设置申请状态", 403)
        if target in BUSINESS_ACTION_ONLY_STATUSES:
            raise StatusTransitionError("该状态只能通过对应业务动作产生", 403)
        action = {
            "viewed": "employer_view",
            "rejected": "employer_rejects",
            "accepted": "employer_accepts",
        }.get(target, "")

    expected = APPLICATION_TRANSITIONS.get(current, {}).get(action)
    if not expected or expected != target:
        raise StatusTransitionError(
            f"不允许从 {current} 通过 {action or 'unknown'} 迁移到 {target}",
            409,
        )
    if actor_role not in ACTION_ROLES.get(action, frozenset()):
        raise StatusTransitionError("当前角色不能执行该状态动作", 403)


def set_application_status(
    application,
    new_status: str,
    *,
    action: str,
    actor_role: str,
    actor_id: Optional[str] = None,
    reason: Optional[str] = None,
    source: Optional[str] = None,
    request_key: Optional[str] = None,
) -> str:
    """
    受控设置申请状态。授权仍由调用方完成，动作/角色/迁移由本服务强制。
    """
    prev = getattr(application, "status", None)
    validate_transition(prev, new_status, action, actor_role)
    if prev == new_status:
        return new_status

    application.status = new_status
    meta = _get_meta(application)
    history = list(meta.get("status_history") or [])
    history.append(
        {
            "from": prev,
            "to": new_status,
            "action": action,
            "source": source or action,
            "actor_id": actor_id,
            "actor_role": actor_role,
            "reason": reason,
            "timestamp": _now(),
            "request_key": request_key,
        }
    )
    meta["status_history"] = history[-100:]
    _set_meta(application, meta)
    return new_status


def patch_status_by_role(
    application, new_status: str, role: str, *, actor_id: Optional[str] = None
) -> str:
    """
    通用 PATCH /status 使用：按角色限制，拒绝业务动作专属状态。
    """
    new_status = (new_status or "").strip()
    validate_transition(getattr(application, "status", None), new_status, "status_patch", role)
    action = {
        "viewed": "employer_view",
        "rejected": "employer_rejects",
        "accepted": "employer_accepts",
    }[new_status]
    return set_application_status(
        application,
        new_status,
        action=action,
        actor_role=role,
        actor_id=actor_id,
        source="status_patch",
    )


# ---------------------------------------------------------------------------
# resume_id 不可变 / 投递快照
# ---------------------------------------------------------------------------
def _content_hash(parsed_json: Any) -> str:
    payload = json.dumps(
        deepcopy(parsed_json) if parsed_json is not None else {},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def capture_resume_snapshot(
    application,
    resume,
    *,
    actor_id: Optional[str] = None,
    source: str = "candidate_applied",
) -> None:
    """
    在申请创建时记录投递时的简历快照，供历史审计使用，
    不受后续简历修改污染。
    """
    if resume is None:
        return
    meta = _get_meta(application)
    if meta.get("initial_submission_snapshot"):
        return
    parsed_json = deepcopy(resume.parsed_json or {})
    captured_at = _now()
    content_hash = _content_hash(parsed_json)
    initial = {
        "resume_id": str(resume.id),
        "parsed_json": parsed_json,
        "captured_at": captured_at,
        "content_hash": content_hash,
        "source": source,
        "actor_id": actor_id,
        "schema_version": 1,
        "snapshot_status": "reliable",
    }
    version = {
        "version_id": "v1",
        "resume_id": str(resume.id),
        "snapshot_json": deepcopy(parsed_json),
        "content_hash": content_hash,
        "source": source,
        "actor_id": actor_id,
        "created_at": captured_at,
        "snapshot_status": "reliable",
    }
    meta["initial_submission_snapshot"] = initial
    meta["resume_versions"] = [version]
    meta["current_resume_version_id"] = "v1"
    meta.setdefault("application_source", source)
    # 旧字段只保留一次兼容镜像，后续换简历不再覆盖。
    if "resume_snapshot" not in meta:
        meta["resume_snapshot"] = deepcopy(initial)
    _set_meta(application, meta)


def get_resume_snapshot(application) -> Optional[dict]:
    meta = _get_meta(application)
    versions = meta.get("resume_versions")
    current_id = meta.get("current_resume_version_id")
    if isinstance(versions, list) and current_id:
        version = next(
            (v for v in versions if isinstance(v, dict) and v.get("version_id") == current_id),
            None,
        )
        if version:
            return {
                "version_id": version.get("version_id"),
                "resume_id": version.get("resume_id"),
                "parsed_json": deepcopy(version.get("snapshot_json") or {}),
                "captured_at": version.get("created_at"),
                "content_hash": version.get("content_hash"),
                "source": version.get("source"),
                "snapshot_status": version.get("snapshot_status", "reliable"),
                "migration_uncertain": bool(version.get("migration_uncertain")),
            }

    snap = meta.get("resume_snapshot")
    if isinstance(snap, dict):
        return {
            **deepcopy(snap),
            "content_hash": snap.get("content_hash")
            or _content_hash(snap.get("parsed_json") or {}),
            "snapshot_status": "legacy_unverified",
            "migration_uncertain": True,
        }
    return None


def ensure_resume_unchanged(application, resume_id: str) -> None:
    """
    要求指定 resume_id 与申请现有 resume_id 一致，否则冲突。
    用于招聘方从人才池发起澄清/邀请时禁止替换申请简历。
    """
    if resume_id is None:
        return
    if str(application.resume_id) != str(resume_id):
        raise ResumeImmutableError(
            "该岗位已有申请，必须使用申请投递时的简历；如需更换请走显式换简历流程。",
            409,
        )


def change_application_resume(
    application,
    *,
    new_resume,
    actor_id: str,
    reason: Optional[str] = None,
) -> dict:
    """
    候选人显式更换申请简历：保留原简历快照与更换记录，不静默覆盖历史。
    返回本次更换记录。
    """
    old_resume_id = str(application.resume_id)
    new_resume_id = str(new_resume.id)

    meta = _get_meta(application)
    if not meta.get("initial_submission_snapshot"):
        legacy = meta.get("resume_snapshot")
        if isinstance(legacy, dict):
            legacy_json = deepcopy(legacy.get("parsed_json") or {})
            legacy_hash = legacy.get("content_hash") or _content_hash(legacy_json)
            legacy_at = legacy.get("captured_at") or _now()
            meta["initial_submission_snapshot"] = {
                "resume_id": legacy.get("resume_id") or old_resume_id,
                "parsed_json": deepcopy(legacy_json),
                "captured_at": legacy_at,
                "content_hash": legacy_hash,
                "source": "legacy_resume_snapshot",
                "actor_id": None,
                "schema_version": 1,
                "snapshot_status": "legacy_unverified",
                "migration_uncertain": True,
            }
            meta["resume_versions"] = [
                {
                    "version_id": "v1",
                    "resume_id": legacy.get("resume_id") or old_resume_id,
                    "snapshot_json": deepcopy(legacy_json),
                    "content_hash": legacy_hash,
                    "source": "legacy_resume_snapshot",
                    "actor_id": None,
                    "created_at": legacy_at,
                    "snapshot_status": "legacy_unverified",
                    "migration_uncertain": True,
                }
            ]
            meta["current_resume_version_id"] = "v1"
        else:
            meta["snapshot_status"] = "legacy_missing"
            meta["migration_uncertain"] = True

    versions = list(meta.get("resume_versions") or [])
    current_id = meta.get("current_resume_version_id")
    current = next(
        (v for v in versions if isinstance(v, dict) and v.get("version_id") == current_id),
        None,
    )
    new_json = deepcopy(new_resume.parsed_json or {})
    new_hash = _content_hash(new_json)
    created_at = _now()
    version_id = f"v{len(versions) + 1}"
    versions.append(
        {
            "version_id": version_id,
            "resume_id": new_resume_id,
            "snapshot_json": new_json,
            "content_hash": new_hash,
            "source": "candidate_replaced",
            "actor_id": actor_id,
            "reason": reason,
            "created_at": created_at,
            "snapshot_status": "reliable",
        }
    )
    meta["resume_versions"] = versions
    meta["current_resume_version_id"] = version_id
    history = list(meta.get("resume_change_history") or [])
    record = {
        "from_resume_id": old_resume_id,
        "to_resume_id": new_resume_id,
        "from_version_id": current_id,
        "to_version_id": version_id,
        "from_hash": current.get("content_hash") if current else None,
        "to_hash": new_hash,
        "actor_id": actor_id,
        "reason": reason,
        "at": created_at,
    }
    history.append(record)
    meta["resume_change_history"] = history[-100:]
    _set_meta(application, meta)

    application.resume_id = new_resume_id
    return record
