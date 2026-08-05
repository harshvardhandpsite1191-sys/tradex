"""
AI-QROS — Feature Registry Router
Phase 0: Project Foundation
Manages all 500-1000+ features across 13 categories
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.db.database import get_db
from app.models.governance import FeatureRegistry, FeatureVersion
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/governance/features", tags=["Feature Registry"])

# 13 Feature Categories (Phase 0 — Pre-seeded)
FEATURE_CATEGORIES = [
    "PRICE", "TREND", "MOMENTUM", "LIQUIDITY", "OPTIONS",
    "GREEKS", "VOLUME", "MACRO", "INSTITUTIONAL",
    "EXPIRY", "OPENING", "PREMIUM_BEHAVIOUR", "VOLATILITY"
]


class FeatureCreate(BaseModel):
    feature_name: str
    category: str
    description: Optional[str] = None
    computation_logic: Optional[str] = None
    data_type: str = "float"
    impact_weight: Optional[float] = None


class FeatureResponse(BaseModel):
    id: str
    feature_name: str
    category: str
    description: Optional[str]
    computation_logic: Optional[str]
    data_type: str
    impact_weight: Optional[float]
    version: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


@router.get("/categories", dependencies=[Depends(require_viewer)])
async def get_categories():
    """Return all 13 feature categories."""
    return {"categories": FEATURE_CATEGORIES, "total": len(FEATURE_CATEGORIES)}


@router.post("/", response_model=FeatureResponse, dependencies=[Depends(require_admin)])
async def create_feature(feature: FeatureCreate, db: AsyncSession = Depends(get_db)):
    """Register a new feature."""
    if feature.category not in FEATURE_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Must be one of: {FEATURE_CATEGORIES}")

    existing = await db.execute(select(FeatureRegistry).where(FeatureRegistry.feature_name == feature.feature_name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Feature '{feature.feature_name}' already registered.")

    db_feature = FeatureRegistry(**feature.model_dump(), version=1)
    db.add(db_feature)
    await db.flush()

    version_record = FeatureVersion(
        feature_id=db_feature.id,
        version=1,
        computation_logic_snapshot=feature.computation_logic,
        change_reason="Initial registration",
        is_current=True,
    )
    db.add(version_record)
    await db.commit()
    await db.refresh(db_feature)
    return db_feature


@router.get("/", response_model=List[FeatureResponse], dependencies=[Depends(require_viewer)])
async def list_features(
    category: Optional[str] = None,
    is_active: Optional[bool] = True,
    db: AsyncSession = Depends(get_db)
):
    """List all registered features, optionally filtered by category."""
    query = select(FeatureRegistry)
    if category:
        query = query.where(FeatureRegistry.category == category)
    if is_active is not None:
        query = query.where(FeatureRegistry.is_active == is_active)
    result = await db.execute(query.order_by(FeatureRegistry.category, FeatureRegistry.feature_name))
    return result.scalars().all()


@router.get("/count", dependencies=[Depends(require_viewer)])
async def get_feature_count(db: AsyncSession = Depends(get_db)):
    """Get total feature count per category."""
    from sqlalchemy import func
    result = await db.execute(
        select(FeatureRegistry.category, func.count(FeatureRegistry.id))
        .where(FeatureRegistry.is_active == True)
        .group_by(FeatureRegistry.category)
        .order_by(FeatureRegistry.category)
    )
    counts = {row[0]: row[1] for row in result.all()}
    return {"per_category": counts, "total": sum(counts.values())}
