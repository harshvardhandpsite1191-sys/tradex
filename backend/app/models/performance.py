"""
AI-QROS — Phase 21 Database Models
Performance Tracking: Strategy backtest P&L logs, portfolio stats, and trade outcomes.
"""

import uuid
from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    String, Float, DateTime, Date, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.db.database import Base


def generate_uuid():
    return str(uuid.uuid4())


class TradePerformanceLog(Base):
    __tablename__ = "trade_performance_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)

    recommendation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("trade_recommendations.id"), nullable=False
    )

    entry_premium: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    exit_premium: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    
    pnl_value: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pnl_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    # outcome: "WIN", "LOSS", "SCRATCH"

    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    logged_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("recommendation_id", name="uq_trade_perf"),
        Index("ix_perf_trade_date", "trade_date"),
        Index("ix_perf_symbol", "symbol"),
        Index("ix_perf_outcome", "outcome"),
    )
