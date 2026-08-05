"""
AI-QROS — Phase 0 Database Models
Governance Tables: Rule Registry, Feature Registry, Model Registry,
Version Management (7 artifact types), System Logs
"""

import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    String, Text, Integer, Float, Boolean, DateTime,
    JSON, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID as PG_UUID, JSONB
from app.db.database import Base


def generate_uuid():
    return str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════
# RULE REGISTRY
# Stores all operational rules and thresholds (Phase 0, Phase 17)
# ═══════════════════════════════════════════════════════════════
class RuleRegistry(Base):
    __tablename__ = "rule_registry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    rule_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    # Categories: TRADE_QUALITY, HYPOTHESIS_REJECTION, RANKING, LEARNING, SYSTEM
    parameters: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(String(100), nullable=True, default="system")

    # Version history relationship
    versions: Mapped[list["RuleVersion"]] = relationship("RuleVersion", back_populates="rule", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_rule_registry_category", "category"),
        Index("ix_rule_registry_is_active", "is_active"),
    )


class RuleVersion(Base):
    __tablename__ = "rule_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    rule_id: Mapped[str] = mapped_column(String(36), ForeignKey("rule_registry.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parameters_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(String(100), nullable=True, default="system")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    rule: Mapped["RuleRegistry"] = relationship("RuleRegistry", back_populates="versions")

    __table_args__ = (
        Index("ix_rule_versions_rule_id", "rule_id"),
        Index("ix_rule_versions_version", "version"),
    )


# ═══════════════════════════════════════════════════════════════
# FEATURE REGISTRY
# Tracks all 500-1000+ features across 13 categories (Phase 0, Phase 4)
# ═══════════════════════════════════════════════════════════════
class FeatureRegistry(Base):
    __tablename__ = "feature_registry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    feature_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    # Categories: PRICE, TREND, MOMENTUM, LIQUIDITY, OPTIONS, GREEKS,
    #             VOLUME, MACRO, INSTITUTIONAL, EXPIRY, OPENING, PREMIUM_BEHAVIOUR, VOLATILITY
    description: Mapped[str] = mapped_column(Text, nullable=True)
    computation_logic: Mapped[str] = mapped_column(Text, nullable=True)  # Python function reference
    data_type: Mapped[str] = mapped_column(String(50), nullable=False, default="float")
    impact_weight: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Impact weight used for Macro features (e.g., S&P500 = 0.375 for 35-40% range)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    versions: Mapped[list["FeatureVersion"]] = relationship("FeatureVersion", back_populates="feature", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_feature_registry_category", "category"),
        Index("ix_feature_registry_is_active", "is_active"),
    )


class FeatureVersion(Base):
    __tablename__ = "feature_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    feature_id: Mapped[str] = mapped_column(String(36), ForeignKey("feature_registry.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    computation_logic_snapshot: Mapped[str] = mapped_column(Text, nullable=True)
    change_reason: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    feature: Mapped["FeatureRegistry"] = relationship("FeatureRegistry", back_populates="versions")

    __table_args__ = (
        Index("ix_feature_versions_feature_id", "feature_id"),
    )


# ═══════════════════════════════════════════════════════════════
# MODEL REGISTRY
# Tracks all ML model versions (Phase 0, Phase 16)
# Primary registry via MLflow — this table stores metadata + links
# ═══════════════════════════════════════════════════════════════
class ModelRegistry(Base):
    __tablename__ = "model_registry"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # Types: XGBOOST, LIGHTGBM, CATBOOST, RANDOM_FOREST
    purpose: Mapped[str] = mapped_column(String(255), nullable=True)
    # e.g., "Phase 16 — AI Decision Engine — Intraday Direction"
    mlflow_run_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    mlflow_model_uri: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    feature_registry_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    training_data_window_start: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    training_data_window_end: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    metrics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # e.g., {"accuracy": 0.72, "f1": 0.68, "auc": 0.76}
    stage: Mapped[str] = mapped_column(String(50), nullable=False, default="development")
    # Stages: development, staging, production, archived
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    promoted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    promoted_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    versions: Mapped[list["ModelVersion"]] = relationship("ModelVersion", back_populates="model", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_model_registry_model_type", "model_type"),
        Index("ix_model_registry_stage", "stage"),
        Index("ix_model_registry_is_active", "is_active"),
    )


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    model_id: Mapped[str] = mapped_column(String(36), ForeignKey("model_registry.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    mlflow_run_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    metrics_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    change_reason: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    model: Mapped["ModelRegistry"] = relationship("ModelRegistry", back_populates="versions")

    __table_args__ = (
        Index("ix_model_versions_model_id", "model_id"),
    )


# ═══════════════════════════════════════════════════════════════
# VERSION MANAGEMENT — Remaining 4 artifact types
# (Features + Models + Rules handled above via their own tables)
# Remaining: Research, Scenarios, Strategies, Knowledge
# ═══════════════════════════════════════════════════════════════
class ArtifactVersionHistory(Base):
    """
    Generic version history table for: Research, Scenarios, Strategies, Knowledge.
    Feature, Model, and Rule versions are tracked in their dedicated tables above.
    """
    __tablename__ = "artifact_version_history"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # Types: RESEARCH, SCENARIO, STRATEGY, KNOWLEDGE
    artifact_id: Mapped[str] = mapped_column(String(36), nullable=False)
    artifact_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    change_reason: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    created_by: Mapped[str] = mapped_column(String(100), nullable=True, default="system")
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("ix_artifact_version_artifact_type", "artifact_type"),
        Index("ix_artifact_version_artifact_id", "artifact_id"),
        Index("ix_artifact_version_is_current", "is_current"),
    )


# ═══════════════════════════════════════════════════════════════
# SYSTEM LOGS
# Every system action is logged here (Phase 0 — Logging)
# ═══════════════════════════════════════════════════════════════
class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    # Levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
    source: Mapped[str] = mapped_column(String(255), nullable=False)
    # Source: router name, celery task name, phase name
    phase: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # Phase: PHASE_0, PHASE_1, ... PHASE_24
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)

    __table_args__ = (
        Index("ix_system_logs_timestamp", "timestamp"),
        Index("ix_system_logs_level", "level"),
        Index("ix_system_logs_phase", "phase"),
        Index("ix_system_logs_event_type", "event_type"),
    )


# ═══════════════════════════════════════════════════════════════
# USER (Authentication — Phase 0)
# ═══════════════════════════════════════════════════════════════
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    username: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), nullable=False, default="viewer")
    # Roles: admin, researcher, viewer
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_users_username", "username"),
        Index("ix_users_email", "email"),
    )
