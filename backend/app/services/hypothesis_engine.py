"""
AI-QROS — Hypothesis Generation Engine
Phase 6: Research Pipeline — Step 1

Generates testable research hypotheses from:
 1. Detected behaviours (Phase 5)
 2. Computed features (Phase 4)
 3. Market regime state
 4. Knowledge base concepts (Phase 1)

Each hypothesis is a structured, testable statement:
  "WHEN [condition] THEN [expected outcome] with [prior confidence]"

Hypothesis Categories:
 - REGIME: Trend continuation/reversal hypotheses
 - STRUCTURE: ICT/SMC pattern outcome hypotheses
 - LIQUIDITY: Sweep/stop-hunt outcome hypotheses
 - OPTIONS: OI buildup, PCR, IV-based directional hypotheses
 - VOLUME: Volume anomaly outcome hypotheses
 - INSTITUTIONAL: Smart money flow directional hypotheses
 - EXPIRY: Expiry-day behaviour hypotheses
 - OPENING: Gap and opening range hypotheses
 - MACRO: Global factor correlation hypotheses
 - CROSS_ASSET: Multi-asset correlation hypotheses
"""

import time
from datetime import datetime, date, timedelta
from typing import Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.db.database import AsyncSessionLocal
from app.models.behaviour import DetectedBehaviour, MarketRegime
from app.models.feature_store import ComputedFeatureStore
from app.models.research import ResearchHypothesis, ResearchPipelineLog

logger = structlog.get_logger("aiqros.services.hypothesis_engine")

TARGET_SYMBOLS = ["NIFTY", "BANKNIFTY", "SENSEX"]

# Counter for hypothesis IDs
_hyp_counter = {}


def _next_hyp_id(symbol: str, category: str) -> str:
    key = f"{symbol}-{category}"
    _hyp_counter[key] = _hyp_counter.get(key, 0) + 1
    return f"HYP-{symbol}-{category[:4]}-{_hyp_counter[key]:04d}"


# ═══════════════════════════════════════════════════════════════
# HYPOTHESIS GENERATORS
# Each returns a list of hypothesis dicts
# ═══════════════════════════════════════════════════════════════

def generate_regime_hypotheses(symbol: str, regime: dict, features: dict, trade_date: date) -> list[dict]:
    """Generate hypotheses from market regime classification."""
    hypotheses = []
    r = regime.get("regime", "unknown")
    adx = features.get("adx_14")
    rsi = features.get("rsi_14")

    if r == "trending_up":
        hypotheses.append({
            "category": "REGIME",
            "title": f"{symbol} uptrend continuation: trend persists for 3+ more days",
            "description": f"{symbol} is in trending_up regime (ADX={adx}). Hypothesis: the uptrend continues for at least 3 more trading days with positive returns.",
            "condition": {
                "when": f"regime=trending_up AND adx_14>{adx:.1f}" if adx else "regime=trending_up",
                "then": "cumulative_3d_return > 0",
                "features_used": ["adx_14", "sma_50_200_cross", "macd_cross"],
                "lookback_days": 252,
            },
            "expected_outcome": f"{symbol} continues rising for 3 trading days",
            "source_behaviour": "MARKET_REGIME",
            "priority": 3,
            "confidence_prior": 0.55 if adx and adx > 30 else 0.50,
            "tags": {"regime": r, "adx": adx},
        })

    elif r == "trending_down":
        hypotheses.append({
            "category": "REGIME",
            "title": f"{symbol} downtrend continuation: bearish momentum persists",
            "description": f"{symbol} is in trending_down regime (ADX={adx}). Hypothesis: the downtrend continues for 3+ days.",
            "condition": {
                "when": f"regime=trending_down AND adx_14>{adx:.1f}" if adx else "regime=trending_down",
                "then": "cumulative_3d_return < 0",
                "features_used": ["adx_14", "sma_50_200_cross"],
                "lookback_days": 252,
            },
            "expected_outcome": f"{symbol} continues falling for 3 trading days",
            "source_behaviour": "MARKET_REGIME",
            "priority": 3,
            "confidence_prior": 0.55,
            "tags": {"regime": r, "adx": adx},
        })

    elif r == "ranging":
        hypotheses.append({
            "category": "REGIME",
            "title": f"{symbol} mean reversion: extreme RSI reverts within 2 days",
            "description": f"{symbol} is in ranging regime. Hypothesis: when RSI reaches extremes (>70 or <30), price reverts to mean within 2 trading days.",
            "condition": {
                "when": "regime=ranging AND (rsi_14>70 OR rsi_14<30)",
                "then": "2d_return reverses sign from current direction",
                "features_used": ["rsi_14", "bb_20_pct_b"],
                "lookback_days": 252,
            },
            "expected_outcome": f"{symbol} reverts to SMA20 within 2 days",
            "source_behaviour": "MARKET_REGIME",
            "priority": 4,
            "confidence_prior": 0.55,
            "tags": {"regime": r, "rsi": rsi},
        })

    elif r == "low_vol_squeeze":
        hypotheses.append({
            "category": "REGIME",
            "title": f"{symbol} volatility expansion: squeeze resolves into directional move",
            "description": f"{symbol} Bollinger bandwidth is compressed (squeeze). Hypothesis: a >1.5% directional move occurs within 5 trading days.",
            "condition": {
                "when": "regime=low_vol_squeeze AND bb_20_bandwidth<0.03",
                "then": "max_5d_abs_return > 1.5",
                "features_used": ["bb_20_bandwidth", "hist_vol_5d", "atr_14"],
                "lookback_days": 252,
            },
            "expected_outcome": f"{symbol} moves >1.5% directionally within 5 days",
            "source_behaviour": "MARKET_REGIME",
            "priority": 2,
            "confidence_prior": 0.6,
            "tags": {"regime": r},
        })

    return hypotheses


