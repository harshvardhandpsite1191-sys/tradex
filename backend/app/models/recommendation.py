"""
AI-QROS — Phase 19 Database Models
Trade Recommendations: Executable trade proposals, exact strikes, targets, and stops.
"""

import uuid
from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    String, Text, Float, DateTime, Date, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.db.database import Base


def generate_uuid():
    return str(uuid.uuid4())


class TradeRecommendation(Base):
    __tablename__ = "trade_recommendations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)

    strategy_name: Mapped[str] = mapped_column(String(50), nullable=False)
    # e.g., BULL_CALL_SPREAD, IRON_CONDOR, LONG_CALL
    
    legs_detail: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Exact strikes, expirations, prices, SL/TP rules

    stop_loss_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    target_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    risk_reward_ratio: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    allocation_weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    # Sizing multiplier from Phase 18

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # Status: pending, active, completed, cancelled
    
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("trade_date", "symbol", "strategy_name", name="uq_trade_reco"),
        Index("ix_reco_trade_date", "trade_date"),
        Index("ix_reco_symbol", "symbol"),
    )
