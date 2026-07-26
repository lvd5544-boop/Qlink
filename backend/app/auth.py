import os
from datetime import datetime, timedelta, timezone
from typing import Optional
import uuid
import bcrypt
import jwt
from dotenv import load_dotenv
from jwt import InvalidTokenError as JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession
from .database import get_db
from .models_db import User

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
_revoked_tokens: dict[str, datetime] = {}
_auth_redis = None


def validate_auth_configuration() -> None:
    environment = os.getenv("ENV", "development").strip().lower()
    if environment != "production":
        return
    secret = SECRET_KEY.encode("utf-8")
    if SECRET_KEY == "dev-secret-key-change-in-production" or len(secret) < 32:
        raise RuntimeError("生产环境必须设置高强度 SECRET_KEY（至少 32 字节）")


def _shared_auth_state_enabled() -> bool:
    configured = os.getenv("AUTH_STATE_BACKEND", "").strip().lower()
    if configured:
        return configured == "redis"
    return os.getenv("ENV", "development").strip().lower() == "production"


def _get_auth_redis():
    global _auth_redis
    if _auth_redis is None:
        _auth_redis = aioredis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            decode_responses=True,
        )
    return _auth_redis


def _truncate_password(password: str) -> bytes:
    """将密码截断到 bcrypt 允许的 72 字节"""
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
    return password_bytes


def get_password_hash(password: str) -> str:
    """返回哈希后的密码字符串"""
    truncated = _truncate_password(password)
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(truncated, salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    if not hashed_password:
        return False
    truncated = _truncate_password(plain_password)
    return bcrypt.checkpw(truncated, hashed_password.encode("utf-8"))


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.setdefault("jti", str(uuid.uuid4()))
    to_encode.update({"exp": expire, "iat": now})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])


async def revoke_access_token(token: str) -> None:
    payload = decode_access_token(token)
    jti = payload.get("jti")
    exp = payload.get("exp")
    if jti and exp:
        expiry = datetime.fromtimestamp(float(exp), tz=timezone.utc)
        if _shared_auth_state_enabled():
            ttl = max(1, int((expiry - datetime.now(timezone.utc)).total_seconds()))
            try:
                await _get_auth_redis().set(f"auth:revoked:{jti}", "1", ex=ttl)
            except Exception as exc:
                raise HTTPException(
                    status_code=503,
                    detail="认证撤销服务暂不可用，请稍后重试",
                ) from exc
        else:
            _revoked_tokens[str(jti)] = expiry


async def _is_revoked(payload: dict) -> bool:
    jti = payload.get("jti")
    if not jti:
        return False
    if _shared_auth_state_enabled():
        try:
            return bool(await _get_auth_redis().exists(f"auth:revoked:{jti}"))
        except Exception:
            # 撤销状态不可确认时必须 fail closed，不能放行可能已撤销的 token。
            return True
    now = datetime.now(timezone.utc)
    expired = [jti for jti, expiry in _revoked_tokens.items() if expiry <= now]
    for jti in expired:
        _revoked_tokens.pop(jti, None)
    return str(jti) in _revoked_tokens


async def get_user_from_token(token: str, db: AsyncSession) -> Optional[User]:
    """从 JWT 解析用户，供 WebSocket 等无法使用 Bearer 头的场景。"""
    if not token:
        return None
    try:
        payload = decode_access_token(token)
        if await _is_revoked(payload):
            return None
        user_id: str = payload.get("sub")
        if user_id is None:
            return None
    except JWTError:
        return None
    return await db.get(User, user_id)


async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_access_token(token)
        if await _is_revoked(payload):
            raise credentials_exception
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    user = await db.get(User, user_id)
    if user is None:
        raise credentials_exception
    return user