def generate_structure_hypotheses(symbol: str, behaviours: list[dict], features: dict) -> list[dict]:
    """Generate hypotheses from ICT/SMC structure patterns."""
    hypotheses = []

    for b in behaviours:
        btype = b.get("behaviour_type")

        if btype == "CHOCH":
            direction = b.get("direction", "neutral")
            hypotheses.append({
                "category": "STRUCTURE",
                "title": f"{symbol} CHoCH reversal: {direction} move continues",
                "description": f"Change of Character detected ({direction}). Hypothesis: price follows through in the CHoCH direction for 2+ days.",
                "condition": {
                    "when": f"choch_detected=True AND direction={direction}",
                    "then": f"2d_return {'> 0' if direction == 'bullish' else '< 0'}",
                    "features_used": ["close", "high", "low"],
                    "lookback_days": 252,
                },
                "expected_outcome": f"{symbol} continues {direction} for 2 days after CHoCH",
                "source_behaviour": "CHOCH",
                "priority": 3,
                "confidence_prior": 0.58,
                "tags": {"pattern": "choch", "direction": direction},
            })

        elif btype == "BOS":
            direction = b.get("direction", "neutral")
            hypotheses.append({
                "category": "STRUCTURE",
                "title": f"{symbol} BOS continuation: {direction} break holds",
                "description": f"Break of Structure detected ({direction}). Hypothesis: the break holds and price extends in the break direction.",
                "condition": {
                    "when": f"bos_detected=True AND direction={direction}",
                    "then": f"1d_return {'> 0' if direction == 'bullish' else '< 0'}",
                    "features_used": ["close", "high", "low", "volume"],
                    "lookback_days": 252,
                },
                "expected_outcome": f"{symbol} extends {direction} after BOS",
                "source_behaviour": "BOS",
                "priority": 4,
                "confidence_prior": 0.55,
                "tags": {"pattern": "bos", "direction": direction},
            })

        elif btype == "FVG_DETECTION":
            direction = b.get("direction", "neutral")
            hypotheses.append({
                "category": "STRUCTURE",
                "title": f"{symbol} FVG fill: {direction} gap fills within 3 days",
                "description": f"Fair Value Gap detected ({direction}). Hypothesis: price returns to fill the FVG within 3 trading days.",
                "condition": {
                    "when": f"fvg_detected=True AND direction={direction}",
                    "then": "fvg_filled_within_3d=True",
                    "features_used": ["high", "low", "close"],
                    "lookback_days": 252,
                },
                "expected_outcome": f"{symbol} FVG fills within 3 trading days",
                "source_behaviour": "FVG_DETECTION",
                "priority": 5,
                "confidence_prior": 0.60,
                "tags": {"pattern": "fvg", "direction": direction},
            })

    return hypotheses


