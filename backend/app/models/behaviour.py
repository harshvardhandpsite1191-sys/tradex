"""
AI-QROS — Phase 5 Database Models
Behaviour Store: Detected market behaviours, patterns, and regime classifications.
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
# DETECTED BEHAVIOUR
# One row per detected behaviour event.
# A single trading day can have multiple behaviours detected.
# ═══════════════════════════════════════════════════════════════
class DetectedBehaviour(Base):
    __tablename__ = "detected_behaviours"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)

    behaviour_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # Types: MARKET_REGIME, LIQUIDITY_SWEEP, STOP_HUNT, OI_BUILDUP,
    #        VOLUME_ANOMALY, GAP_BEHAVIOUR, PREMIUM_DECAY, IV_CRUSH,
    #        FVG_DETECTION, ORDER_BLOCK, CHOCH, BOS, INSTITUTIONAL_FLOW,
    #        EXPIRY_PINNING, GAMMA_SQUEEZE, SHORT_COVERING, LONG_UNWINDING

    category: Mapped[str] = mapped_column(String(50), nullable=False)
    # Categories: STRUCTURE, LIQUIDITY, INSTITUTIONAL, OPTIONS, VOLUME, REGIME

    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 0.0 to 1.0 confidence score

    direction: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # direction: "bullish", "bearish", "neutral"

    description: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Arbitrary detail payload per behaviour type

    detected_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_db_trade_date", "trade_date"),
        Index("ix_db_symbol", "symbol"),
        Index("ix_db_behaviour_type", "behaviour_type"),
        Index("ix_db_category", "category"),
        Index("ix_db_confidence", "confidence"),
        Index("ix_db_direction", "direction"),
    )


# ═══════════════════════════════════════════════════════════════
# MARKET REGIME
# One row per symbol per trade_date — the classified regime state.
# ═══════════════════════════════════════════════════════════════
class MarketRegime(Base):
    __tablename__ = "market_regimes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)

    regime: Mapped[str] = mapped_column(String(50), nullable=False)
    # regime: "trending_up", "trending_down", "ranging", "volatile", "low_vol_squeeze"

    sub_regime: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # sub_regime: "strong_trend", "weak_trend", "breakout", "mean_revert", "expansion"

    trend_strength: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # ADX-based 0-100

    volatility_state: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    # "low", "normal", "high", "extreme"

    options_regime: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # "iv_expansion", "iv_contraction", "gamma_squeeze", "theta_decay", "neutral"

    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    classified_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("trade_date", "symbol", name="uq_market_regime"),
        Index("ix_mr_trade_date", "trade_date"),
        Index("ix_mr_symbol", "symbol"),
        Index("ix_mr_regime", "regime"),
    )


# ═══════════════════════════════════════════════════════════════
# BEHAVIOUR EXTRACTION LOG
# Tracks every extraction run — timing, counts, errors
# ═══════════════════════════════════════════════════════════════
class BehaviourExtractionLog(Base):
    __tablename__ = "behaviour_extraction_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    behaviours_detected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    categories_detected: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(50), nullable=False, default="scheduler")

    __table_args__ = (
        Index("ix_bel_symbol", "symbol"),
        Index("ix_bel_trade_date", "trade_date"),
        Index("ix_bel_status", "status"),
    )
