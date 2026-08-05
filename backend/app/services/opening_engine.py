"""
AI-QROS — Opening Intelligence Engine
Phase 11: Opening Intelligence

Analyzes pre-market indicators, global macro factors, and prior profile metrics
to produce daily gap expectations, opening direction bias, and predicted Initial Balance (IB) ranges.
"""

import time
import math
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, desc

from app.db.database import AsyncSessionLocal
from app.models.opening import OpeningIntelligence
from app.models.market_data import GlobalMarketData, OHLCVCandle
from app.models.feature_store import ComputedFeatureStore

logger = structlog.get_logger("aiqros.services.opening_engine")

TARGET_SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]
SYMBOL_MAP = {"NIFTY": "26000", "BANKNIFTY": "26009", "SENSEX": "1"}


async def calculate_global_sentiment(trade_date: date, db: AsyncSession) -> Tuple[float, Optional[float]]:
    """
    Calculate consolidated global sentiment score (-1 to +1) and GIFT Nifty return.
    Looks at S&P 500, Nasdaq, Dow Jones, Nikkei, Hang Seng, USD/INR, and US VIX.
    """
    global_q = select(GlobalMarketData).where(GlobalMarketData.trade_date == trade_date)
    res = await db.execute(global_q)
    rows = res.scalars().all()
    if not rows:
        # Fallback to the previous day if no current day data is loaded yet
        prev_date = trade_date - timedelta(days=1)
        global_q = select(GlobalMarketData).where(GlobalMarketData.trade_date == prev_date)
        res = await db.execute(global_q)
        rows = res.scalars().all()
        if not rows:
            return 0.0, None

    bullish_weight = 0.0
    total_weight = 0.0
    gift_nifty_change = None

    for r in rows:
        ret = 0.0
        if r.open and r.close:
            ret = (r.close - r.open) / r.open
        
        # Factor definitions & weighting
        if r.factor_name in ("SP500", "NASDAQ", "DOW"):
            weight = 2.0
            bullish_weight += (weight if ret > 0 else -weight)
            total_weight += weight
        elif r.factor_name in ("NIKKEI", "HANGSENG"):
            weight = 1.0
            bullish_weight += (weight if ret > 0 else -weight)
            total_weight += weight
        elif r.factor_name == "GIFT_NIFTY":
            weight = 3.0
            gift_nifty_change = ret
            bullish_weight += (weight if ret > 0 else -weight)
            total_weight += weight
        elif r.factor_name == "US_VIX":
            # Inverse relationship
            weight = 1.5
            bullish_weight += (-weight if ret > 0 else weight)
            total_weight += weight
        elif r.factor_name == "USD_INR":
            # Strong USD is typically negative for Indian markets
            weight = 1.0
            bullish_weight += (-weight if ret > 0 else weight)
            total_weight += weight

    sentiment_score = bullish_weight / total_weight if total_weight > 0 else 0.0
    return round(float(sentiment_score), 4), gift_nifty_change