def generate_liquidity_hypotheses(symbol: str, behaviours: list[dict]) -> list[dict]:
    """Generate hypotheses from liquidity pattern detections."""
    hypotheses = []

    for b in behaviours:
        btype = b.get("behaviour_type")

        if btype == "STOP_HUNT":
            direction = b.get("direction", "neutral")
            hypotheses.append({
                "category": "LIQUIDITY",
                "title": f"{symbol} stop hunt reversal: {direction} move after sweep",
                "description": f"Stop hunt detected ({direction}). Hypothesis: price reverses and moves {direction} for 1-2 days after the sweep.",
                "condition": {
                    "when": f"stop_hunt=True AND direction={direction}",
                    "then": f"1d_return {'> 0.3' if direction == 'bullish' else '< -0.3'}",
                    "features_used": ["high", "low", "close", "volume"],
                    "lookback_days": 252,
                },
                "expected_outcome": f"{symbol} reverses {direction} after stop hunt",
                "source_behaviour": "STOP_HUNT",
                "priority": 2,
                "confidence_prior": 0.62,
                "tags": {"pattern": "stop_hunt", "direction": direction},
            })

        elif btype == "LIQUIDITY_SWEEP":
            details = b.get("details", {})
            if details.get("is_swept"):
                hypotheses.append({
                    "category": "LIQUIDITY",
                    "title": f"{symbol} swept liquidity reversal",
                    "description": f"Liquidity pool swept. Hypothesis: price reverses from sweep level within 1 day.",
                    "condition": {
                        "when": "liquidity_swept=True",
                        "then": "1d_reversal=True",
                        "features_used": ["high", "low", "close"],
                        "lookback_days": 252,
                    },
                    "expected_outcome": f"{symbol} reverses after sweeping liquidity",
                    "source_behaviour": "LIQUIDITY_SWEEP",
                    "priority": 3,
                    "confidence_prior": 0.58,
                    "tags": {"pattern": "sweep"},
                })

    return hypotheses


