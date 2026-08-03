"""Evidence object storage adapters and short-lived signed download URLs."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import urlencode


class ObjectStorage(Protocol):
    def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> str: ...

    def get_bytes(self, key: str) -> bytes: ...

    def delete(self, key: str) -> None: ...

    def exists(self, key: str) -> bool: ...


@dataclass(frozen=True)
class SignedDownload:
    url: str
    expires_at: int
    backend: str


def storage_backend_name() -> str:
    return (os.getenv("OBJECT_STORAGE_BACKEND") or "local").strip().lower()


def signed_url_ttl_seconds() -> int:
    return max(30, int(os.getenv("SIGNED_URL_TTL_SECONDS", "300")))


def _signing_secret() -> bytes:
    secret = (
        os.getenv("EVIDENCE_DOWNLOAD_SIGNING_KEY")
        or os.getenv("FIDELITY_PROOF_SECRET_KEY")
        or os.getenv("SECRET_KEY")
        or ""
    ).strip()
    if len(secret) < 16:
        raise RuntimeError("EVIDENCE_DOWNLOAD_SIGNING_KEY or SECRET_KEY must be configured")
    return secret.encode("utf-8")


def evidence_object_key(*, user_id: str, artifact_id: str, filename_hint: str = "bin") -> str:
    safe_hint = "".join(ch for ch in filename_hint if ch.isalnum() or ch in "._-")[:32] or "bin"
    return f"evidence/{user_id}/{artifact_id}/{secrets.token_hex(16)}-{safe_hint}"


class LocalVolumeAdapter:
    """Private local volume storage; downloads go through app-signed URLs."""

    name = "local"

    def __init__(self, root: str | None = None) -> None:
        configured = root or os.getenv("EVIDENCE_VAULT_DIR")
        if not configured:
            configured = (
                "/data/evidence-vault"
                if os.getenv("ENV", "").strip().lower() == "production"
                else "evidence_vault"
            )
        self.root = Path(configured)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        # Prevent path traversal: only allow keys under evidence/
        if ".." in key or key.startswith("/") or "\\" in key:
            raise ValueError("invalid object key")
        path = (self.root / key).resolve()
        if not str(path).startswith(str(self.root.resolve())):
            raise ValueError("object key escapes storage root")
        return path

    def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get_bytes(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()


class S3CompatibleAdapter:
    """Minimal S3-compatible put/get using optional boto3.

    If boto3 is unavailable, instantiation fails loudly so ops can fall back to local.
    """

    name = "s3"

    def __init__(self) -> None:
        try:
            import boto3
            from botocore.client import Config
        except ImportError as exc:  # pragma: no cover - optional dep
            raise RuntimeError(
                "OBJECT_STORAGE_BACKEND=s3 requires boto3; pip install boto3 or use local"
            ) from exc
        endpoint = (os.getenv("S3_ENDPOINT") or "").strip() or None
        region = (os.getenv("S3_REGION") or "us-east-1").strip()
        self.bucket = (os.getenv("S3_BUCKET") or "").strip()
        if not self.bucket:
            raise RuntimeError("S3_BUCKET is required for s3 storage backend")
        self.client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=(os.getenv("S3_ACCESS_KEY") or "").strip() or None,
            aws_secret_access_key=(os.getenv("S3_SECRET_KEY") or "").strip() or None,
            region_name=region,
            config=Config(signature_version="s3v4"),
        )

    def put_bytes(self, key: str, data: bytes, *, content_type: str | None = None) -> str:
        extra = {"ContentType": content_type} if content_type else {}
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, **extra)
        return key

    def get_bytes(self, key: str) -> bytes:
        obj = self.client.get_object(Bucket=self.bucket, Key=key)
        return obj["Body"].read()

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:
            return False

    def presign_get(self, key: str, *, expires_in: int) -> str:
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_in,
        )


def get_object_storage() -> ObjectStorage:
    backend = storage_backend_name()
    if backend in {"s3", "minio"}:
        return S3CompatibleAdapter()
    return LocalVolumeAdapter()


def issue_download_token(*, artifact_id: str, user_id: str, object_ref: str) -> SignedDownload:
    """Issue a short-lived HMAC token for app-mediated download."""
    expires_at = int(time.time()) + signed_url_ttl_seconds()
    payload = f"{artifact_id}:{user_id}:{object_ref}:{expires_at}"
    signature = hmac.new(_signing_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    token = base64.urlsafe_b64encode(f"{expires_at}.{signature}".encode("utf-8")).decode("ascii")
    query = urlencode({"token": token})
    # Relative API path; frontend/nginx prefixes /api.
    url = f"/evidence-vault/artifacts/{artifact_id}/download?{query}"
    return SignedDownload(url=url, expires_at=expires_at, backend=storage_backend_name())


def verify_download_token(
    *,
    token: str,
    artifact_id: str,
    user_id: str,
    object_ref: str,
) -> None:
    try:
        decoded = base64.urlsafe_b64decode(token.encode("ascii")).decode("utf-8")
        expires_raw, signature = decoded.split(".", 1)
        expires_at = int(expires_raw)
    except Exception as exc:
        raise PermissionError("invalid_download_token") from exc
    if expires_at < int(time.time()):
        raise PermissionError("download_token_expired")
    payload = f"{artifact_id}:{user_id}:{object_ref}:{expires_at}"
    expected = hmac.new(_signing_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise PermissionError("invalid_download_token")


def maybe_s3_presign(object_ref: str) -> SignedDownload | None:
    """When using S3/MinIO, prefer native presigned URLs."""
    if storage_backend_name() not in {"s3", "minio"}:
        return None
    storage = get_object_storage()
    if not isinstance(storage, S3CompatibleAdapter):
        return None
    expires = signed_url_ttl_seconds()
    url = storage.presign_get(object_ref, expires_in=expires)
    return SignedDownload(url=url, expires_at=int(time.time()) + expires, backend="s3")
