"""Admin data source registry APIs (PR10)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .ai.data_sources import (
    SOURCE_LAYERS,
    SOURCE_STATUSES,
    VERSION_STATUSES,
    assert_source_usable_for_formal_profile,
    public_source_view,
)
from .database import get_db
from .models_db import DataSource, DataSourceVersion, User
from .security import require_admin

router = APIRouter(prefix="/admin/data-sources", tags=["data-sources"])


class DataSourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    owner_organization: Optional[str] = None
    acquisition_method: str = "manual"
    license_name: Optional[str] = None
    license_url: Optional[str] = None
    contract_ref: Optional[str] = None
    allowed_product_uses: list[str] = Field(default_factory=list)
    training_allowed: bool = False
    contains_personal_data: bool = False
    processing_region: str = "cn-beijing"
    attribution_text: Optional[str] = None
    deletion_contact: Optional[str] = None
    status: str = "pending_review"
    layer: str = "E"
    scope: dict[str, Any] = Field(default_factory=dict)


class DataSourcePatch(BaseModel):
    status: Optional[str] = None
    layer: Optional[str] = None
    attribution_text: Optional[str] = None
    allowed_product_uses: Optional[list[str]] = None
    training_allowed: Optional[bool] = None
    scope: Optional[dict[str, Any]] = None


class DataSourceVersionCreate(BaseModel):
    external_version: str
    checksum: Optional[str] = None
    raw_object_ref: Optional[str] = None
    parser_version: Optional[str] = None
    validation_report: Optional[dict[str, Any]] = None
    expires_at: Optional[datetime] = None
    status: str = "pending_validation"


def _serialize_source(row: DataSource) -> dict[str, Any]:
    return public_source_view(
        {
            "id": str(row.id),
            "name": row.name,
            "owner_organization": row.owner_organization,
            "acquisition_method": row.acquisition_method,
            "license_name": row.license_name,
            "allowed_product_uses": row.allowed_product_uses or [],
            "training_allowed": row.training_allowed,
            "contains_personal_data": row.contains_personal_data,
            "processing_region": row.processing_region,
            "attribution_text": row.attribution_text,
            "status": row.status,
            "layer": row.layer,
            "scope": row.scope or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    )


@router.get("")
async def list_admin_data_sources(
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    rows = (await db.execute(select(DataSource).order_by(DataSource.created_at.desc()))).scalars().all()
    return {"sources": [_serialize_source(row) for row in rows]}


@router.post("")
async def create_data_source(
    body: DataSourceCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.status not in SOURCE_STATUSES:
        raise HTTPException(status_code=400, detail="非法 status")
    if body.layer not in SOURCE_LAYERS:
        raise HTTPException(status_code=400, detail="非法 layer")
    row = DataSource(
        id=str(uuid.uuid4()),
        name=body.name.strip(),
        owner_organization=body.owner_organization,
        acquisition_method=body.acquisition_method,
        license_name=body.license_name,
        license_url=body.license_url,
        contract_ref=body.contract_ref,
        allowed_product_uses=body.allowed_product_uses,
        training_allowed=body.training_allowed,
        contains_personal_data=body.contains_personal_data,
        processing_region=body.processing_region,
        attribution_text=body.attribution_text,
        deletion_contact=body.deletion_contact,
        status=body.status,
        layer=body.layer,
        scope=body.scope,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {"source": _serialize_source(row)}


@router.patch("/{source_id}")
async def patch_data_source(
    source_id: str,
    body: DataSourcePatch,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(DataSource, source_id)
    if not row:
        raise HTTPException(status_code=404, detail="来源不存在")
    payload = body.model_dump(exclude_unset=True)
    if "status" in payload and payload["status"] not in SOURCE_STATUSES:
        raise HTTPException(status_code=400, detail="非法 status")
    if "layer" in payload and payload["layer"] not in SOURCE_LAYERS:
        raise HTTPException(status_code=400, detail="非法 layer")
    for key, value in payload.items():
        setattr(row, key, value)
    row.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return {"source": _serialize_source(row)}


@router.post("/{source_id}/versions")
async def add_data_source_version(
    source_id: str,
    body: DataSourceVersionCreate,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    source = await db.get(DataSource, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="来源不存在")
    if body.status not in VERSION_STATUSES:
        raise HTTPException(status_code=400, detail="非法版本 status")
    version = DataSourceVersion(
        id=str(uuid.uuid4()),
        source_id=source_id,
        external_version=body.external_version,
        checksum=body.checksum,
        raw_object_ref=body.raw_object_ref,
        parser_version=body.parser_version,
        validation_report=body.validation_report,
        expires_at=body.expires_at,
        status=body.status,
        retrieved_at=datetime.now(timezone.utc),
        effective_at=datetime.now(timezone.utc),
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return {
        "version": {
            "id": str(version.id),
            "source_id": source_id,
            "external_version": version.external_version,
            "checksum": version.checksum,
            "parser_version": version.parser_version,
            "status": version.status,
            "expires_at": version.expires_at.isoformat() if version.expires_at else None,
            "created_at": version.created_at.isoformat() if version.created_at else None,
        }
    }


@router.get("/{source_id}/versions")
async def list_data_source_versions(
    source_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    if not await db.get(DataSource, source_id):
        raise HTTPException(status_code=404, detail="来源不存在")
    rows = (
        await db.execute(
            select(DataSourceVersion)
            .where(DataSourceVersion.source_id == source_id)
            .order_by(DataSourceVersion.created_at.desc())
        )
    ).scalars().all()
    return {
        "versions": [
            {
                "id": str(row.id),
                "external_version": row.external_version,
                "status": row.status,
                "checksum": row.checksum,
                "retrieved_at": row.retrieved_at.isoformat() if row.retrieved_at else None,
                "effective_at": row.effective_at.isoformat() if row.effective_at else None,
                "expires_at": row.expires_at.isoformat() if row.expires_at else None,
                "superseded_by_version_id": row.superseded_by_version_id,
                "validation_report": row.validation_report,
            }
            for row in rows
        ]
    }


@router.get("/{source_id}/formal-profile-gate")
async def check_formal_profile_gate(
    source_id: str,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    row = await db.get(DataSource, source_id)
    if not row:
        raise HTTPException(status_code=404, detail="来源不存在")
    try:
        assert_source_usable_for_formal_profile(
            {"status": row.status, "layer": row.layer}
        )
        usable = True
        reason = None
    except PermissionError as exc:
        usable = False
        reason = str(exc)
    return {"source_id": source_id, "usable_for_formal_profile": usable, "reason": reason}
