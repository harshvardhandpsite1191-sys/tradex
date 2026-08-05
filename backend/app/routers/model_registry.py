"""
AI-QROS — Model Registry Router
Phase 0: Project Foundation
API wrapper around MLflow Model Registry + local DB metadata
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.db.database import get_db
from app.models.governance import ModelRegistry, ModelVersion
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/governance/models", tags=["Model Registry"])

MODEL_TYPES  = ["XGBOOST", "LIGHTGBM", "CATBOOST", "RANDOM_FOREST"]
MODEL_STAGES = ["development", "staging", "production", "archived"]


class ModelCreate(BaseModel):
    model_name: str
    model_type: str
    purpose: Optional[str] = None
    mlflow_run_id: Optional[str] = None
    mlflow_model_uri: Optional[str] = None
    feature_registry_version: Optional[int] = None
    training_data_window_start: Optional[datetime] = None
    training_data_window_end: Optional[datetime] = None
    metrics: Optional[dict] = None


class ModelPromote(BaseModel):
    target_stage: str
    change_reason: str


class ModelResponse(BaseModel):
    id: str
    model_name: str
    model_type: str
    purpose: Optional[str]
    mlflow_run_id: Optional[str]
    mlflow_model_uri: Optional[str]
    metrics: Optional[dict]
    stage: str
    version: int
    is_active: bool
    created_at: datetime
    promoted_at: Optional[datetime]

    class Config:
        from_attributes = True


@router.post("/", response_model=ModelResponse, dependencies=[Depends(require_admin)])
async def register_model(model: ModelCreate, db: AsyncSession = Depends(get_db)):
    """Register a new model version from a completed MLflow training run."""
    if model.model_type not in MODEL_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid model_type. Must be one of: {MODEL_TYPES}")

    db_model = ModelRegistry(
        **model.model_dump(),
        stage="development",
        version=1,
        is_active=False,
    )
    db.add(db_model)
    await db.flush()

    version_record = ModelVersion(
        model_id=db_model.id,
        version=1,
        stage="development",
        mlflow_run_id=model.mlflow_run_id,
        metrics_snapshot=model.metrics,
        change_reason="Initial registration from training run",
        is_current=True,
    )
    db.add(version_record)
    await db.commit()
    await db.refresh(db_model)
    return db_model


@router.get("/", response_model=List[ModelResponse], dependencies=[Depends(require_viewer)])
async def list_models(
    stage: Optional[str] = None,
    model_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List all registered models, optionally filtered by stage and type."""
    query = select(ModelRegistry)
    if stage:
        query = query.where(ModelRegistry.stage == stage)
    if model_type:
        query = query.where(ModelRegistry.model_type == model_type)
    result = await db.execute(query.order_by(ModelRegistry.created_at.desc()))
    return result.scalars().all()


@router.post("/{model_id}/promote", response_model=ModelResponse, dependencies=[Depends(require_admin)])
async def promote_model(model_id: str, promote_data: ModelPromote, db: AsyncSession = Depends(get_db)):
    """
    Promote a model to staging or production.
    Phase 22 (Continuous Learning) NEVER auto-promotes — human approval required.
    """
    if promote_data.target_stage not in MODEL_STAGES:
        raise HTTPException(status_code=400, detail=f"Invalid stage. Must be one of: {MODEL_STAGES}")

    result = await db.execute(select(ModelRegistry).where(ModelRegistry.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found.")

    # Mark previous versions of same model as not current
    await db.execute(
        update(ModelVersion).where(ModelVersion.model_id == model.id).values(is_current=False)
    )

    new_version = model.version + 1
    model.stage = promote_data.target_stage
    model.version = new_version
    model.is_active = (promote_data.target_stage == "production")
    model.promoted_at = datetime.utcnow()

    version_record = ModelVersion(
        model_id=model.id,
        version=new_version,
        stage=promote_data.target_stage,
        mlflow_run_id=model.mlflow_run_id,
        metrics_snapshot=model.metrics,
        change_reason=promote_data.change_reason,
        is_current=True,
    )
    db.add(version_record)
    await db.commit()
    await db.refresh(model)
    return model


@router.post("/{model_id}/rollback/{version}", dependencies=[Depends(require_admin)])
async def rollback_model(model_id: str, version: int, db: AsyncSession = Depends(get_db)):
    """Rollback a model to a prior version."""
    result = await db.execute(select(ModelRegistry).where(ModelRegistry.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found.")

    target = await db.execute(
        select(ModelVersion).where(ModelVersion.model_id == model_id, ModelVersion.version == version)
    )
    target_version = target.scalar_one_or_none()
    if not target_version:
        raise HTTPException(status_code=404, detail=f"Version {version} not found.")

    await db.execute(update(ModelVersion).where(ModelVersion.model_id == model_id).values(is_current=False))

    new_version = model.version + 1
    model.stage = target_version.stage
    model.version = new_version
    model.promoted_at = datetime.utcnow()

    rollback_record = ModelVersion(
        model_id=model.id,
        version=new_version,
        stage=target_version.stage,
        mlflow_run_id=target_version.mlflow_run_id,
        metrics_snapshot=target_version.metrics_snapshot,
        change_reason=f"Rollback to version {version}",
        is_current=True,
    )
    db.add(rollback_record)
    await db.commit()
    return {"message": f"Model rolled back to version {version}.", "current_version": new_version}


@router.get("/{model_id}/history", dependencies=[Depends(require_viewer)])
async def get_model_history(model_id: str, db: AsyncSession = Depends(get_db)):
    """Get full version history for a model."""
    result = await db.execute(select(ModelRegistry).where(ModelRegistry.id == model_id))
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found.")

    versions = await db.execute(
        select(ModelVersion).where(ModelVersion.model_id == model_id).order_by(ModelVersion.version.desc())
    )
    return {"model_name": model.model_name, "versions": versions.scalars().all()}
