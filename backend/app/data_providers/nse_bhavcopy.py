"""
AI-QROS — NSE Bhavcopy Connector
Phase 2: Data Infrastructure

Downloads NSE F&O Bhavcopy CSV files for historical option chain data.
This is 100% FREE — no authentication required.
Provides ALL expired option contract data going back 5+ years.

NSE publishes F&O bhavcopy daily:
- New format (2024+): BhavCopy_NSE_FO_0_0_0_YYYYMMDD_F_0000.csv.zip
- Old format (pre-2024): fo{DD}{MMM}{YYYY}bhav.csv.zip via nsearchives

Bhavcopy fields:
  INSTRUMENT, SYMBOL, EXPIRY_DT, STRIKE_PR, OPTION_TYP,
  OPEN, HIGH, LOW, CLOSE, SETTLE_PR, CONTRACTS, VAL_IN_LAKH,
  OPEN_INT, CHG_IN_OI, TIMESTAMP
"""

import io
import zipfile
import asyncio
import aiohttp
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Optional
import structlog

logger = structlog.get_logger("aiqros.data.nse_bhavcopy")

# NSE Bhavcopy URL patterns
NSE_NEW_BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/content/fo/"
    "BhavCopy_NSE_FO_0_0_0_{date_str}_F_0000.csv.zip"
)
NSE_OLD_BHAVCOPY_URL = (
    "https://nsearchives.nseindia.com/content/historical/DERIVATIVES/"
    "{year}/{month_abbr}/fo{dd}{month_abbr}{year}bhav.csv.zip"
)

# Unofficial CDN mirrors that are accessible from cloud servers
NSE_CDN_MIRROR_URL = (
    "https://archives.nseindia.com/content/fo/"
    "BhavCopy_NSE_FO_0_0_0_{date_str}_F_0000.csv.zip"
)

MONTH_ABBR = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC"
}

# Headers to mimic browser (NSE blocks plain requests)
NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def _build_url(trade_date: date) -> list[str]:
    """Build all URL variants for a given trade date — try multiple sources."""
    date_str_new = trade_date.strftime("%Y%m%d")
    date_str_dd = trade_date.strftime("%d")
    month_abbr = MONTH_ABBR[trade_date.month]
    year = trade_date.strftime("%Y")

    return [
        # New format (2024+) — primary
        NSE_NEW_BHAVCOPY_URL.format(date_str=date_str_new),
        # CDN mirror — cloud-friendly
        NSE_CDN_MIRROR_URL.format(date_str=date_str_new),
        # Old format (pre-2024)
        NSE_OLD_BHAVCOPY_URL.format(
            year=year, month_abbr=month_abbr, dd=date_str_dd
        ),
    ]


def _fetch_bhavcopy_sync(trade_date: date) -> Optional[pd.DataFrame]:
    """
    Synchronous requests-based fallback for NSE Bhavcopy.
    Uses a persistent session with cookies to bypass NSE's anti-bot measures.
    """
    import requests
    urls = _build_url(trade_date)

    session = requests.Session()
    session.headers.update(NSE_HEADERS)

    # Prime session with NSE homepage cookie
    try:
        session.get("https://www.nseindia.com", timeout=10)
    except Exception:
        pass

    for url in urls:
        try:
            resp = session.get(url, timeout=30)
            if resp.status_code != 200 or len(resp.content) < 100:
                continue

            with zipfile.ZipFile(io.BytesIO(resp.content)) as z:
                csv_name = z.namelist()[0]
                with z.open(csv_name) as f:
                    df = pd.read_csv(f)

            df.columns = [c.strip().upper() for c in df.columns]
            df = df[df["SYMBOL"].isin(["NIFTY", "BANKNIFTY", "SENSEX"])]
            df = df[df["INSTRUMENT"].isin(["OPTIDX", "OPTSTK"])]

            rename_map = {
                "SYMBOL": "underlying",
                "EXPIRY_DT": "expiry_date",
                "STRIKE_PR": "strike",
                "OPTION_TYP": "option_type",
                "OPEN": "open",
                "HIGH": "high",
                "LOW": "low",
                "CLOSE": "close",
                "SETTLE_PR": "settle_price",
                "CONTRACTS": "contracts",
                "OPEN_INT": "oi",
                "CHG_IN_OI": "change_oi",
                "TIMESTAMP": "trade_date",
                "VAL_IN_LAKH": "value_lakh",
            }
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
            df["data_source"] = "NSE_BHAVCOPY"

            logger.info("bhavcopy_sync_downloaded", date=trade_date.isoformat(), url=url, rows=len(df))
            return df

        except Exception as e:
            logger.warning("bhavcopy_sync_url_failed", url=url, error=str(e))
            continue

    return None


