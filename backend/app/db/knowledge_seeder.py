"""
AI-QROS — Knowledge Base Seeder
Phase 1: Institutional Research Library
Seeds all 104 concepts into the knowledge_base table on startup
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from app.models.knowledge import KnowledgeConcept
from app.db.knowledge_seed_data import KNOWLEDGE_CONCEPTS
import structlog

logger = structlog.get_logger("aiqros.seeder.knowledge")


async def seed_knowledge_base(db: AsyncSession):
    """
    Seeds all 104 institutional concepts into the knowledge_base table.
    Only inserts concepts that do not already exist (by name).
    Safe to call on every startup — idempotent.
    """
    # Check how many concepts already exist
    result = await db.execute(select(func.count(KnowledgeConcept.id)))
    existing_count = result.scalar()

    if existing_count >= 104:
        logger.info("knowledge_base_already_seeded", existing=existing_count)
        return

    seeded_count = 0
    for concept_data in KNOWLEDGE_CONCEPTS:
        # Check if this specific concept already exists
        existing = await db.execute(
            select(KnowledgeConcept).where(KnowledgeConcept.name == concept_data["name"])
        )
        if existing.scalar_one_or_none():
            continue

        db_concept = KnowledgeConcept(
            name=concept_data["name"],
            category=concept_data["category"],
            sub_category=concept_data.get("sub_category"),
            description=concept_data["description"],
            definition=concept_data["definition"],
            market_relevance=concept_data["market_relevance"],
            conditions=concept_data.get("conditions"),
            rank_score=None,          # Set by Phase 9 (Knowledge Ranking Engine)
            last_ranked_at=None,      # Set by Phase 9
            version=1,
            is_active=True,
        )
        db.add(db_concept)
        seeded_count += 1

    await db.commit()
    logger.info(
        "knowledge_base_seeded",
        seeded=seeded_count,
        total=existing_count + seeded_count
    )
