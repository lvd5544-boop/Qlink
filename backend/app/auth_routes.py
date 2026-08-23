from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import html
import logging
import os
import re
import secrets
import uuid
from urllib.parse import quote, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession
from .database import get_db
from .email_service import send_email, smtp_configured
from .models_db import LegalAcceptance, PasswordResetToken, User
from .auth import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    AUTH_COOKIE_NAME,
    CSRF_COOKIE_NAME,
    create_access_token,
    get_current_user,
    get_password_hash,
    oauth2_scheme,
    revoke_access_token,
    verify_password,
    _get_auth_redis,
    _shared_auth_state_enabled,
)
from .privacy import delete_user_graph
from .billing_provisioning import provision_new_user_billing
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy import update

router = APIRouter(prefix="/auth", tags=["认证"])
logger = logging.getLogger(__name__)
TERMS_VERSION = "pilot-terms-v1"
PRIVACY_NOTICE_VERSION = "pilot-privacy-v1"


def _cookie_secure() -> bool:
    configured = os.getenv("AUTH_COOKIE_SECURE", "").strip().lower()
    if configured:
        return configured in {"1", "true", "yes", "on"}
    return os.getenv("ENV", "development").strip().lower() == "production"


def _cookie_samesite() -> str:
    value = os.getenv("AUTH_COOKIE_SAMESITE", "lax").strip().lower()
    return value if value in {"lax", "strict", "none"} else "lax"


def _set_auth_cookies(response: Response, token: str) -> None:
    max_age = max(60, ACCESS_TOKEN_EXPIRE_MINUTES * 60)
    secure = _cookie_secure()
    same_site = _cookie_samesite()
    response.set_cookie(
        AUTH_COOKIE_NAME,
        token,
        max_age=max_age,
        path="/",
        secure=secure,
        httponly=True,
        samesite=same_site,
    )
    response.set_cookie(
        CSRF_COOKIE_NAME,
        secrets.token_urlsafe(24),
        max_age=max_age,
        path="/",
        secure=secure,
        httponly=False,
        samesite=same_site,
    )


def _clear_auth_cookies(response: Response) -> None:
    secure = _cookie_secure()
    same_site = _cookie_samesite()
    response.delete_cookie(
        AUTH_COOKIE_NAME,
        path="/",
        secure=secure,
        httponly=True,
        samesite=same_site,
    )
    response.delete_cookie(
        CSRF_COOKIE_NAME,
        path="/",
        secure=secure,
        httponly=False,
        samesite=same_site,
    )


class RegisterRequest(BaseModel):
    email: str
    password: str
    role: str = "candidate"
    terms_accepted: bool = False
    privacy_notice_acknowledged: bool = False


class EmployerRegisterRequest(BaseModel):
    email: str
    password: str
    invite_code: str = Field(..., min_length=1)
    terms_accepted: bool = False
    privacy_notice_acknowledged: bool = False


class LoginRequest(BaseModel):
    email: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=1, max_length=72)


class PasswordResetRequest(BaseModel):
    email: str


class PasswordResetConfirmRequest(BaseModel):
    token: str = Field(min_length=32, max_length=256)
    new_password: str = Field(min_length=1, max_length=72)


_login_attempts: dict[str, deque[datetime]] = defaultdict(deque)
_password_reset_attempts: dict[str, deque[datetime]] = defaultdict(deque)
_dummy_password_hash = get_password_hash("Dummy-Password-123")
_COMMON_PASSWORD_MARKERS = (
    "password",
    "qwerty",
    "admin",
    "letmein",
    "welcome",
    "123456",
)


def _login_rate_key(client_ip: str, email: str) -> str:
    digest = hashlib.sha256(f"{client_ip}:{email}".encode("utf-8")).hexdigest()
    return f"auth:login-fail:{digest}"


def _password_reset_rate_key(client_ip: str, email: str) -> str:
    digest = hashlib.sha256(f"{client_ip}:{email}".encode("utf-8")).hexdigest()
    return f"auth:password-reset:{digest}"


