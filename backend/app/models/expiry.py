"""
AI-QROS — Phase 12 Database Models
Expiry Intelligence: Options expiry calculations, max pain levels, and projected pinning risk.
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


class ExpiryIntelligence(Base):
    __tablename__ = "expiry_intelligence"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    expiry_date: Mapped[str] = mapped_column(String(20), nullable=False)

    max_pain: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pcr_oi: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    total_call_oi: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_put_oi: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    net_gex: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Net Gamma Exposure

    predicted_pin_strike: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    pinning_probability: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("trade_date", "symbol", "expiry_date", name="uq_expiry_intel"),
        Index("ix_exp_trade_date", "trade_date"),
        Index("ix_exp_symbol", "symbol"),
        Index("ix_exp_expiry_date", "expiry_date"),
    )