def generate_options_hypotheses(symbol: str, behaviours: list[dict], features: dict) -> list[dict]:
    """Generate hypotheses from options behaviour detections."""
    hypotheses = []

    pcr = features.get("pcr_oi")
    max_pain = features.get("max_pain")
    dte = features.get("days_to_expiry")

    # PCR extreme hypothesis
    if pcr and pcr > 1.3:
        hypotheses.append({
            "category": "OPTIONS",
            "title": f"{symbol} high PCR bullish: PCR>{pcr:.2f} implies upside",
            "description": f"Put-Call Ratio at {pcr:.2f} (>1.3). Hypothesis: high PCR indicates excess bearish positioning, creating contrarian bullish opportunity.",
            "condition": {
                "when": f"pcr_oi>{pcr:.2f}",
                "then": "1d_return > 0",
                "features_used": ["pcr_oi", "total_pe_oi", "total_ce_oi"],
                "lookback_days": 252,
            },
            "expected_outcome": f"{symbol} rises next day (contrarian PCR signal)",
            "source_behaviour": "OI_BUILDUP",
            "priority": 3,
            "confidence_prior": 0.57,
            "tags": {"pcr": pcr, "signal": "contrarian_bullish"},
        })
    elif pcr and pcr < 0.7:
        hypotheses.append({
            "category": "OPTIONS",
            "title": f"{symbol} low PCR bearish: PCR<{pcr:.2f} implies downside",
            "description": f"Put-Call Ratio at {pcr:.2f} (<0.7). Hypothesis: low PCR indicates excess bullish positioning, creating contrarian bearish opportunity.",
            "condition": {
                "when": f"pcr_oi<{pcr:.2f}",
                "then": "1d_return < 0",
                "features_used": ["pcr_oi"],
                "lookback_days": 252,
            },
            "expected_outcome": f"{symbol} falls next day (contrarian PCR signal)",
            "source_behaviour": "OI_BUILDUP",
            "priority": 3,
            "confidence_prior": 0.55,
            "tags": {"pcr": pcr, "signal": "contrarian_bearish"},
        })

    # Max Pain hypothesis
    if max_pain and dte is not None and dte <= 2:
        hypotheses.append({
            "category": "OPTIONS",
            "title": f"{symbol} max pain magnet: price gravitates to {max_pain:.0f} by expiry",
            "description": f"Max Pain at {max_pain:.0f}, {dte} DTE. Hypothesis: price converges toward max pain on expiry day.",
            "condition": {
                "when": f"days_to_expiry<={dte} AND max_pain={max_pain:.0f}",
                "then": f"expiry_close within 0.5% of {max_pain:.0f}",
                "features_used": ["max_pain", "days_to_expiry", "price_close"],
                "lookback_days": 60,
            },
            "expected_outcome": f"{symbol} pins near max pain {max_pain:.0f} on expiry",
            "source_behaviour": "EXPIRY_PINNING",
            "priority": 2,
            "confidence_prior": 0.50,
            "tags": {"max_pain": max_pain, "dte": dte},
        })

    # OI buildup direction hypotheses from behaviours
    for b in behaviours:
        if b.get("behaviour_type") == "OI_BUILDUP":
            direction = b.get("direction", "neutral")
            hypotheses.append({
                "category": "OPTIONS",
                "title": f"{symbol} OI buildup {direction}: continuation expected",
                "description": f"OI buildup detected ({direction}). Hypothesis: the buildup direction confirms and continues for 2 days.",
                "condition": {
                    "when": f"oi_buildup=True AND direction={direction}",
                    "then": f"2d_return {'> 0' if direction == 'bullish' else '< 0'}",
                    "features_used": ["ce_oi_change", "pe_oi_change", "price_daily_return"],
                    "lookback_days": 252,
                },
                "expected_outcome": f"{symbol} continues {direction} for 2 days",
                "source_behaviour": "OI_BUILDUP",
                "priority": 3,
                "confidence_prior": 0.56,
                "tags": {"signal": "oi_buildup", "direction": direction},
            })

    return hypotheses


def generate_volume_hypotheses(symbol: str, behaviours: list[dict], features: dict) -> list[dict]:
    """Generate hypotheses from volume anomalies."""
    hypotheses = []

    for b in behaviours:
        if b.get("behaviour_type") == "VOLUME_ANOMALY":
            details = b.get("details", {})
            rel_vol = details.get("relative_volume")
            direction = b.get("direction", "neutral")

            if rel_vol and rel_vol > 2.0:
                hypotheses.append({
                    "category": "VOLUME",
                    "title": f"{symbol} volume spike continuation: {direction} move follows through",
                    "description": f"Volume at {rel_vol:.1f}x average ({direction}). Hypothesis: high-volume directional moves follow through next day.",
                    "condition": {
                        "when": f"relative_volume>{rel_vol:.1f} AND direction={direction}",
                        "then": f"1d_return {'> 0' if direction == 'bullish' else '< 0'}",
                        "features_used": ["relative_volume", "price_daily_return"],
                        "lookback_days": 252,
                    },
                    "expected_outcome": f"{symbol} continues {direction} after volume spike",
                    "source_behaviour": "VOLUME_ANOMALY",
                    "priority": 4,
                    "confidence_prior": 0.54,
                    "tags": {"rel_vol": rel_vol, "direction": direction},
                })

    return hypotheses


