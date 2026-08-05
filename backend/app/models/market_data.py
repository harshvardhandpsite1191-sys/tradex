"""
AI-QROS — Phase 2 Database Models
Market Data Tables: OHLCV Candles, Option Settlements,
Global Market Data, Data Ingestion Logs
"""

import uuid
from datetime import datetime, date
from typing import Optional
from sqlalchemy import (
    String, Text, Integer, Float, Boolean, DateTime, Date,
    UniqueConstraint, Index
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import JSONB
from app.db.database import Base


def generate_uuid():
    return str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════
# OHLCV CANDLES
# Historical and intraday candle data from Angel One SmartAPI
# Intervals: 1min, 5min, 15min, 30min, 60min, 1day
# ═══════════════════════════════════════════════════════════════
class OHLCVCandle(Base):
    __tablename__ = "ohlcv_candles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    symbol_token: Mapped[str] = mapped_column(String(20), nullable=False)
    exchange: Mapped[str] = mapped_column(String(10), nullable=False)
    # exchange: "NSE" for index, "NFO" for F&O
    interval: Mapped[str] = mapped_column(String(10), nullable=False)
    # interval: "1min", "5min", "15min", "30min", "60min", "1day"

    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    volume: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    data_source: Mapped[str] = mapped_column(String(50), nullable=False, default="ANGEL_ONE")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("timestamp", "symbol_token", "exchange", "interval",
                         name="uq_ohlcv_candle"),
        Index("ix_ohlcv_candles_timestamp", "timestamp"),
        Index("ix_ohlcv_candles_symbol_token", "symbol_token"),
        Index("ix_ohlcv_candles_interval", "interval"),
        Index("ix_ohlcv_candles_exchange", "exchange"),
    )


# ═══════════════════════════════════════════════════════════════
# OPTION SETTLEMENTS
# NSE F&O Bhavcopy — daily settlement data for NIFTY/SENSEX/BANKNIFTY
# options. Covers ALL expired contracts going back 5+ years.
# ═══════════════════════════════════════════════════════════════
class OptionSettlement(Base):
    __tablename__ = "option_settlements"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    underlying: Mapped[str] = mapped_column(String(20), nullable=False)
    # underlying: "NIFTY", "BANKNIFTY", "SENSEX"
    expiry_date: Mapped[str] = mapped_column(String(20), nullable=False)
    # Stored as string because NSE format varies (e.g. "29-Feb-2024")
    strike: Mapped[float] = mapped_column(Float, nullable=False)
    option_type: Mapped[str] = mapped_column(String(5), nullable=False)
    # option_type: "CE" or "PE"

    open: Mapped[float] = mapped_column(Float, nullable=False)
    high: Mapped[float] = mapped_column(Float, nullable=False)
    low: Mapped[float] = mapped_column(Float, nullable=False)
    close: Mapped[float] = mapped_column(Float, nullable=False)
    settle_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    contracts: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    value_lakh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    oi: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    change_oi: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    data_source: Mapped[str] = mapped_column(String(50), nullable=False, default="NSE_BHAVCOPY")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("trade_date", "underlying", "expiry_date", "strike", "option_type",
                         name="uq_option_settlement"),
        Index("ix_option_settlements_trade_date", "trade_date"),
        Index("ix_option_settlements_underlying", "underlying"),
        Index("ix_option_settlements_expiry_date", "expiry_date"),
        Index("ix_option_settlements_strike", "strike"),
        Index("ix_option_settlements_option_type", "option_type"),
    )


# ═══════════════════════════════════════════════════════════════
# GLOBAL MARKET DATA
# Daily OHLCV for 16 global macro factors from yfinance
# Used as MACRO features for NIFTY/SENSEX prediction
# ═══════════════════════════════════════════════════════════════
class GlobalMarketData(Base):
    __tablename__ = "global_market_data"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    factor_name: Mapped[str] = mapped_column(String(50), nullable=False)
    # factor_name: SP500, NASDAQ, DOW, NIKKEI, HANGSENG, SHANGHAI, KOSPI,
    #              GIFT_NIFTY, FTSE, DAX, CAC40, BRENT_CRUDE, GOLD,
    #              USD_INR, US10Y_YIELD, US_VIX
    ticker: Mapped[str] = mapped_column(String(30), nullable=False)
    # yfinance ticker symbol (e.g. "^GSPC" for S&P 500)

    open: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    high: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    low: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    close: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    volume: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    data_source: Mapped[str] = mapped_column(String(50), nullable=False, default="YFINANCE")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("trade_date", "factor_name",
                         name="uq_global_market_data"),
        Index("ix_global_market_data_trade_date", "trade_date"),
        Index("ix_global_market_data_factor_name", "factor_name"),
    )


# ═══════════════════════════════════════════════════════════════
# DATA INGESTION LOG
# Tracks every data fetch job — status, rows, duration, errors
# Used by /data/ingestion-logs and /data/status endpoints
# ═══════════════════════════════════════════════════════════════
class DataIngestionLog(Base):
    __tablename__ = "data_ingestion_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    # source: "NSE_BHAVCOPY", "YFINANCE", "ANGEL_ONE"
    job_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # job_type: "daily_fetch", "backfill", "manual_trigger"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    # status: "pending", "running", "success", "failed"

    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    rows_fetched: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    rows_inserted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)
    rows_skipped: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, default=0)

    date_range_start: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    date_range_end: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_data_ingestion_logs_source", "source"),
        Index("ix_data_ingestion_logs_status", "status"),
        Index("ix_data_ingestion_logs_started_at", "started_at"),
    )
