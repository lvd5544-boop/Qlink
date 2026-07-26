"""Stable API error envelope with a temporary FastAPI-detail compatibility field."""

from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


_STATUS_CODES = {
    400: "request.invalid",
    401: "auth.unauthorized",
    403: "auth.forbidden",
    404: "resource.not_found",
    409: "request.conflict",
    413: "request.too_large",
    422: "request.validation_failed",
    429: "request.rate_limited",
    500: "server.internal_error",
    502: "provider.unavailable",
    503: "service.unavailable",
}


def request_id(request: Request) -> str:
    existing = getattr(request.state, "request_id", None)
    if existing:
        return str(existing)
    supplied = (request.headers.get("X-Request-ID") or "").strip()
    value = supplied[:128] if supplied else str(uuid.uuid4())
    request.state.request_id = value
    return value


def _normalized_detail(
    *,
    status_code: int,
    detail,
    request_id_value: str,
) -> dict:
    fields = {}
    if isinstance(detail, dict):
        raw_code = detail.get("error") or detail.get("code")
        message = detail.get("message")
        fields = {
            key: value
            for key, value in detail.items()
            if key not in {"error", "code", "message", "request_id"}
        }
    else:
        raw_code = None
        message = str(detail) if detail else None
    code = str(raw_code or _STATUS_CODES.get(status_code, "http.error"))
    if "." not in code:
        domain = (
            "billing"
            if code
            in {
                "quota_exceeded",
                "subscription_inactive",
                "billing_account_missing",
                "billing_account_ambiguous",
                "feature_not_in_plan",
                "seat_limit_exceeded",
                "billing_entitlement_required",
            }
            else "request"
        )
        code = f"{domain}.{code}"
    return {
        "code": code,
        "message": message or code,
        "fields": fields,
        "request_id": request_id_value,
    }


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    rid = request_id(request)
    return JSONResponse(
        status_code=exc.status_code,
        headers={
            **(exc.headers or {}),
            "X-Request-ID": rid,
        },
        content={
            "error": _normalized_detail(
                status_code=exc.status_code,
                detail=exc.detail,
                request_id_value=rid,
            ),
            # Transitional compatibility. Frontend code must use `error`.
            "detail": exc.detail,
        },
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    rid = request_id(request)
    fields = {
        ".".join(str(part) for part in error.get("loc", ())): error.get("msg")
        for error in exc.errors()
    }
    return JSONResponse(
        status_code=422,
        headers={"X-Request-ID": rid},
        content={
            "error": {
                "code": "request.validation_failed",
                "message": "请求字段校验失败",
                "fields": fields,
                "request_id": rid,
            },
            "detail": exc.errors(),
        },
    )


async def attach_request_context(
    request: Request,
    call_next,
):
    rid = request_id(request)
    response = await call_next(request)
    response.headers["X-Request-ID"] = rid
    response.headers["X-Server-Time"] = datetime.now(timezone.utc).isoformat()
    return response
