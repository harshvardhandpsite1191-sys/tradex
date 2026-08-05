"""
AI-QROS — Rule Registry
Phase 0: Project Foundation
CRUD API for all operational rules and thresholds
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.db.database import get_db
from app.models.governance import RuleRegistry, RuleVersion
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/governance/rules", tags=["Rule Registry"])


# ─────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────
class RuleCreate(BaseModel):
    rule_name: str
    description: Optional[str] = None
    category: str
    parameters: dict
    change_reason: Optional[str] = "Initial creation"


class RuleUpdate(BaseModel):
    description: Optional[str] = None
    parameters: Optional[dict] = None
    is_active: Optional[bool] = None
    change_reason: str


class RuleResponse(BaseModel):
    id: str
    rule_name: str
    description: Optional[str]
    category: str
    parameters: dict
    version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────
@router.post("/", response_model=RuleResponse, dependencies=[Depends(require_admin)])
async def create_rule(rule: RuleCreate, db: AsyncSession = Depends(get_db)):
    """Create a new rule in the registry."""
    # Check for duplicate name
    existing = await db.execute(select(RuleRegistry).where(RuleRegistry.rule_name == rule.rule_name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Rule '{rule.rule_name}' already exists.")

    db_rule = RuleRegistry(
        rule_name=rule.rule_name,
        description=rule.description,
        category=rule.category,
        parameters=rule.parameters,
        version=1,
    )
    db.add(db_rule)
    await db.flush()

    # Create initial version record
    version_record = RuleVersion(
        rule_id=db_rule.id,
        version=1,
        parameters_snapshot=rule.parameters,
        change_reason=rule.change_reason,
        is_current=True,
    )
    db.add(version_record)
    await db.commit()
    await db.refresh(db_rule)
    return db_rule


@router.get("/", response_model=List[RuleResponse], dependencies=[Depends(require_viewer)])
async def list_rules(
    category: Optional[str] = None,
    is_active: Optional[bool] = True,
    db: AsyncSession = Depends(get_db)
):
    """List all rules, optionally filtered by category and active status."""
    query = select(RuleRegistry)
    if category:
        query = query.where(RuleRegistry.category == category)
    if is_active is not None:
        query = query.where(RuleRegistry.is_active == is_active)
    result = await db.execute(query.order_by(RuleRegistry.category, RuleRegistry.rule_name))
    return result.scalars().all()


@router.get("/{rule_name}", response_model=RuleResponse, dependencies=[Depends(require_viewer)])
async def get_rule(rule_name: str, db: AsyncSession = Depends(get_db)):
    """Get a specific rule by name."""
    result = await db.execute(select(RuleRegistry).where(RuleRegistry.rule_name == rule_name))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_name}' not found.")
    return rule


@router.put("/{rule_name}", response_model=RuleResponse, dependencies=[Depends(require_admin)])
async def update_rule(rule_name: str, update_data: RuleUpdate, db: AsyncSession = Depends(get_db)):
    """Update a rule — automatically creates a new version record."""
    result = await db.execute(select(RuleRegistry).where(RuleRegistry.rule_name == rule_name))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_name}' not found.")

    # Mark all previous versions as not current
    await db.execute(
        update(RuleVersion)
        .where(RuleVersion.rule_id == rule.id)
        .values(is_current=False)
    )

    # Apply updates
    new_version = rule.version + 1
    if update_data.parameters is not None:
        rule.parameters = update_data.parameters
    if update_data.description is not None:
        rule.description = update_data.description
    if update_data.is_active is not None:
        rule.is_active = update_data.is_active
    rule.version = new_version
    rule.updated_at = datetime.utcnow()

    # Create new version record
    version_record = RuleVersion(
        rule_id=rule.id,
        version=new_version,
        parameters_snapshot=rule.parameters,
        change_reason=update_data.change_reason,
        is_current=True,
    )
    db.add(version_record)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.get("/{rule_name}/history", dependencies=[Depends(require_viewer)])
async def get_rule_history(rule_name: str, db: AsyncSession = Depends(get_db)):
    """Get full version history for a rule."""
    result = await db.execute(select(RuleRegistry).where(RuleRegistry.rule_name == rule_name))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_name}' not found.")

    versions = await db.execute(
        select(RuleVersion)
        .where(RuleVersion.rule_id == rule.id)
        .order_by(RuleVersion.version.desc())
    )
    return {"rule_name": rule_name, "versions": versions.scalars().all()}


@router.post("/{rule_name}/rollback/{version}", dependencies=[Depends(require_admin)])
async def rollback_rule(rule_name: str, version: int, db: AsyncSession = Depends(get_db)):
    """Rollback a rule to a specific version."""
    result = await db.execute(select(RuleRegistry).where(RuleRegistry.rule_name == rule_name))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(status_code=404, detail=f"Rule '{rule_name}' not found.")

    version_result = await db.execute(
        select(RuleVersion)
        .where(RuleVersion.rule_id == rule.id, RuleVersion.version == version)
    )
    target_version = version_result.scalar_one_or_none()
    if not target_version:
        raise HTTPException(status_code=404, detail=f"Version {version} not found for rule '{rule_name}'.")

    # Mark all versions as not current
    await db.execute(update(RuleVersion).where(RuleVersion.rule_id == rule.id).values(is_current=False))

    # Apply rollback
    new_version = rule.version + 1
    rule.parameters = target_version.parameters_snapshot
    rule.version = new_version
    rule.updated_at = datetime.utcnow()

    rollback_version = RuleVersion(
        rule_id=rule.id,
        version=new_version,
        parameters_snapshot=target_version.parameters_snapshot,
        change_reason=f"Rollback to version {version}",
        is_current=True,
    )
    db.add(rollback_version)
    await db.commit()
    await db.refresh(rule)
    return {"message": f"Rule '{rule_name}' rolled back to version {version}.", "current_version": new_version}
