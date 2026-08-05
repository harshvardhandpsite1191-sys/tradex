"""
AI-QROS — yfinance Global Markets Connector
Phase 2: Data Infrastructure

Fetches daily OHLCV data for all 16 global market factors from yfinance.
This is FREE, no authentication required.

Decision rationale:
- Global markets are MACRO factors for NIFTY/SENSEX
- Daily OHLCV is sufficient — Indian market hours don't overlap US/European hours
- 5-year daily data: fully available from yfinance
- Intraday global data: not needed (global indices are closed when NIFTY trades)

Covers all 16 global factors from user's specification:
  US Markets: S&P 500, Nasdaq, Dow Jones
  Asian Markets: Nikkei, Hang Seng, Shanghai, KOSPI
  Gift Nifty: SGX Nifty proxy via GFT futures
  European Markets: FTSE 100, DAX, CAC 40
  Commodities: Brent Crude
  Currency: USD/INR
  Fixed Income: US 10-Year Treasury Yield
  Fear Index: VIX (CBOE)
  Gold: Gold Spot Price
"""

import asyncio
from datetime import datetime, date, timedelta
from typing import Optional
import pandas as pd
import structlog

logger = structlog.get_logger("aiqros.data.yfinance_global")

# All 16 global factors with their yfinance tickers
GLOBAL_TICKERS = {
    # US Markets (35–40% impact)
    "SP500":      "^GSPC",
    "NASDAQ":     "^IXIC",
    "DOW":        "^DJI",

    # Asian Markets (10–15% impact)
    "NIKKEI":     "^N225",
    "HANGSENG":   "^HSI",
    "SHANGHAI":   "000001.SS",
    "KOSPI":      "^KS11",

    # Gift Nifty proxy (20–25% impact — nearest SGX futures)
    "GIFT_NIFTY": "NIFTYBEES.NS",   # Proxy via NIFTY ETF when SGX unavailable

    # European Markets (2–5% impact)
    "FTSE":       "^FTSE",
    "DAX":        "^GDAXI",
    "CAC40":      "^FCHI",

    # Commodities / Macro (5–10% impact)
    "BRENT_CRUDE":"BZ=F",
    "GOLD":       "GC=F",

    # Currency (5–10% impact)
    "USD_INR":    "USDINR=X",

    # Fixed Income (3–5% impact)
    "US10Y_YIELD":"^TNX",

    # Fear Index (3–5% impact)
    "US_VIX":     "^VIX",
}


def fetch_historical_global_data(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> dict[str, pd.DataFrame]:
    """
    Fetch 5-year daily OHLCV for all 16 global factors.
    Returns a dict mapping factor_name → DataFrame.
    All data is daily — this is sufficient for macro feature computation.
    """
    try:
        import yfinance as yf
    except ImportError:
        logger.error("yfinance_not_installed", message="pip install yfinance")
        return {}

    start = start_date or (date.today() - timedelta(days=365 * 5))
    end = end_date or date.today()

    results = {}

    for factor_name, ticker in GLOBAL_TICKERS.items():
        try:
            data = yf.download(
                ticker,
                start=start.isoformat(),
                end=end.isoformat(),
                progress=False,
                auto_adjust=True,
            )

            if data.empty:
                logger.warning("yfinance_no_data", ticker=ticker, factor=factor_name)
                continue

            data = data.reset_index()
            data.columns = [c.lower() for c in data.columns]
            data["factor_name"] = factor_name
            data["ticker"] = ticker
            data["data_source"] = "YFINANCE"
            data = data.rename(columns={"date": "trade_date"})

            results[factor_name] = data
            logger.info(
                "yfinance_fetched",
                factor=factor_name,
                ticker=ticker,
                rows=len(data),
            )

        except Exception as e:
            logger.error("yfinance_error", factor=factor_name, ticker=ticker, error=str(e))
            continue

    logger.info("yfinance_global_complete", factors_fetched=len(results), total_factors=len(GLOBAL_TICKERS))
    return results


def fetch_latest_global_snapshot() -> dict[str, dict]:
    """
    Fetch today's latest price for all 16 global factors.
    Used by Phase 20 (Live Engine) for current global market context.
    yfinance provides latest price for all tickers in one call.
    """
    try:
        import yfinance as yf
    except ImportError:
        return {}

    snapshot = {}
    tickers_str = " ".join(GLOBAL_TICKERS.values())

    try:
        data = yf.download(
            tickers_str,
            period="2d",
            progress=False,
            auto_adjust=True,
        )

        if data.empty:
            return {}

        close_data = data["Close"].iloc[-1]
        prev_close = data["Close"].iloc[-2] if len(data) > 1 else None

        for factor_name, ticker in GLOBAL_TICKERS.items():
            if ticker in close_data:
                current = float(close_data[ticker]) if not pd.isna(close_data[ticker]) else None
                prev = float(prev_close[ticker]) if prev_close is not None and not pd.isna(prev_close[ticker]) else None
                change_pct = ((current - prev) / prev * 100) if current and prev else None

                snapshot[factor_name] = {
                    "ticker": ticker,
                    "price": current,
                    "prev_close": prev,
                    "change_pct": change_pct,
                    "timestamp": datetime.utcnow().isoformat(),
                }

    except Exception as e:
        logger.error("yfinance_snapshot_error", error=str(e))

    return snapshot
