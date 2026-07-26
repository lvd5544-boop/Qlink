from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import os
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from .database import get_db
from .models_db import User
from .auth import (
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

router = APIRouter(prefix="/auth", tags=["认证"])


class RegisterRequest(BaseModel):
    email: str
    password: str
    role: str = "candidate"


class EmployerRegisterRequest(BaseModel):
    email: str
    password: str
    invite_code: str = Field(..., min_length=1)


class LoginRequest(BaseModel):
    email: str
    password: str


_login_attempts: dict[str, deque[datetime]] = defaultdict(deque)
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


async def _create_user(db: AsyncSession, *, email: str, password: str, role: str) -> User:
    normalized = _normalize_email(email)
    _validate_password(password)
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
    await provision_new_user_billing(db, user=user)
    await db.commit()
    await db.refresh(user)
    return user


@router.post("/register")
async def register(req: RegisterRequest, db: AsyncSession = Depends(get_db)):
    if req.role != "candidate":
        raise HTTPException(status_code=403, detail="公开注册仅支持求职者账号")
    user = await _create_user(db, email=req.email, password=req.password, role="candidate")
    return {"msg": "注册成功", "user_id": str(user.id)}


@router.post("/register-employer")
async def register_employer(req: EmployerRegisterRequest, db: AsyncSession = Depends(get_db)):
    configured = os.getenv("EMPLOYER_INVITE_CODE", "")
    if not configured or not hmac.compare_digest(req.invite_code, configured):
        raise HTTPException(status_code=403, detail="招聘方邀请码无效")
    user = await _create_user(db, email=req.email, password=req.password, role="employer")
    return {"msg": "招聘方账号注册成功", "user_id": str(user.id)}


@router.post("/login")
async def login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
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
    token = create_access_token(data={"sub": str(user.id), "role": user.role})
    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user.role,
        "user_id": str(user.id),
    }


@router.post("/logout")
async def logout(
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
):
    await revoke_access_token(token)
    return {"status": "ok"}


@router.delete("/account")
async def delete_account(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if current_user.role == "admin":
        raise HTTPException(status_code=403, detail="管理员账号不能通过自助接口删除")
    await delete_user_graph(db, str(current_user.id))
    await db.commit()
    return {"status": "ok"}
