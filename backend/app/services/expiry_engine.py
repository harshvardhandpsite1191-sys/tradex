"""
AI-QROS — Expiry Intelligence Engine
Phase 12: Expiry Intelligence

Calculates options max pain levels, net gamma exposure (GEX), and predicts
expiration pinning risks using historical option settlements and current options chain data.
"""

import time
import math
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Tuple
import structlog
import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.database import AsyncSessionLocal
from app.models.expiry import ExpiryIntelligence
from app.models.market_data import OptionSettlement, OHLCVCandle

logger = structlog.get_logger("aiqros.services.expiry_engine")

TARGET_SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]


# ─────────────────────────────────────────────
# Black-Scholes Options Greeks Calculations
# ─────────────────────────────────────────────

def _normal_cdf(x: float) -> float:
    """Standard normal cumulative distribution function approximation."""
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def _normal_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x**2) / math.sqrt(2.0 * math.pi)


def calculate_gamma(
    spot: float,
    strike: float,
    days_to_expiry: float,
    volatility: float,
    risk_free: float = 0.07
) -> float:
    """Calculate option Gamma."""
    t = days_to_expiry / 365.0
    if t <= 0 or volatility <= 0 or spot <= 0:
        return 0.0
    
    d1 = (math.log(spot / strike) + (risk_free + 0.5 * volatility**2) * t) / (volatility * math.sqrt(t))
    gamma = _normal_pdf(d1) / (spot * volatility * math.sqrt(t))
    return gamma


# ─────────────────────────────────────────────
# Expiry Engines
# ─────────────────────────────────────────────

def calculate_max_pain(options_df: pd.DataFrame) -> float:
    """
    Calculate the option strike that minimizes cumulative option buyer value.
    """
    if options_df.empty:
        return 0.0
    
    strikes = options_df["strike"].unique()
    strikes.sort()
    
    min_pain = float("inf")
    pain_strike = 0.0
    
    # Calculate pain at each strike level
    for test_strike in strikes:
        current_pain = 0.0
        for _, row in options_df.iterrows():
            strike = row["strike"]
            oi = row["oi"]
            opt_type = row["option_type"]
            
            if opt_type == "CE":
                current_pain += max(0.0, test_strike - strike) * oi
            elif opt_type == "PE":
                current_pain += max(0.0, strike - test_strike) * oi
                
        if current_pain < min_pain:
            min_pain = current_pain
            pain_strike = test_strike
            
    return float(pain_strike)


