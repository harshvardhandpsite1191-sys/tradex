"""
AI-QROS — Knowledge Base API Router
Phase 1: Institutional Research Library
Endpoints: list, get, filter by category/rank, version history
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.db.database import get_db
from app.models.knowledge import KnowledgeConcept
from app.models.governance import ArtifactVersionHistory
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base"])


# ─────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────
class ConceptCreate(BaseModel):
    name: str
    category: str
    sub_category: Optional[str] = None
    description: str
    definition: str
    market_relevance: str
    conditions: Optional[dict] = None


class ConceptResponse(BaseModel):
    id: str
    name: str
    category: str
    sub_category: Optional[str]
    description: str
    definition: str
    market_relevance: str
    conditions: Optional[dict]
    rank_score: Optional[float]
    last_ranked_at: Optional[datetime]
    version: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class CategorySummary(BaseModel):
    category: str
    count: int


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.get("/categories", dependencies=[Depends(require_viewer)])
async def get_categories(db: AsyncSession = Depends(get_db)):
    """Return all 13 categories with concept counts."""
    result = await db.execute(
        select(KnowledgeConcept.category, func.count(KnowledgeConcept.id))
        .where(KnowledgeConcept.is_active == True)
        .group_by(KnowledgeConcept.category)
        .order_by(KnowledgeConcept.category)
    )
    rows = result.all()
    categories = [{"category": row[0], "count": row[1]} for row in rows]
    return {
        "categories": categories,
        "total_categories": len(categories),
        "total_concepts": sum(r["count"] for r in categories),
    }


@router.get("/concepts", response_model=List[ConceptResponse], dependencies=[Depends(require_viewer)])
async def list_concepts(
    category: Optional[str] = Query(None, description="Filter by category"),
    min_rank: Optional[float] = Query(None, description="Filter by minimum rank score"),
    is_active: Optional[bool] = Query(True),
    limit: int = Query(100, le=200),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db)
):
    """
    List all concepts. Filter by category, rank score, or active status.
    Queryable by category, name, rank.
    """
    query = select(KnowledgeConcept)

    if category:
        query = query.where(KnowledgeConcept.category == category)
    if min_rank is not None:
        query = query.where(KnowledgeConcept.rank_score >= min_rank)
    if is_active is not None:
        query = query.where(KnowledgeConcept.is_active == is_active)

    query = query.order_by(
        KnowledgeConcept.rank_score.desc().nullslast(),
        KnowledgeConcept.category,
        KnowledgeConcept.name
    ).limit(limit).offset(offset)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/concepts/{concept_id}", response_model=ConceptResponse, dependencies=[Depends(require_viewer)])
async def get_concept(concept_id: str, db: AsyncSession = Depends(get_db)):
    """Get a single concept with full detail."""
    result = await db.execute(
        select(KnowledgeConcept).where(KnowledgeConcept.id == concept_id)
    )
    concept = result.scalar_one_or_none()
    if not concept:
        raise HTTPException(status_code=404, detail=f"Concept '{concept_id}' not found.")
    return concept


@router.get("/concepts/{concept_id}/rank-history", dependencies=[Depends(require_viewer)])
async def get_rank_history(concept_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get the rank score history for a concept.
    Rank scores are updated by Phase 9 (Knowledge Ranking Engine).
    History is stored in ArtifactVersionHistory with type=KNOWLEDGE.
    """
    # Verify concept exists
    result = await db.execute(
        select(KnowledgeConcept).where(KnowledgeConcept.id == concept_id)
    )
    concept = result.scalar_one_or_none()
    if not concept:
        raise HTTPException(status_code=404, detail=f"Concept '{concept_id}' not found.")

    # Fetch version history
    history_result = await db.execute(
        select(ArtifactVersionHistory)
        .where(
            ArtifactVersionHistory.artifact_type == "KNOWLEDGE",
            ArtifactVersionHistory.artifact_id == concept_id,
        )
        .order_by(ArtifactVersionHistory.version.desc())
    )
    history = history_result.scalars().all()

    return {
        "concept_id": concept_id,
        "concept_name": concept.name,
        "current_rank_score": concept.rank_score,
        "last_ranked_at": concept.last_ranked_at,
        "history": history,
    }


@router.post("/concepts", response_model=ConceptResponse, dependencies=[Depends(require_admin)])
async def create_concept(concept: ConceptCreate, db: AsyncSession = Depends(get_db)):
    """Add a new concept to the knowledge base (admin only)."""
    existing = await db.execute(
        select(KnowledgeConcept).where(KnowledgeConcept.name == concept.name)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"Concept '{concept.name}' already exists.")

    db_concept = KnowledgeConcept(**concept.model_dump(), version=1)
    db.add(db_concept)

    # Log version 1 to artifact history
    await db.flush()
    version_record = ArtifactVersionHistory(
        artifact_type="KNOWLEDGE",
        artifact_id=db_concept.id,
        artifact_name=concept.name,
        version=1,
        content_snapshot=concept.model_dump(),
        change_reason="Initial concept creation",
        is_current=True,
    )
    db.add(version_record)
    await db.commit()
    await db.refresh(db_concept)
    return db_concept


@router.put("/concepts/{concept_id}", response_model=ConceptResponse, dependencies=[Depends(require_admin)])
async def update_concept(
    concept_id: str,
    update_data: ConceptCreate,
    change_reason: str = Query(..., description="Reason for update"),
    db: AsyncSession = Depends(get_db)
):
    """Update a concept — creates a new version record."""
    result = await db.execute(
        select(KnowledgeConcept).where(KnowledgeConcept.id == concept_id)
    )
    concept = result.scalar_one_or_none()
    if not concept:
        raise HTTPException(status_code=404, detail=f"Concept '{concept_id}' not found.")

    # Mark all previous versions as not current
    await db.execute(
        update(ArtifactVersionHistory)
        .where(
            ArtifactVersionHistory.artifact_type == "KNOWLEDGE",
            ArtifactVersionHistory.artifact_id == concept_id,
        )
        .values(is_current=False)
    )

    new_version = concept.version + 1
    for field, value in update_data.model_dump().items():
        setattr(concept, field, value)
    concept.version = new_version
    concept.updated_at = datetime.utcnow()

    version_record = ArtifactVersionHistory(
        artifact_type="KNOWLEDGE",
        artifact_id=concept_id,
        artifact_name=concept.name,
        version=new_version,
        content_snapshot=update_data.model_dump(),
        change_reason=change_reason,
        is_current=True,
    )
    db.add(version_record)
    await db.commit()
    await db.refresh(concept)
    return concept
