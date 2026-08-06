"""
AI-QROS — Demo & Realistic Market Data Seeder
Populates rich market intelligence, regimes, expiry calculations, opening biases,
and trade signals into Neon PostgreSQL without requiring external broker credentials.
"""

import asyncio
from datetime import datetime, date, timedelta
import random
import structlog

from app.db.database import AsyncSessionLocal
from app.models.behaviour import MarketRegime, DetectedBehaviour
from app.models.opening import OpeningIntelligence
from app.models.expiry import ExpiryIntelligence
from app.models.signal import TradeSignal
from app.models.market_data import OptionSettlement, GlobalMarketData
from app.models.recommendation import TradeRecommendation
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy import select

logger = structlog.get_logger("aiqros.db.seed_demo")

SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]
BASE_PRICES = {
    "NIFTY": 24250.0,
    "BANKNIFTY": 51800.0,
    "SENSEX": 79600.0,
}


async def seed_demo_data(force: bool = False) -> dict:
    """
    Seed rich demo intelligence for the past 7 days up to today.
    Skipped if data already exists, unless force=True.
    """
    today = date.today()
    start_date = today - timedelta(days=7)

    async with AsyncSessionLocal() as db:
        # Check if already seeded
        if not force:
            existing = await db.execute(select(MarketRegime).limit(1))
            if existing.scalar_one_or_none():
                logger.info("demo_data_already_present", message="Skipping demo seeding.")
                return {"status": "skipped", "message": "Demo data already present."}

        seeded_counts = {
            "regimes": 0,
            "opening": 0,
            "expiry": 0,
            "signals": 0,
            "behaviours": 0,
            "options": 0,
            "global": 0,
            "recommendations": 0,
        }

        # Loop through past 7 days
        for day_offset in range(7, -1, -1):
            t_date = today - timedelta(days=day_offset)
            if t_date.weekday() >= 5:  # Skip weekends
                continue

            for symbol in SYMBOLS:
                base_p = BASE_PRICES[symbol]

                # 1. Market Regime
                regime_obj = MarketRegime(
                    trade_date=t_date,
                    symbol=symbol,
                    regime="trending_up" if day_offset % 2 == 0 else "ranging",
                    sub_regime="strong_trend" if day_offset % 2 == 0 else "mean_revert",
                    trend_strength=round(random.uniform(28.5, 42.0), 1),
                    volatility_state="normal",
                    options_regime="iv_expansion" if day_offset % 2 == 0 else "theta_decay",
                    confidence=round(random.uniform(0.78, 0.92), 2),
                    details={
                        "adx": 34.5,
                        "atr_pct": 1.15,
                        "moving_averages": {"sma_20": base_p - 100, "sma_50": base_p - 350},
                        "summary": f"{symbol} exhibits strong institutional buying with IV expansion."
                    }
                )
                stmt = pg_insert(MarketRegime).values({
                    "trade_date": regime_obj.trade_date,
                    "symbol": regime_obj.symbol,
                    "regime": regime_obj.regime,
                    "sub_regime": regime_obj.sub_regime,
                    "trend_strength": regime_obj.trend_strength,
                    "volatility_state": regime_obj.volatility_state,
                    "options_regime": regime_obj.options_regime,
                    "confidence": regime_obj.confidence,
                    "details": regime_obj.details,
                }).on_conflict_do_nothing()
                await db.execute(stmt)
                seeded_counts["regimes"] += 1

                # 2. Opening Intelligence
                open_obj = OpeningIntelligence(
                    trade_date=t_date,
                    symbol=symbol,
                    global_sentiment_score=round(random.uniform(0.25, 0.65), 2),
                    gift_nifty_change_pct=round(random.uniform(0.15, 0.45), 2),
                    expected_gap_pct=round(random.uniform(0.20, 0.50), 2),
                    actual_gap_pct=round(random.uniform(0.18, 0.48), 2),
                    opening_bias="bullish",
                    ib_high_predicted=base_p + 120,
                    ib_low_predicted=base_p - 60,
                    ib_high_actual=base_p + 140,
                    ib_low_actual=base_p - 50,
                    ib_extension_bias="up",
                    details={"asia_session": "+0.4%", "us_futures": "+0.3%"}
                )
                stmt = pg_insert(OpeningIntelligence).values({
                    "trade_date": open_obj.trade_date,
                    "symbol": open_obj.symbol,
                    "global_sentiment_score": open_obj.global_sentiment_score,
                    "gift_nifty_change_pct": open_obj.gift_nifty_change_pct,
                    "expected_gap_pct": open_obj.expected_gap_pct,
                    "actual_gap_pct": open_obj.actual_gap_pct,
                    "opening_bias": open_obj.opening_bias,
                    "ib_high_predicted": open_obj.ib_high_predicted,
                    "ib_low_predicted": open_obj.ib_low_predicted,
                    "ib_high_actual": open_obj.ib_high_actual,
                    "ib_low_actual": open_obj.ib_low_actual,
                    "ib_extension_bias": open_obj.ib_extension_bias,
                    "details": open_obj.details,
                }).on_conflict_do_nothing()
                await db.execute(stmt)
                seeded_counts["opening"] += 1

                # 3. Expiry Intelligence
                exp_date_str = (t_date + timedelta(days=(3 - t_date.weekday()) % 7)).strftime("%d-%b-%Y")
                exp_obj = ExpiryIntelligence(
                    trade_date=t_date,
                    symbol=symbol,
                    expiry_date=exp_date_str,
                    max_pain=base_p,
                    pcr_oi=1.18,
                    total_call_oi=14520000.0,
                    total_put_oi=17133600.0,
                    net_gex=142.5,
                    predicted_pin_strike=base_p,
                    pinning_probability=0.82,
                    details={"gamma_walls": [base_p - 200, base_p + 200], "key_resistance": base_p + 300}
                )
                stmt = pg_insert(ExpiryIntelligence).values({
                    "trade_date": exp_obj.trade_date,
                    "symbol": exp_obj.symbol,
                    "expiry_date": exp_obj.expiry_date,
                    "max_pain": exp_obj.max_pain,
                    "pcr_oi": exp_obj.pcr_oi,
                    "total_call_oi": exp_obj.total_call_oi,
                    "total_put_oi": exp_obj.total_put_oi,
                    "net_gex": exp_obj.net_gex,
                    "predicted_pin_strike": exp_obj.predicted_pin_strike,
                    "pinning_probability": exp_obj.pinning_probability,
                    "details": exp_obj.details,
                }).on_conflict_do_nothing()
                await db.execute(stmt)
                seeded_counts["expiry"] += 1

                # 4. Trade Signal
                sig_obj = TradeSignal(
                    trade_date=t_date,
                    symbol=symbol,
                    signal_type="BUY_CALL" if day_offset % 2 == 0 else "BULL_CALL_SPREAD",
                    direction="bullish",
                    confidence_score=round(random.uniform(0.79, 0.88), 2),
                    contributing_factors={
                        "regime": "trending_up",
                        "opening_bias": "bullish",
                        "pcr": 1.18,
                        "knn_similarity_score": 0.89,
                        "ml_model_probability": 0.74
                    },
                    details={"target_price": base_p + 180, "stop_loss": base_p - 80}
                )
                stmt = pg_insert(TradeSignal).values({
                    "trade_date": sig_obj.trade_date,
                    "symbol": sig_obj.symbol,
                    "signal_type": sig_obj.signal_type,
                    "direction": sig_obj.direction,
                    "confidence_score": sig_obj.confidence_score,
                    "contributing_factors": sig_obj.contributing_factors,
                    "details": sig_obj.details,
                }).on_conflict_do_nothing()
                await db.execute(stmt)
                seeded_counts["signals"] += 1

                # 5. Detected Behaviours
                behaviours_list = [
                    ("INSTITUTIONAL_FLOW", "INSTITUTIONAL", "bullish", "Large block buying detected near support."),
                    ("LIQUIDITY_SWEEP", "LIQUIDITY", "bullish", "Swept sell-side liquidity before upward expansion."),
                    ("OI_BUILDUP", "OPTIONS", "bullish", "Significant long buildup in ATM Call options."),
                    ("VOLUME_ANOMALY", "VOLUME", "bullish", "Volume spiked +145% above 20-period moving average.")
                ]
                for b_type, b_cat, b_dir, b_desc in behaviours_list:
                    beh_entry = DetectedBehaviour(
                        trade_date=t_date,
                        symbol=symbol,
                        behaviour_type=b_type,
                        category=b_cat,
                        confidence=round(random.uniform(0.80, 0.95), 2),
                        direction=b_dir,
                        description=b_desc,
                        details={"volume_multiplier": 1.45, "delta": 0.62}
                    )
                    db.add(beh_entry)
                    seeded_counts["behaviours"] += 1

                # 6. Option Settlement Chains (10 Strikes around ATM)
                strike_step = 50 if symbol == "NIFTY" else 100
                atm_strike = int(base_p / strike_step) * strike_step
                for offset in range(-5, 6):
                    strike_val = atm_strike + (offset * strike_step)
                    for opt_t in ["CE", "PE"]:
                        is_itm = (opt_t == "CE" and strike_val < base_p) or (opt_t == "PE" and strike_val > base_p)
                        intrinsic = max(0, base_p - strike_val) if opt_t == "CE" else max(0, strike_val - base_p)
                        prem = intrinsic + random.uniform(40, 150)
                        
                        opt_settle = {
                            "trade_date": t_date,
                            "underlying": symbol,
                            "expiry_date": exp_date_str,
                            "strike": float(strike_val),
                            "option_type": opt_t,
                            "open": round(prem * 0.95, 2),
                            "high": round(prem * 1.12, 2),
                            "low": round(prem * 0.90, 2),
                            "close": round(prem, 2),
                            "settle_price": round(prem, 2),
                            "contracts": random.randint(15000, 85000),
                            "value_lakh": round(random.uniform(400, 2500), 2),
                            "oi": random.randint(500000, 3500000),
                            "change_oi": random.randint(-150000, 450000),
                            "data_source": "DEMO_SEED"
                        }
                        stmt = pg_insert(OptionSettlement).values(opt_settle).on_conflict_do_nothing()
                        await db.execute(stmt)
                        seeded_counts["options"] += 1

                # 7. Trade Recommendation
                rec_entry = TradeRecommendation(
                    trade_date=t_date,
                    symbol=symbol,
                    strategy_name="BULL_CALL_SPREAD",
                    legs=[
                        {"type": "BUY", "strike": atm_strike, "option_type": "CE", "entry_price": 140.0},
                        {"type": "SELL", "strike": atm_strike + (2 * strike_step), "option_type": "CE", "entry_price": 45.0}
                    ],
                    max_risk=95.0 * 25,
                    max_reward=105.0 * 25,
                    risk_reward_ratio=1.1,
                    breakeven_points=[atm_strike + 95.0],
                    greeks_snapshot={"delta": 0.42, "gamma": 0.0015, "theta": -12.5, "vega": 18.2},
                    conviction_score=0.86,
                    status="ACTIVE" if day_offset == 0 else "CLOSED"
                )
                stmt = pg_insert(TradeRecommendation).values({
                    "trade_date": rec_entry.trade_date,
                    "symbol": rec_entry.symbol,
                    "strategy_name": rec_entry.strategy_name,
                    "legs": rec_entry.legs,
                    "max_risk": rec_entry.max_risk,
                    "max_reward": rec_entry.max_reward,
                    "risk_reward_ratio": rec_entry.risk_reward_ratio,
                    "breakeven_points": rec_entry.breakeven_points,
                    "greeks_snapshot": rec_entry.greeks_snapshot,
                    "conviction_score": rec_entry.conviction_score,
                    "status": rec_entry.status,
                }).on_conflict_do_nothing()
                await db.execute(stmt)
                seeded_counts["recommendations"] += 1

        # 8. Global Market Factors
        global_factors = [
            ("SP500", "^GSPC", 5520.4),
            ("NASDAQ", "^IXIC", 17650.2),
            ("GIFT_NIFTY", "NIFTYBEES.NS", 24310.0),
            ("US_VIX", "^VIX", 15.4),
            ("BRENT_CRUDE", "BZ=F", 76.5),
            ("USD_INR", "USDINR=X", 83.95),
        ]
        for factor_name, ticker, val in global_factors:
            for day_offset in range(7, -1, -1):
                t_date = today - timedelta(days=day_offset)
                if t_date.weekday() >= 5:
                    continue
                v_entry = {
                    "trade_date": t_date,
                    "factor_name": factor_name,
                    "ticker": ticker,
                    "open": round(val * 0.995, 2),
                    "high": round(val * 1.008, 2),
                    "low": round(val * 0.991, 2),
                    "close": round(val * (1 + random.uniform(-0.005, 0.008)), 2),
                    "volume": random.randint(10000, 500000),
                    "data_source": "DEMO_SEED"
                }
                stmt = pg_insert(GlobalMarketData).values(v_entry).on_conflict_do_nothing()
                await db.execute(stmt)
                seeded_counts["global"] += 1

        await db.commit()
        logger.info("demo_data_seeded_successfully", counts=seeded_counts)
        return {"status": "success", "counts": seeded_counts}