async def generate_expiry_intelligence(
    symbol: str,
    trade_date: date,
    db: AsyncSession
) -> Optional[ExpiryIntelligence]:
    """Calculate expiry-specific metrics for the nearest expiring option contract."""
    # 1. Load option settlements for the date
    result = await db.execute(
        select(OptionSettlement)
        .where(and_(
            OptionSettlement.underlying == symbol,
            OptionSettlement.trade_date == trade_date
        ))
    )
    rows = result.scalars().all()
    if not rows:
        logger.warn("no_options_settlement_found_for_expiry_intel", symbol=symbol, trade_date=str(trade_date))
        return None

    # Load into DataFrame
    df = pd.DataFrame([{
        "strike": r.strike, "option_type": r.option_type,
        "expiry_date": r.expiry_date, "oi": r.oi or 0,
        "close": r.close
    } for r in rows])

    # Parse and find closest expiry date
    # Format of expiry_date is usually like "29-Feb-2024" or standard date strings. We'll parse it.
    unique_expiries = df["expiry_date"].unique()
    if len(unique_expiries) == 0:
        return None

    # Pick the nearest expiry
    def _parse_exp(exp_str):
        try:
            return datetime.strptime(exp_str, "%d-%b-%Y").date()
        except:
            try:
                return datetime.strptime(exp_str, "%Y-%m-%d").date()
            except:
                return date.max

    sorted_expiries = sorted(unique_expiries, key=_parse_exp)
    nearest_expiry_str = sorted_expiries[0]
    nearest_expiry_date = _parse_exp(nearest_expiry_str)

    # Filter to nearest expiry options
    expiry_df = df[df["expiry_date"] == nearest_expiry_str]

    # Calculate Max Pain
    max_pain_val = calculate_max_pain(expiry_df)

    # Calculate PCR OI
    calls_oi = expiry_df[expiry_df["option_type"] == "CE"]["oi"].sum()
    puts_oi = expiry_df[expiry_df["option_type"] == "PE"]["oi"].sum()
    pcr_val = puts_oi / calls_oi if calls_oi > 0 else 0.0

    # Fetch spot price (close of underlying)
    # Angel One token maps: NIFTY=26000
    token_map = {"NIFTY": "26000", "BANKNIFTY": "26009", "SENSEX": "1"}
    token = token_map.get(symbol, symbol)
    spot_q = select(OHLCVCandle).where(
        and_(
            OHLCVCandle.symbol_token == token,
            OHLCVCandle.interval == "1day",
            OHLCVCandle.timestamp <= datetime.combine(trade_date, datetime.max.time())
        )
    ).order_by(OHLCVCandle.timestamp.desc()).limit(1)
    
    spot_res = await db.execute(spot_q)
    spot_row = spot_res.scalar_one_or_none()
    spot_price = spot_row.close if spot_row else max_pain_val  # Fallback to max pain if no spot

    # 2. Calculate Gamma Exposure (GEX)
    dte = (nearest_expiry_date - trade_date).days
    dte = max(dte, 0.5)  # Avoid divide by zero on expiry day
    
    # Simple IV proxy (15% if no other source)
    volatility = 0.15
    
    net_gex_val = 0.0
    for _, row in expiry_df.iterrows():
        strike = row["strike"]
        oi = row["oi"]
        opt_type = row["option_type"]
        
        gamma = calculate_gamma(spot_price, strike, dte, volatility)
        gex = oi * gamma * (spot_price ** 2) * 0.01  # Dollar Gamma representation
        
        if opt_type == "CE":
            net_gex_val += gex  # Long calls / Short calls positioning assumption
        else:
            net_gex_val -= gex  # Puts negative exposure

    # 3. Expiry pinning risk prediction
    # Pinning probability increases as DTE decreases, and if Spot is close to Max Pain
    dist_to_pain = abs(spot_price - max_pain_val) / spot_price
    dte_factor = math.exp(-dte / 3.0)  # High when close to 0 DTE
    pain_factor = math.exp(-dist_to_pain * 50.0)  # High when close to max pain strike
    pin_prob = dte_factor * pain_factor

    # Upsert the expiry intelligence entry
    entry = ExpiryIntelligence(
        trade_date=trade_date,
        symbol=symbol,
        expiry_date=nearest_expiry_str,
        max_pain=float(max_pain_val),
        pcr_oi=float(pcr_val),
        total_call_oi=float(calls_oi),
        total_put_oi=float(puts_oi),
        net_gex=float(net_gex_val),
        predicted_pin_strike=float(max_pain_val) if pin_prob > 0.4 else None,
        pinning_probability=float(pin_prob),
        details={
            "spot_price": spot_price,
            "days_to_expiry": dte,
            "nearest_expiry": nearest_expiry_str,
            "dist_to_pain_pct": round(dist_to_pain * 100.0, 4)
        }
    )

    stmt = select(ExpiryIntelligence).where(
        and_(
            ExpiryIntelligence.symbol == symbol,
            ExpiryIntelligence.trade_date == trade_date,
            ExpiryIntelligence.expiry_date == nearest_expiry_str
        )
    )
    existing = await db.execute(stmt)
    row = existing.scalar_one_or_none()

    if row:
        row.max_pain = entry.max_pain
        row.pcr_oi = entry.pcr_oi
        row.total_call_oi = entry.total_call_oi
        row.total_put_oi = entry.total_put_oi
        row.net_gex = entry.net_gex
        row.predicted_pin_strike = entry.predicted_pin_strike
        row.pinning_probability = entry.pinning_probability
        row.details = entry.details
        return row
    else:
        db.add(entry)
        return entry


async def run_daily_expiry_intelligence(trade_date: Optional[date] = None) -> dict:
    """Run daily expiry intelligence update."""
    td = trade_date or date.today()
    results = {}
    async with AsyncSessionLocal() as db:
        for symbol in TARGET_SYMBOLS:
            try:
                entry = await generate_expiry_intelligence(symbol, td, db)
                if entry:
                    results[symbol] = {
                        "expiry": entry.expiry_date,
                        "max_pain": entry.max_pain,
                        "pcr": entry.pcr_oi,
                        "pin_prob": entry.pinning_probability
                    }
            except Exception as e:
                logger.error("expiry_intelligence_failed", symbol=symbol, error=str(e))
                results[symbol] = {"status": "failed", "error": str(e)}
        await db.commit()
    return {"status": "success", "trade_date": str(td), "expiry_intelligence": results}
