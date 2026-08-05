"""
AI-QROS — Phase 13 Database Models
Scenario Library: Named market scenarios, trigger conditions, and historical edge statistics.
"""

import uuid
from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    String, Text, Float, Integer, DateTime, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.db.database import Base


def generate_uuid():
    return str(uuid.uuid4())


class MarketScenario(Base):
    __tablename__ = "market_scenarios"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    scenario_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    # scenario_id: SCEN-NIFTY-EQH-001

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    # Categories: STRUCTURE, LIQUIDITY, OPTIONS, OPENING, VOLUME, INSTITUTIONAL

    description: Mapped[str] = mapped_column(Text, nullable=False)
    condition_definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Rules to match this scenario, e.g., {"behaviours": ["STOP_HUNT"], "direction": "bullish"}

    # Statistical outcomes
    win_rate_all: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    win_rate_by_regime: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # e.g., {"trending_up": 0.68, "ranging": 0.45}
    
    avg_return: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    is_active: Mapped[bool] = mapped_column(DateTime, nullable=True) # or Boolean. Let's make it standard Mapped[bool]
    
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_scen_id", "scenario_id"),
        Index("ix_scen_category", "category"),
    )
