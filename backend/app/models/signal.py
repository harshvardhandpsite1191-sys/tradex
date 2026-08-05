"""
AI-QROS — Phase 15 Database Models
Signal Generation: Consolidated directional trading signals, confidence scores, and contributing factors.
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


class TradeSignal(Base):
    __tablename__ = "trade_signals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)

    signal_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # Types: BUY_CALL, BUY_PUT, SHORT_STRADDLE, SHORT_STRANGLE, SPREAD, NO_TRADE

    direction: Mapped[str] = mapped_column(String(20), nullable=False)
    # direction: bullish, bearish, neutral

    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 0.0 to 1.0

    contributing_factors: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Lists outputs from Phase 9-14 that drove this decision
    
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("trade_date", "symbol", name="uq_trade_signal"),
        Index("ix_sig_trade_date", "trade_date"),
        Index("ix_sig_symbol", "symbol"),
        Index("ix_sig_type", "signal_type"),
    )
