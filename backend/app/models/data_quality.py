"""
AI-QROS — Phase 3 Database Models
Data Quality Tables: Quality Reports and Individual Check Results
"""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Text, Integer, Float, DateTime, Index, ForeignKey
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from app.db.database import Base


def generate_uuid():
    return str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════
# DATA QUALITY REPORT
# One report per source per check run. Holds the overall score.
# ═══════════════════════════════════════════════════════════════
class DataQualityReport(Base):
    __tablename__ = "data_quality_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    # source: "NSE_BHAVCOPY", "YFINANCE", "ANGEL_ONE", "ALL"

    overall_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # 0-100 weighted average of individual check scores

    total_checks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checks_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checks_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    checks_warning: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    total_rows_scanned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_issues_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    run_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    triggered_by: Mapped[str] = mapped_column(String(50), nullable=False, default="scheduler")
    # triggered_by: "scheduler", "manual", "post_ingestion"

    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relationship to individual checks
    checks: Mapped[list["DataQualityCheck"]] = relationship(
        "DataQualityCheck", back_populates="report", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_dq_reports_source", "source"),
        Index("ix_dq_reports_run_at", "run_at"),
        Index("ix_dq_reports_overall_score", "overall_score"),
    )


# ═══════════════════════════════════════════════════════════════
# DATA QUALITY CHECK
# Individual check result within a report.
# Each check tests one aspect of data quality.
# ═══════════════════════════════════════════════════════════════
class DataQualityCheck(Base):
    __tablename__ = "data_quality_checks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    report_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("data_quality_reports.id", ondelete="CASCADE"), nullable=False
    )

    check_name: Mapped[str] = mapped_column(String(100), nullable=False)
    # e.g. "completeness_null_check", "consistency_ohlc_logic", "freshness_staleness"
    check_category: Mapped[str] = mapped_column(String(50), nullable=False)
    # category: "completeness", "freshness", "consistency", "duplicates", "outliers", "gaps"

    status: Mapped[str] = mapped_column(String(20), nullable=False)
    # status: "passed", "failed", "warning"
    score: Mapped[float] = mapped_column(Float, nullable=False, default=100.0)
    # 0-100 score for this specific check

    rows_scanned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    issues_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # details may include: affected_columns, sample_bad_rows, thresholds_used, etc.

    report: Mapped["DataQualityReport"] = relationship(
        "DataQualityReport", back_populates="checks"
    )

    __table_args__ = (
        Index("ix_dq_checks_report_id", "report_id"),
        Index("ix_dq_checks_category", "check_category"),
        Index("ix_dq_checks_status", "status"),
    )
