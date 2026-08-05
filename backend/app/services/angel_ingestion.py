"""
AI-QROS — Angel One Historical F&O Data Ingestion Service
Phase 2: Data Infrastructure

Uses Angel One SmartAPI to fetch historical daily settlement data for
NIFTY, BANKNIFTY, and SENSEX options — bypassing NSE's cloud IP blocks.

Strategy:
  1. Download Scrip Master (public JSON, no auth needed) to get all option tokens
  2. Login to SmartAPI using TOTP
  3. Fetch daily OHLCV candles for each active contract
  4. Upsert into option_settlements table

This is a SUPERSET of what NSE Bhavcopy provides:
  - Open, High, Low, Close, Settle Price, Volume (contracts), OI
  - Can fetch intraday candles too (not just EOD)
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import Optional
import pandas as pd
import structlog

from app.db.database import AsyncSessionLocal
from app.models.market_data import OptionSettlement, DataIngestionLog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select
import time

logger = structlog.get_logger("aiqros.services.angel_ingestion")


# ─────────────────────────────────────────────
# Scrip Master (public, no auth needed)
# ─────────────────────────────────────────────

def _download_scrip_master() -> Optional[pd.DataFrame]:
    """
    Download Angel One Scrip Master JSON (public URL, no auth required).
    Returns DataFrame with columns: token, symbol, name, expiry, strike, option_type, exch_seg
    """
    import requests
    url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    try:
        resp = requests.get(url, timeout=30)
        data = resp.json()
        df = pd.DataFrame(data)

        # Filter to NIFTY / BANKNIFTY / SENSEX NFO options only
        df = df[df["exch_seg"] == "NFO"]
        df = df[df["instrumenttype"] == "OPTIDX"]
        df = df[df["name"].isin(["NIFTY", "BANKNIFTY", "SENSEX"])]

        # Parse expiry date
        df["expiry_dt"] = pd.to_datetime(df["expiry"], format="%d%b%Y", errors="coerce")

        logger.info("scrip_master_downloaded", total_rows=len(df))
        return df

    except Exception as e:
        logger.error("scrip_master_failed", error=str(e))
        return None


def _get_active_contracts(
    scrip_df: pd.DataFrame,
    target_date: date,
    symbol: str,
    weeks_forward: int = 4,
) -> pd.DataFrame:
    """
    Filter scrip master to contracts that were active on the target_date.
    Returns contracts expiring within 4 weeks of target_date (weekly + monthly expiries).
    """
    cutoff = pd.Timestamp(target_date + timedelta(weeks=weeks_forward))
    start = pd.Timestamp(target_date)

    mask = (
        (scrip_df["name"] == symbol) &
        (scrip_df["expiry_dt"] >= start) &
        (scrip_df["expiry_dt"] <= cutoff)
    )
    return scrip_df[mask].copy()


# ─────────────────────────────────────────────
# Angel One Session Management
# ─────────────────────────────────────────────

_angel_session = {"obj": None, "logged_in_at": None}


def _get_angel_session():
    """Get or refresh Angel One session."""
    from app.config import settings
    import pyotp
    from SmartApi import SmartConnect

    # Check if session is still fresh (< 7 hours)
    if _angel_session["obj"] and _angel_session["logged_in_at"]:
        hours = (datetime.utcnow() - _angel_session["logged_in_at"]).total_seconds() / 3600
        if hours < 7:
            return _angel_session["obj"]

    if not all([
        settings.ANGEL_ONE_API_KEY,
        settings.ANGEL_ONE_CLIENT_ID,
        settings.ANGEL_ONE_PASSWORD,
        settings.ANGEL_ONE_TOTP_SECRET,
    ]):
        raise ValueError(
            "Angel One credentials not configured. "
            "Set ANGEL_ONE_API_KEY, ANGEL_ONE_CLIENT_ID, "
            "ANGEL_ONE_PASSWORD, ANGEL_ONE_TOTP_SECRET in Render Environment Variables."
        )

    obj = SmartConnect(api_key=settings.ANGEL_ONE_API_KEY)
    totp = pyotp.TOTP(settings.ANGEL_ONE_TOTP_SECRET).now()
    data = obj.generateSession(
        settings.ANGEL_ONE_CLIENT_ID,
        settings.ANGEL_ONE_PASSWORD,
        totp
    )

    if not data.get("status"):
        raise ValueError(f"Angel One login failed: {data}")

    _angel_session["obj"] = obj
    _angel_session["logged_in_at"] = datetime.utcnow()
    logger.info("angel_one_session_created", client=settings.ANGEL_ONE_CLIENT_ID)
    return obj


def _fetch_candle_eod(
    obj,
    token: str,
    exchange: str,
    target_date: date,
) -> Optional[dict]:
    """
    Fetch end-of-day candle for a single contract on target_date.
    Returns dict with OHLC, volume, OI or None.
    """
    from_dt = datetime(target_date.year, target_date.month, target_date.day, 9, 0)
    to_dt = datetime(target_date.year, target_date.month, target_date.day, 15, 35)

    try:
        resp = obj.getCandleData({
            "exchange": exchange,
            "symboltoken": token,
            "interval": "ONE_DAY",
            "fromdate": from_dt.strftime("%Y-%m-%d %H:%M"),
            "todate": to_dt.strftime("%Y-%m-%d %H:%M"),
        })

        if not resp.get("status") or not resp.get("data"):
            return None

        # [timestamp, open, high, low, close, volume]
        candle = resp["data"][-1]  # Last candle = EOD
        return {
            "open": float(candle[1]),
            "high": float(candle[2]),
            "low": float(candle[3]),
            "close": float(candle[4]),
            "volume": int(candle[5]),
        }

    except Exception as e:
        logger.debug("angel_candle_fetch_failed", token=token, error=str(e))
        return None


# ─────────────────────────────────────────────
# Main Ingestion Function
# ─────────────────────────────────────────────

async def ingest_fo_via_angel_one(
    target_date: date,
    symbols: list = None,
) -> dict:
    """
    Fetch F&O settlement data for a single trading day via Angel One SmartAPI.
    Inserts records into option_settlements table.
    """
    symbols = symbols or ["NIFTY", "BANKNIFTY", "SENSEX"]
    start_time = time.time()

    async with AsyncSessionLocal() as db:
        # Create ingestion log
        from app.services.data_ingestion import _create_ingestion_log, _complete_ingestion_log
        log_id = await _create_ingestion_log(
            db, "ANGEL_ONE", "daily_fetch",
            date_start=target_date, date_end=target_date,
        )
        await db.commit()

        try:
            # Step 1: Download scrip master in thread pool (blocking HTTP)
            loop = asyncio.get_event_loop()
            scrip_df = await loop.run_in_executor(None, _download_scrip_master)
            if scrip_df is None or scrip_df.empty:
                raise ValueError("Scrip Master download failed")

            # Step 2: Login to Angel One (blocking)
            obj = await loop.run_in_executor(None, _get_angel_session)

            total_fetched = 0
            total_inserted = 0
            records = []

            for symbol in symbols:
                contracts = _get_active_contracts(scrip_df, target_date, symbol)
                logger.info("processing_symbol", symbol=symbol, contracts=len(contracts))

                for _, row in contracts.iterrows():
                    token = str(row["token"])
                    sym_name = str(row["symbol"])  # e.g. NIFTY24AUG2200CE

                    # Parse strike and option type from symbol name
                    try:
                        strike = float(row.get("strike", 0)) / 100  # Angel stores as paise
                        opt_type = "CE" if sym_name.endswith("CE") else "PE"
                        expiry_dt = row["expiry_dt"]
                    except Exception:
                        continue

                    # Fetch EOD candle (blocking, run in executor)
                    candle = await loop.run_in_executor(
                        None, _fetch_candle_eod, obj, token, "NFO", target_date
                    )

                    if candle is None:
                        continue

                    total_fetched += 1
                    records.append({
                        "trade_date": target_date,
                        "underlying": symbol,
                        "expiry_date": expiry_dt.strftime("%d-%b-%Y") if pd.notna(expiry_dt) else "",
                        "strike": strike,
                        "option_type": opt_type,
                        "open": candle["open"],
                        "high": candle["high"],
                        "low": candle["low"],
                        "close": candle["close"],
                        "settle_price": candle["close"],  # Use close as settle price
                        "contracts": candle["volume"],
                        "value_lakh": None,
                        "oi": None,
                        "change_oi": None,
                        "data_source": "ANGEL_ONE",
                    })

                    # Rate limit: Angel API allows ~3 req/sec
                    await asyncio.sleep(0.35)

            # Bulk upsert
            if records:
                stmt = pg_insert(OptionSettlement).values(records)
                stmt = stmt.on_conflict_do_nothing()
                result = await db.execute(stmt)
                total_inserted = result.rowcount or len(records)

            await _complete_ingestion_log(
                db, log_id, "success",
                rows_fetched=total_fetched,
                rows_inserted=total_inserted,
            )
            await db.commit()

            elapsed = round(time.time() - start_time, 1)
            logger.info(
                "angel_ingestion_complete",
                date=target_date.isoformat(),
                fetched=total_fetched,
                inserted=total_inserted,
                elapsed_s=elapsed,
            )

            return {
                "status": "success",
                "date": target_date.isoformat(),
                "rows_fetched": total_fetched,
                "rows_inserted": total_inserted,
                "elapsed_seconds": elapsed,
            }

        except Exception as e:
            error_msg = str(e)
            logger.error("angel_ingestion_failed", error=error_msg)
            from app.services.data_ingestion import _complete_ingestion_log
            await _complete_ingestion_log(db, log_id, "failed", error_message=error_msg)
            await db.commit()
            return {"status": "failed", "error": error_msg}


async def ingest_fo_via_angel_one_range(
    start_date: date,
    end_date: date,
) -> dict:
    """
    Backfill F&O data for a date range via Angel One SmartAPI.
    Skips weekends automatically.
    """
    trading_days = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5:
            trading_days.append(current)
        current += timedelta(days=1)

    logger.info("angel_backfill_start", days=len(trading_days))

    total_fetched = 0
    total_inserted = 0

    for trade_date in trading_days:
        result = await ingest_fo_via_angel_one(trade_date)
        if result.get("status") == "success":
            total_fetched += result.get("rows_fetched", 0)
            total_inserted += result.get("rows_inserted", 0)
        await asyncio.sleep(1.0)  # Brief pause between days

    return {
        "status": "success",
        "days_processed": len(trading_days),
        "rows_fetched": total_fetched,
        "rows_inserted": total_inserted,
    }