def generate_opening_hypotheses(symbol: str, features: dict) -> list[dict]:
    """Generate hypotheses from opening/gap features."""
    hypotheses = []
    gap_pct = features.get("gap_pct")
    gap_filled = features.get("gap_filled")

    if gap_pct and abs(gap_pct) > 0.5:
        if not gap_filled:
            hypotheses.append({
                "category": "OPENING",
                "title": f"{symbol} unfilled gap: gap fills within 2 days",
                "description": f"Gap of {gap_pct:.2f}% remains unfilled. Hypothesis: gaps >0.5% fill within 2 trading days with >65% probability.",
                "condition": {
                    "when": f"abs(gap_pct)>0.5 AND gap_filled=False",
                    "then": "gap_fills_within_2d=True",
                    "features_used": ["gap_pct", "gap_filled", "gap_direction"],
                    "lookback_days": 252,
                },
                "expected_outcome": f"{symbol} gap of {gap_pct:.2f}% fills within 2 days",
                "source_behaviour": "GAP_BEHAVIOUR",
                "priority": 4,
                "confidence_prior": 0.65,
                "tags": {"gap_pct": gap_pct},
            })

    return hypotheses


def generate_macro_hypotheses(symbol: str, features: dict) -> list[dict]:
    """Generate hypotheses from macro sentiment."""
    hypotheses = []
    macro_score = features.get("macro_sentiment_score")

    if macro_score is not None:
        if macro_score > 0.3:
            hypotheses.append({
                "category": "MACRO",
                "title": f"{symbol} positive global sentiment: opens gap-up tomorrow",
                "description": f"Macro sentiment score: {macro_score:.3f} (positive). Hypothesis: positive global cues lead to gap-up opening.",
                "condition": {
                    "when": f"macro_sentiment_score>0.3",
                    "then": "next_day_gap_pct > 0.2",
                    "features_used": ["macro_sentiment_score"],
                    "lookback_days": 252,
                },
                "expected_outcome": f"{symbol} opens with positive gap tomorrow",
                "source_behaviour": "MARKET_REGIME",
                "priority": 5,
                "confidence_prior": 0.55,
                "tags": {"macro_score": macro_score},
            })
        elif macro_score < -0.3:
            hypotheses.append({
                "category": "MACRO",
                "title": f"{symbol} negative global sentiment: opens gap-down tomorrow",
                "description": f"Macro sentiment score: {macro_score:.3f} (negative). Hypothesis: negative global cues lead to gap-down opening.",
                "condition": {
                    "when": f"macro_sentiment_score<-0.3",
                    "then": "next_day_gap_pct < -0.2",
                    "features_used": ["macro_sentiment_score"],
                    "lookback_days": 252,
                },
                "expected_outcome": f"{symbol} opens with negative gap tomorrow",
                "source_behaviour": "MARKET_REGIME",
                "priority": 5,
                "confidence_prior": 0.55,
                "tags": {"macro_score": macro_score},
            })

    return hypotheses


# ═══════════════════════════════════════════════════════════════
# MAIN ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════