async def generate_opening_intelligence(
    symbol: str,
    trade_date: date,
    db: AsyncSession
) -> Optional[OpeningIntelligence]:
    """Generates pre-market opening intelligence for a symbol."""
    # 1. Fetch prior day Close & ATR from Feature Store
    prev_date = trade_date - timedelta(days=1)
    feat_q = select(ComputedFeatureStore.features).where(
        and_(
            ComputedFeatureStore.symbol == symbol,
            ComputedFeatureStore.trade_date <= prev_date
        )
    ).order_by(ComputedFeatureStore.trade_date.desc()).limit(1)
    
    feat_res = await db.execute(feat_q)
    features = feat_res.scalar_one_or_none() or {}
    
    prev_close = features.get("price_close") or features.get("close")
    atr = features.get("atr_14")
    
    if not prev_close:
        # Load from candle database if feature store is missing
        token = SYMBOL_MAP.get(symbol, symbol)
        candle_q = select(OHLCVCandle).where(
            and_(
                OHLCVCandle.symbol_token == token,
                OHLCVCandle.interval == "1day",
                OHLCVCandle.timestamp < datetime.combine(trade_date, datetime.min.time())
            )
        ).order_by(OHLCVCandle.timestamp.desc()).limit(1)
        candle_res = await db.execute(candle_q)
        row = candle_res.scalar_one_or_none()
        if row:
            prev_close = row.close
            atr = (row.high - row.low) * 0.8  # Rough proxy for ATR
        else:
            prev_close = 20000.0  # Fallback dummy NIFTY close
            atr = 150.0

    # 2. Get Global Sentiment
    sentiment, gift_nifty_change = await calculate_global_sentiment(trade_date, db)

    # 3. Calculate expected gap size & direction
    # Gift Nifty change is primary driver, scaled with global sentiment score
    if gift_nifty_change is not None:
        expected_gap_pct = gift_nifty_change * 100.0
    else:
        expected_gap_pct = sentiment * 0.5  # Max 0.5% gap expectation if Gift Nifty missing

    # Set bias classification
    if expected_gap_pct > 0.15:
        opening_bias = "bullish"
    elif expected_gap_pct < -0.15:
        opening_bias = "bearish"
    else:
        opening_bias = "neutral"

    # 4. Predict Initial Balance (first hour range) high and low boundaries
    # Bullish bias shifts the predicted IB higher relative to previous close, bearish shifts it lower
    expected_open = prev_close * (1.0 + (expected_gap_pct / 100.0))
    ib_range = (atr or 150.0) * 0.45  # Average IB range is approx 45% of daily ATR
    
    if opening_bias == "bullish":
        ib_low_predicted = expected_open - (ib_range * 0.3)
        ib_high_predicted = expected_open + (ib_range * 0.7)
    elif opening_bias == "bearish":
        ib_low_predicted = expected_open - (ib_range * 0.7)
        ib_high_predicted = expected_open + (ib_range * 0.3)
    else:
        ib_low_predicted = expected_open - (ib_range * 0.5)
        ib_high_predicted = expected_open + (ib_range * 0.5)

    # 5. Populate and Upsert Opening Intelligence Entry
    entry = OpeningIntelligence(
        trade_date=trade_date,
        symbol=symbol,
        global_sentiment_score=sentiment,
        gift_nifty_change_pct=round(gift_nifty_change * 100.0, 4) if gift_nifty_change else None,
        expected_gap_pct=round(expected_gap_pct, 4),
        opening_bias=opening_bias,
        ib_high_predicted=round(ib_high_predicted, 2),
        ib_low_predicted=round(ib_low_predicted, 2),
        details={
            "sentiment_score": sentiment,
            "prev_close": prev_close,
            "predicted_open": round(expected_open, 2),
            "estimated_atr": atr
        }
    )

    stmt = select(OpeningIntelligence).where(
        and_(
            OpeningIntelligence.symbol == symbol,
            OpeningIntelligence.trade_date == trade_date
        )
    )
    existing = await db.execute(stmt)
    row = existing.scalar_one_or_none()

    if row:
        row.global_sentiment_score = sentiment
        row.gift_nifty_change_pct = entry.gift_nifty_change_pct
        row.expected_gap_pct = entry.expected_gap_pct
        row.opening_bias = opening_bias
        row.ib_high_predicted = entry.ib_high_predicted
        row.ib_low_predicted = entry.ib_low_predicted
        row.details = entry.details
        return row
    else:
        db.add(entry)
        return entry


async def run_daily_opening_intelligence(trade_date: Optional[date] = None) -> dict:
    """Run daily pre-market opening intelligence check."""
    td = trade_date or date.today()
    results = {}
    async with AsyncSessionLocal() as db:
        for symbol in TARGET_SYMBOLS:
            try:
                entry = await generate_opening_intelligence(symbol, td, db)
                if entry:
                    results[symbol] = {
                        "global_sentiment": entry.global_sentiment_score,
                        "expected_gap_pct": entry.expected_gap_pct,
                        "opening_bias": entry.opening_bias,
                        "predicted_ib": f"{entry.ib_low_predicted} - {entry.ib_high_predicted}"
                    }
            except Exception as e:
                logger.error("opening_intelligence_failed", symbol=symbol, error=str(e))
                results[symbol] = {"status": "failed", "error": str(e)}
        await db.commit()
    return {"status": "success", "trade_date": str(td), "opening_intelligence": results}
