"""WebSocket first-message authentication and resource authorization."""

from __future__ import annotations

import asyncio
import json
import os
from typing import Optional

from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import get_user_from_token
from .models_db import JobApplication, Resume, User


def query_token_compatibility_enabled() -> bool:
    environment = os.getenv("ENV", "development").strip().lower()
    if environment == "production":
        return False
    return os.getenv("WS_ALLOW_QUERY_TOKEN", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


async def _close_unauthorized(websocket: WebSocket, reason: str) -> None:
    await websocket.close(code=1008, reason=reason)


async def authenticate_websocket(
    websocket: WebSocket,
    db: AsyncSession,
    *,
    user_id: str,
    resume_id: Optional[str],
    application_id: Optional[str],
) -> Optional[User]:
    """Authenticate before any interview payload and validate bound resources."""
    token = ""
    requested_uses = {}
    if query_token_compatibility_enabled():
        token = websocket.query_params.get("token") or ""

    if not token:
        try:
            raw = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=max(
                    1.0,
                    float(os.getenv("WS_AUTH_TIMEOUT_SECONDS", "10")),
                ),
            )
            payload = json.loads(raw)
        except Exception:
            await _close_unauthorized(websocket, "鉴权超时或消息无效")
            return None
        if not isinstance(payload, dict) or payload.get("type") != "auth":
            await _close_unauthorized(websocket, "首条消息必须为鉴权消息")
            return None
        token = str(payload.get("token") or "")
        raw_uses = payload.get("requested_uses")
        if isinstance(raw_uses, dict):
            requested_uses = {
                key: raw_uses.get(key) is True
                for key in (
                    "resume_write",
                    "job_recommendation",
                    "employer_share",
                    "model_improvement",
                )
            }

    user = await get_user_from_token(token, db)
    if user is None or str(user.id) != str(user_id) or user.role != "candidate":
        await _close_unauthorized(websocket, "未授权")
        return None

    resume = None
    if resume_id:
        resume = await db.get(Resume, str(resume_id))
        if not resume or str(resume.user_id) != str(user.id):
            await _close_unauthorized(websocket, "简历不存在或无权访问")
            return None

    if application_id:
        application = await db.get(JobApplication, str(application_id))
        if not application or str(application.candidate_id) != str(user.id):
            await _close_unauthorized(websocket, "申请不存在或无权访问")
            return None

    if requested_uses.get("employer_share") and not application_id:
        requested_uses["employer_share"] = False
    if hasattr(websocket, "state"):
        websocket.state.interview_requested_uses = requested_uses
        if resume_id and str(application.resume_id) != str(resume_id):
            await _close_unauthorized(websocket, "简历与申请不一致")
            return None

    await websocket.send_text(json.dumps({"type": "auth_ok"}, ensure_ascii=False))
    return user