async def _download_bhavcopy(trade_date: date, session: aiohttp.ClientSession) -> Optional[pd.DataFrame]:
    """
    Download and parse NSE F&O Bhavcopy for a given trading date.
    Tries async aiohttp first, then falls back to synchronous requests session
    (which handles NSE cookies better on cloud IPs).
    """
    urls = _build_url(trade_date)

    # Try async first (fast path)
    for url in urls:
        try:
            async with session.get(
                url, headers=NSE_HEADERS,
                timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    continue
                content = await resp.read()
                if len(content) < 100:
                    continue

                with zipfile.ZipFile(io.BytesIO(content)) as z:
                    csv_name = z.namelist()[0]
                    with z.open(csv_name) as f:
                        df = pd.read_csv(f)

                df.columns = [c.strip().upper() for c in df.columns]
                df = df[df["SYMBOL"].isin(["NIFTY", "BANKNIFTY", "SENSEX"])]
                df = df[df["INSTRUMENT"].isin(["OPTIDX", "OPTSTK"])]

                rename_map = {
                    "SYMBOL": "underlying", "EXPIRY_DT": "expiry_date",
                    "STRIKE_PR": "strike", "OPTION_TYP": "option_type",
                    "OPEN": "open", "HIGH": "high", "LOW": "low", "CLOSE": "close",
                    "SETTLE_PR": "settle_price", "CONTRACTS": "contracts",
                    "OPEN_INT": "oi", "CHG_IN_OI": "change_oi",
                    "TIMESTAMP": "trade_date", "VAL_IN_LAKH": "value_lakh",
                }
                df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
                df["data_source"] = "NSE_BHAVCOPY"
                logger.info("bhavcopy_downloaded", date=trade_date.isoformat(), url=url, rows=len(df))
                return df

        except Exception as e:
            logger.warning("bhavcopy_url_failed", url=url, error=str(e))
            continue

    # Async failed — try synchronous requests session (cookie-aware)
    logger.info("bhavcopy_async_failed_trying_sync", date=trade_date.isoformat())
    try:
        loop = asyncio.get_event_loop()
        df = await loop.run_in_executor(None, _fetch_bhavcopy_sync, trade_date)
        if df is not None:
            return df
    except Exception as e:
        logger.warning("bhavcopy_sync_also_failed", date=trade_date.isoformat(), error=str(e))

    logger.warning("bhavcopy_not_found", date=trade_date.isoformat())
    return None


async def download_historical_bhavcopy(
    start_date: date,
    end_date: date,
    batch_size: int = 5,
) -> list[pd.DataFrame]:
    """
    Download NSE F&O Bhavcopy for a date range.
    Returns list of DataFrames (one per trading day).
    Skips weekends automatically.
    Processes in batches to avoid overwhelming NSE servers.
    """
    trading_days = []
    current = start_date
    while current <= end_date:
        # Skip weekends (NSE is closed Saturday=5, Sunday=6)
        if current.weekday() < 5:
            trading_days.append(current)
        current += timedelta(days=1)

    logger.info(
        "bhavcopy_bulk_download_start",
        start=start_date.isoformat(),
        end=end_date.isoformat(),
        trading_days=len(trading_days),
    )

    results = []
    async with aiohttp.ClientSession() as session:
        # First, get a session cookie from NSE homepage (required)
        try:
            async with session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=aiohttp.ClientTimeout(total=15)) as _:
                pass
        except Exception:
            pass

        # Download in batches with delay to avoid rate limiting
        for i in range(0, len(trading_days), batch_size):
            batch = trading_days[i:i + batch_size]
            tasks = [_download_bhavcopy(d, session) for d in batch]
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in batch_results:
                if isinstance(r, pd.DataFrame) and len(r) > 0:
                    results.append(r)

            # Respectful delay between batches
            if i + batch_size < len(trading_days):
                await asyncio.sleep(2.0)

    logger.info(
        "bhavcopy_bulk_download_complete",
        days_requested=len(trading_days),
        days_downloaded=len(results),
    )
    return results


async def download_latest_bhavcopy() -> Optional[pd.DataFrame]:
    """Download yesterday's or today's bhavcopy — used by Phase 22 daily cycle."""
    today = date.today()
    # Try today first, then yesterday (in case today's isn't published yet)
    for offset in range(0, 5):
        check_date = today - timedelta(days=offset)
        if check_date.weekday() >= 5:
            continue

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get("https://www.nseindia.com", headers=NSE_HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as _:
                    pass
            except Exception:
                pass
            df = await _download_bhavcopy(check_date, session)
            if df is not None:
                return df

    return None
