"""
AI-QROS — Knowledge Base Model
Phase 1: Institutional Research Library
Stores all 104 institutional concepts across 13 categories
"""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Float, Boolean, DateTime, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from app.db.database import Base


def generate_uuid():
    return str(uuid.uuid4())


class KnowledgeConcept(Base):
    """
    Stores every institutional concept the AI has learned about.
    All 104 concepts across 13 categories are seeded here (Phase 1).
    rank_score is updated by Phase 9 (Knowledge Ranking Engine).
    """
    __tablename__ = "knowledge_base"

    # ── Identity ─────────────────────────────────────────────────
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    sub_category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # ── Content ──────────────────────────────────────────────────
    description: Mapped[str] = mapped_column(Text, nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    market_relevance: Mapped[str] = mapped_column(Text, nullable=False)
    # How this concept applies specifically to NIFTY/SENSEX Options
    conditions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # When this concept is applicable — e.g., {"market_state": ["trending"], "session": ["opening"]}

    # ── Ranking (updated by Phase 9) ─────────────────────────────
    rank_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    last_ranked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # ── Versioning ───────────────────────────────────────────────
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    __table_args__ = (
        Index("ix_knowledge_base_category", "category"),
        Index("ix_knowledge_base_name", "name"),
        Index("ix_knowledge_base_rank_score", "rank_score"),
        Index("ix_knowledge_base_is_active", "is_active"),
    )
