"""
AI-QROS — Phase 4 Database Models
Feature Store: Computed feature values for ML training and inference.
Stores pre-computed features per symbol per trading day.
"""

import uuid
from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    String, Text, Integer, Float, DateTime, Date,
    UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.db.database import Base


def generate_uuid():
    return str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════
# COMPUTED FEATURE STORE
# One row per symbol per trade_date. The `features` JSONB column
# holds all 500-1000+ feature values as a flat dict.
# This avoids creating 1000 columns — JSONB is queryable and fast.
# ═══════════════════════════════════════════════════════════════
class ComputedFeatureStore(Base):
    __tablename__ = "computed_feature_store"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    # symbol: "NIFTY", "BANKNIFTY", "SENSEX"

    feature_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    features: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # Features dict: {"rsi_14": 65.2, "macd_signal": 1.23, "iv_rank": 72.5, ...}

    computation_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    computed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    __table_args__ = (
        UniqueConstraint("trade_date", "symbol", "computation_version",
                         name="uq_computed_feature"),
        Index("ix_cfs_trade_date", "trade_date"),
        Index("ix_cfs_symbol", "symbol"),
    )


# ═══════════════════════════════════════════════════════════════
# FEATURE COMPUTATION LOG
# Tracks every feature computation run — timing, counts, errors
# ═══════════════════════════════════════════════════════════════
class FeatureComputationLog(Base):
    __tablename__ = "feature_computation_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # status: "pending", "running", "success", "failed"
    features_computed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    categories_computed: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # {category: count} e.g. {"PRICE": 12, "MOMENTUM": 25, ...}

    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(50), nullable=False, default="scheduler")

    __table_args__ = (
        Index("ix_fcl_symbol", "symbol"),
        Index("ix_fcl_trade_date", "trade_date"),
        Index("ix_fcl_status", "status"),
    )
