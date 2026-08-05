"""
AI-QROS — Phase 11 Database Models
Opening Intelligence: Pre-market forecasts, gaps, global sentiments, and Initial Balance ranges.
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


class OpeningIntelligence(Base):
    __tablename__ = "opening_intelligence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)

    global_sentiment_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Score from -1.0 (very bearish) to +1.0 (very bullish)
    
    gift_nifty_change_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    expected_gap_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    actual_gap_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    opening_bias: Mapped[str] = mapped_column(String(20), nullable=False)
    # "bullish", "bearish", "neutral"

    ib_high_predicted: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ib_low_predicted: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ib_high_actual: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ib_low_actual: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    
    ib_extension_bias: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # "up", "down", "both", "neither"

    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("trade_date", "symbol", name="uq_opening_intel"),
        Index("ix_oi_trade_date", "trade_date"),
        Index("ix_oi_symbol", "symbol"),
    )