async def _shared_failure_count(key: str) -> int:
    try:
        value = await _get_auth_redis().get(key)
        return int(value or 0)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="登录安全服务暂不可用，请稍后重试",
        ) from exc


async def _record_shared_failure(key: str, window_seconds: int) -> None:
    try:
        redis = _get_auth_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_seconds)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="登录安全服务暂不可用，请稍后重试",
        ) from exc


async def _clear_shared_failures(key: str) -> None:
    try:
        await _get_auth_redis().delete(key)
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="登录安全服务暂不可用，请稍后重试",
        ) from exc


def _normalize_email(email: str) -> str:
    value = (email or "").strip().lower()
    if len(value) > 255 or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
        raise HTTPException(status_code=422, detail="邮箱格式无效")
    return value


def _validate_password(password: str) -> None:
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        raise HTTPException(status_code=422, detail="密码过长，请使用 72 字节以内的密码")
    if (
        len(password) < 10
        or not re.search(r"[A-Z]", password)
        or not re.search(r"[a-z]", password)
        or not re.search(r"\d", password)
    ):
        raise HTTPException(
            status_code=422,
            detail="密码至少 10 位，且必须包含大写字母、小写字母和数字",
        )
    normalized = re.sub(r"[^a-z0-9]", "", password.lower())
    if any(marker in normalized for marker in _COMMON_PASSWORD_MARKERS):
        raise HTTPException(
            status_code=422,
            detail="密码过于常见，请避免 Password、Qwerty、Admin 或连续数字等弱密码",
        )


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _reset_origin() -> str | None:
    value = os.getenv("PUBLIC_ORIGIN", "").strip().rstrip("/")
    parsed = urlparse(value)
    environment = os.getenv("ENV", "development").strip().lower()
    if not parsed.hostname or parsed.path not in {"", "/"}:
        return None
    if environment == "production" and parsed.scheme != "https":
        return None
    if parsed.scheme not in {"http", "https"}:
        return None
    return value


async def _password_reset_allowed(client_ip: str, email: str) -> bool:
    window_seconds = max(60, int(os.getenv("PASSWORD_RESET_WINDOW_SECONDS", "3600")))
    limit = max(1, int(os.getenv("PASSWORD_RESET_LIMIT", "3")))
    key = _password_reset_rate_key(client_ip, email)
    if _shared_auth_state_enabled():
        try:
            redis = _get_auth_redis()
            count = await redis.incr(key)
            if count == 1:
                await redis.expire(key, window_seconds)
            return int(count) <= limit
        except Exception as exc:
            raise HTTPException(
                status_code=503,
                detail="账号恢复安全服务暂不可用，请稍后重试",
            ) from exc

    now = datetime.now(timezone.utc)
    attempts = _password_reset_attempts[key]
    window = timedelta(seconds=window_seconds)
    while attempts and attempts[0] <= now - window:
        attempts.popleft()
    if len(attempts) >= limit:
        return False
    attempts.append(now)
    return True


def _legal_notice_snapshot() -> dict[str, str]:
    return {
        "terms_version": TERMS_VERSION,
        "privacy_notice_version": PRIVACY_NOTICE_VERSION,
        "operator": os.getenv("LEGAL_ENTITY_NAME", "QLink pilot operator").strip(),
        "support_email": os.getenv("SUPPORT_EMAIL", "support@example.invalid").strip(),
        "privacy_email": os.getenv("PRIVACY_CONTACT_EMAIL", "privacy@example.invalid").strip(),
    }


def _require_legal_acceptance(*, terms_accepted: bool, privacy_acknowledged: bool) -> None:
    if not terms_accepted or not privacy_acknowledged:
        raise HTTPException(
            status_code=422,
            detail="创建账号前必须阅读并同意服务条款，同时确认已阅读隐私说明",
        )