async def generate_hypotheses_for_date(
    symbol: str,
    trade_date: date,
    triggered_by: str = "scheduler",
) -> dict:
    """
    Generate all hypotheses for a symbol on a trade_date.
    Reads detected behaviours and features, produces hypothesis records.
    """
    start_time = time.time()

    async with AsyncSessionLocal() as db:
        log = ResearchPipelineLog(
            pipeline_phase="hypothesis_generation",
            symbol=symbol, trade_date=trade_date,
            status="running", triggered_by=triggered_by,
        )
        db.add(log)
        await db.flush()

        try:
            # Load features
            feat_result = await db.execute(
                select(ComputedFeatureStore.features)
                .where(and_(
                    ComputedFeatureStore.symbol == symbol,
                    ComputedFeatureStore.trade_date == trade_date,
                ))
                .order_by(ComputedFeatureStore.computation_version.desc())
                .limit(1)
            )
            features = feat_result.scalar_one_or_none() or {}

            # Load regime
            regime_result = await db.execute(
                select(MarketRegime)
                .where(and_(MarketRegime.symbol == symbol, MarketRegime.trade_date == trade_date))
            )
            regime_row = regime_result.scalar_one_or_none()
            regime = {
                "regime": regime_row.regime if regime_row else "unknown",
                "sub_regime": regime_row.sub_regime if regime_row else None,
                "trend_strength": regime_row.trend_strength if regime_row else None,
            } if regime_row else {"regime": "unknown"}

            # Load behaviours
            beh_result = await db.execute(
                select(DetectedBehaviour)
                .where(and_(
                    DetectedBehaviour.symbol == symbol,
                    DetectedBehaviour.trade_date == trade_date,
                ))
            )
            behaviours = [
                {"behaviour_type": b.behaviour_type, "category": b.category,
                 "direction": b.direction, "confidence": b.confidence,
                 "details": b.details}
                for b in beh_result.scalars().all()
            ]

            # Generate hypotheses from all generators
            all_hypotheses = []
            all_hypotheses.extend(generate_regime_hypotheses(symbol, regime, features, trade_date))
            all_hypotheses.extend(generate_structure_hypotheses(symbol, behaviours, features))
            all_hypotheses.extend(generate_liquidity_hypotheses(symbol, behaviours))
            all_hypotheses.extend(generate_options_hypotheses(symbol, behaviours, features))
            all_hypotheses.extend(generate_volume_hypotheses(symbol, behaviours, features))
            all_hypotheses.extend(generate_opening_hypotheses(symbol, features))
            all_hypotheses.extend(generate_macro_hypotheses(symbol, features))

            # Store hypotheses (skip duplicates by checking existing hypothesis_ids)
            stored = 0
            for h in all_hypotheses:
                hyp_id = _next_hyp_id(symbol, h["category"])

                # Check if similar hypothesis already exists (by title match)
                existing = await db.execute(
                    select(func.count(ResearchHypothesis.id))
                    .where(and_(
                        ResearchHypothesis.symbol == symbol,
                        ResearchHypothesis.title == h["title"],
                        ResearchHypothesis.status.in_(["generated", "testing"]),
                    ))
                )
                if existing.scalar() > 0:
                    continue

                db.add(ResearchHypothesis(
                    hypothesis_id=hyp_id,
                    symbol=symbol,
                    category=h["category"],
                    title=h["title"],
                    description=h["description"],
                    condition=h["condition"],
                    expected_outcome=h["expected_outcome"],
                    source_behaviour=h.get("source_behaviour"),
                    source_date=trade_date,
                    status="generated",
                    priority=h.get("priority", 5),
                    confidence_prior=h.get("confidence_prior"),
                    generated_by=triggered_by,
                    tags=h.get("tags"),
                ))
                stored += 1

            duration = round(time.time() - start_time, 2)

            log.status = "success"
            log.items_processed = len(behaviours)
            log.items_generated = stored
            log.completed_at = datetime.utcnow()
            log.duration_seconds = duration
            log.details = {"total_generated": len(all_hypotheses), "stored_new": stored}

            await db.commit()

            logger.info(
                "hypotheses_generated", symbol=symbol,
                trade_date=str(trade_date), total=len(all_hypotheses),
                stored=stored, duration_s=duration,
            )

            return {
                "status": "success",
                "symbol": symbol,
                "trade_date": str(trade_date),
                "hypotheses_generated": len(all_hypotheses),
                "hypotheses_stored": stored,
                "duration_seconds": duration,
            }

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)[:500]
            log.completed_at = datetime.utcnow()
            log.duration_seconds = round(time.time() - start_time, 2)
            await db.commit()
            logger.error("hypothesis_generation_failed", symbol=symbol, error=str(e))
            return {"status": "failed", "symbol": symbol, "error": str(e)[:200]}


async def generate_daily_hypotheses(
    trade_date: Optional[date] = None,
    triggered_by: str = "scheduler",
) -> dict:
    """Generate hypotheses for ALL symbols for a given date."""
    if trade_date is None:
        trade_date = date.today()

    results = {}
    for symbol in TARGET_SYMBOLS:
        results[symbol] = await generate_hypotheses_for_date(symbol, trade_date, triggered_by)

    total = sum(r.get("hypotheses_stored", 0) for r in results.values())
    success = sum(1 for r in results.values() if r.get("status") == "success")

    return {
        "status": "complete",
        "trade_date": str(trade_date),
        "symbols_processed": len(TARGET_SYMBOLS),
        "symbols_succeeded": success,
        "total_hypotheses_stored": total,
        "results": results,
    }
