"""
AI-QROS — Phase 6-9 Database Models
Research Pipeline: Hypotheses, Test Results, Verified Findings, Research Synthesis
"""

import uuid
from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    String, Text, Integer, Float, DateTime, Date,
    Boolean, UniqueConstraint, Index, ForeignKey
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.db.database import Base


def generate_uuid():
    return str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════
# RESEARCH HYPOTHESIS (Phase 6)
# Generated from detected behaviours, features, and market conditions.
# Each hypothesis is a testable statement about market behaviour.
# ═══════════════════════════════════════════════════════════════
class ResearchHypothesis(Base):
    __tablename__ = "research_hypotheses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    hypothesis_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    # hypothesis_id: "HYP-NIFTY-REGIME-001", "HYP-BANKNIFTY-OI-042"

    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    # Categories: REGIME, STRUCTURE, LIQUIDITY, OPTIONS, VOLUME, INSTITUTIONAL,
    #             EXPIRY, OPENING, MACRO, PREMIUM, CROSS_ASSET

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # The testable condition
    condition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # e.g. {"when": "pcr_oi > 1.3 AND adx > 25", "then": "next_day_return > 0",
    #        "features_used": ["pcr_oi", "adx_14"], "lookback_days": 252}

    expected_outcome: Mapped[str] = mapped_column(Text, nullable=False)
    # e.g. "NIFTY rises next day with >60% probability"

    source_behaviour: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    # The behaviour type that triggered this hypothesis
    source_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="generated")
    # status: "generated", "testing", "verified", "rejected", "archived"

    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    # 1 (highest) to 10 (lowest)

    confidence_prior: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Prior confidence before testing (0-1)

    generated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    generated_by: Mapped[str] = mapped_column(String(50), nullable=False, default="system")
    # "system", "llm", "manual"

    tags: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # e.g. {"expiry_related": true, "regime": "trending_up"}

    __table_args__ = (
        Index("ix_rh_symbol", "symbol"),
        Index("ix_rh_category", "category"),
        Index("ix_rh_status", "status"),
        Index("ix_rh_priority", "priority"),
        Index("ix_rh_generated_at", "generated_at"),
    )


# ═══════════════════════════════════════════════════════════════
# HYPOTHESIS TEST RESULT (Phase 7)
# Statistical test results for each hypothesis.
# ═══════════════════════════════════════════════════════════════
class HypothesisTestResult(Base):
    __tablename__ = "hypothesis_test_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    hypothesis_id: Mapped[str] = mapped_column(
        String(50), ForeignKey("research_hypotheses.hypothesis_id"), nullable=False
    )

    test_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # test_type: "win_rate", "t_test", "chi_square", "mann_whitney",
    #            "bootstrap", "bayesian", "permutation"

    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    test_period_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    test_period_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Results
    win_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_return: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    t_statistic: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    effect_size: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_interval: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # e.g. {"lower": 0.52, "upper": 0.68, "level": 0.95}

    is_significant: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verdict: Mapped[str] = mapped_column(String(30), nullable=False, default="inconclusive")
    # verdict: "supported", "rejected", "inconclusive", "weak_support"

    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    tested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_htr_hypothesis_id", "hypothesis_id"),
        Index("ix_htr_verdict", "verdict"),
        Index("ix_htr_is_significant", "is_significant"),
    )


# ═══════════════════════════════════════════════════════════════
# RESEARCH FINDING (Phase 8-9)
# Verified, actionable research findings that feed into the AI.
# ═══════════════════════════════════════════════════════════════
class ResearchFinding(Base):
    __tablename__ = "research_findings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    finding_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    # finding_id: "RES-NIFTY-001"

    hypothesis_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    actionable_insight: Mapped[str] = mapped_column(Text, nullable=False)
    # e.g. "When PCR > 1.3 and ADX > 25, buy NIFTY CE at open"

    # Verified metrics
    win_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    avg_return: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 0-1 overall confidence

    # Applicability conditions
    applicable_regimes: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # e.g. {"regimes": ["trending_up"], "volatility": ["normal", "high"]}
    applicable_conditions: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active")
    # status: "active", "deprecated", "under_review"

    verified_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_validated: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_rf_symbol", "symbol"),
        Index("ix_rf_category", "category"),
        Index("ix_rf_status", "status"),
        Index("ix_rf_confidence_score", "confidence_score"),
    )


# ═══════════════════════════════════════════════════════════════
# RESEARCH PIPELINE LOG
# Tracks each research pipeline run
# ═══════════════════════════════════════════════════════════════
class ResearchPipelineLog(Base):
    __tablename__ = "research_pipeline_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    pipeline_phase: Mapped[str] = mapped_column(String(30), nullable=False)
    # phase: "hypothesis_generation", "hypothesis_testing",
    #        "historical_verification", "research_synthesis"

    symbol: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    trade_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    items_processed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    items_generated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(50), nullable=False, default="scheduler")
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_rpl_pipeline_phase", "pipeline_phase"),
        Index("ix_rpl_status", "status"),
        Index("ix_rpl_started_at", "started_at"),
    )