async def _create_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    role: str,
    terms_accepted: bool,
    privacy_acknowledged: bool,
) -> User:
    normalized = _normalize_email(email)
    _validate_password(password)
    _require_legal_acceptance(
        terms_accepted=terms_accepted,
        privacy_acknowledged=privacy_acknowledged,
    )
    result = await db.execute(select(User).where(User.email == normalized))
    if result.scalars().first():
        raise HTTPException(status_code=409, detail="邮箱已注册")
    user = User(
        email=normalized,
        password_hash=get_password_hash(password),
        role=role,
    )
    db.add(user)
    await db.flush()
    db.add(
        LegalAcceptance(
            user_id=str(user.id),
            terms_version=TERMS_VERSION,
            privacy_notice_version=PRIVACY_NOTICE_VERSION,
            notice_snapshot=_legal_notice_snapshot(),
        )
    )
    await provision_new_user_billing(db, user=user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if req.role != "candidate":
        raise HTTPException(status_code=403, detail="公开注册仅支持求职者账号")
    user = await _create_user(
        db,
        email=req.email,
        password=req.password,
        role="candidate",
        terms_accepted=req.terms_accepted,
        privacy_acknowledged=req.privacy_notice_acknowledged,
    )
    return {"msg": "注册成功", "user_id": str(user.id)}


@router.post("/register-employer")
async def register_employer(req: EmployerRegisterRequest, db: AsyncSession = Depends(get_db)):
    configured = os.getenv("EMPLOYER_INVITE_CODE", "")
    if not configured or not hmac.compare_digest(req.invite_code, configured):
        raise HTTPException(status_code=403, detail="招聘方邀请码无效")
    user = await _create_user(
        db,
        email=req.email,
        password=req.password,
        role="employer",
        terms_accepted=req.terms_accepted,
        privacy_acknowledged=req.privacy_notice_acknowledged,
    )
    return {"msg": "招聘方账号注册成功", "user_id": str(user.id)}


@router.get("/legal-notice")
async def legal_notice():
    """Public runtime identity/contact details used by the versioned notices."""
    return _legal_notice_snapshot()


@router.post("/login")
async def login(
    req: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    email = _normalize_email(req.email)
    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{email}"
    now = datetime.now(timezone.utc)
    window = timedelta(seconds=max(1, int(os.getenv("LOGIN_RATE_WINDOW_SECONDS", "300"))))
    limit = max(1, int(os.getenv("LOGIN_RATE_LIMIT", "5")))
    shared_key = _login_rate_key(client_ip, email)
    attempts = None
    if _shared_auth_state_enabled():
        if await _shared_failure_count(shared_key) >= limit:
            raise HTTPException(status_code=429, detail="登录尝试过多，请稍后再试")
    else:
        attempts = _login_attempts[key]
        while attempts and attempts[0] <= now - window:
            attempts.popleft()
        if len(attempts) >= limit:
            raise HTTPException(status_code=429, detail="登录尝试过多，请稍后再试")

    stmt = select(User).where(User.email == email)
    result = await db.execute(stmt)
    user = result.scalars().first()
    password_hash = user.password_hash if user else _dummy_password_hash
    valid = verify_password(req.password, password_hash)
    if not user or not valid:
        if _shared_auth_state_enabled():
            await _record_shared_failure(shared_key, int(window.total_seconds()))
        else:
            attempts.append(now)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )
    if _shared_auth_state_enabled():
        await _clear_shared_failures(shared_key)
    else:
        attempts.clear()
    token = create_access_token(
        data={
            "sub": str(user.id),
            "role": user.role,
            "sv": int(user.session_version or 1),
        }
    )
    _set_auth_cookies(response, token)
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "user_id": str(user.id),
    }


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    token: str | None = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
):
    resolved_token = token or request.cookies.get(AUTH_COOKIE_NAME)
    if resolved_token:
        await revoke_access_token(resolved_token)
    _clear_auth_cookies(response)
    return {"status": "ok"}


@router.get("/session")
async def session(current_user: User = Depends(get_current_user)):
    return {
        "authenticated": True,
        "role": current_user.role,
        "user_id": str(current_user.id),
    }


_RESET_ACCEPTED = {"status": "accepted"}


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
async def request_password_reset(
    req: PasswordResetRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Issue a short-lived reset link without revealing account existence."""
    email = _normalize_email(req.email)
    client_ip = request.client.host if request.client else "unknown"
    if not await _password_reset_allowed(client_ip, email):
        return _RESET_ACCEPTED

    origin = _reset_origin()
    if not origin or not smtp_configured():
        return _RESET_ACCEPTED

    result = await db.execute(select(User).where(User.email == email))
    user = result.scalars().first()
    if user is None:
        return _RESET_ACCEPTED

    now = datetime.now(timezone.utc)
    await db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    raw_token = secrets.token_urlsafe(32)
    ttl_minutes = min(60, max(10, int(os.getenv("PASSWORD_RESET_TTL_MINUTES", "30"))))
    reset_token = PasswordResetToken(
        id=str(uuid.uuid4()),
        user_id=user.id,
        token_hash=hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        expires_at=now + timedelta(minutes=ttl_minutes),
        created_at=now,
    )
    db.add(reset_token)
    await db.commit()

    reset_url = f"{origin}/reset-password?token={quote(raw_token)}"
    body = (
        "<p>你收到此邮件，是因为有人申请重置 QLink 账号密码。</p>"
        f'<p><a href="{html.escape(reset_url, quote=True)}">重置密码</a></p>'
        f"<p>链接将在 {ttl_minutes} 分钟后失效且只能使用一次。若非本人操作，请忽略。</p>"
    )
    try:
        await send_email(email, "QLink 密码重置", body)
    except Exception as exc:
        reset_token.used_at = datetime.now(timezone.utc)
        await db.commit()
        logger.warning("password reset email failed error_type=%s", type(exc).__name__)
    return _RESET_ACCEPTED


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    req: PasswordResetConfirmRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    _validate_password(req.new_password)
    token_hash = hashlib.sha256(req.token.encode("utf-8")).hexdigest()
    result = await db.execute(
        select(PasswordResetToken)
        .where(PasswordResetToken.token_hash == token_hash)
        .with_for_update()
    )
    reset_token = result.scalars().first()
    now = datetime.now(timezone.utc)
    if (
        reset_token is None
        or reset_token.used_at is not None
        or _utc(reset_token.expires_at) <= now
    ):
        raise HTTPException(status_code=400, detail="重置链接无效或已过期")

    user = await db.get(User, reset_token.user_id)
    if user is None:
        raise HTTPException(status_code=400, detail="重置链接无效或已过期")
    user.password_hash = get_password_hash(req.new_password)
    user.session_version = int(user.session_version or 1) + 1
    await db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.user_id == user.id,
            PasswordResetToken.used_at.is_(None),
        )
        .values(used_at=now)
    )
    await db.commit()
    _clear_auth_cookies(response)
    return {"status": "password_reset"}


@router.post("/password/change")
async def change_password(
    req: ChangePasswordRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(req.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="当前密码错误")
    _validate_password(req.new_password)
    if verify_password(req.new_password, current_user.password_hash):
        raise HTTPException(status_code=422, detail="新密码不能与当前密码相同")
    current_user.password_hash = get_password_hash(req.new_password)
    current_user.session_version = int(current_user.session_version or 1) + 1
    await db.commit()
    _clear_auth_cookies(response)
    return {"status": "password_changed"}


@router.delete("/account")
async def delete_account(
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == "admin":
        raise HTTPException(status_code=403, detail="管理员账号不能通过自助接口删除")
    await delete_user_graph(db, str(current_user.id))
    await db.commit()
    _clear_auth_cookies(response)
    return {"status": "ok"}
