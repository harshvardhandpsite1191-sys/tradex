"""
AI-QROS — Hypothesis Testing Engine
Phase 7: Statistical testing of generated hypotheses against historical data.

Tests each hypothesis using:
 - Win Rate test (simple pass/fail proportion)
 - T-test (mean return significantly different from zero)
 - Bootstrap confidence intervals
 - Significance threshold: p < 0.05, sample >= 30

Verdict rules:
 - supported:    win_rate >= 0.55 AND p_value < 0.05 AND sample >= 30
 - weak_support: win_rate >= 0.52 AND p_value < 0.10
 - rejected:     win_rate < 0.45 OR p_value > 0.20
 - inconclusive: else
"""

import time
import math
import random
from datetime import datetime, date, timedelta
from typing import Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, text

from app.db.database import AsyncSessionLocal
from app.models.research import ResearchHypothesis, HypothesisTestResult, ResearchPipelineLog
from app.models.feature_store import ComputedFeatureStore

logger = structlog.get_logger("aiqros.services.hypothesis_tester")


# ─────────────────────────────────────────────
# Statistical helpers (no scipy — memory safe)
# ─────────────────────────────────────────────

def _mean(data: list) -> float:
    return sum(data) / len(data) if data else 0.0


def _std(data: list) -> float:
    if len(data) < 2:
        return 0.0
    m = _mean(data)
    variance = sum((x - m) ** 2 for x in data) / (len(data) - 1)
    return math.sqrt(variance)


def _t_statistic(data: list) -> tuple[float, float]:
    """Returns (t_stat, approx_p_value) using normal approximation for large samples."""
    n = len(data)
    if n < 5:
        return 0.0, 1.0
    m = _mean(data)
    s = _std(data)
    if s == 0:
        return 0.0, 1.0
    t = m / (s / math.sqrt(n))
    # Two-tailed p-value approximation via normal distribution
    abs_t = abs(t)
    if abs_t > 3.5:
        p = 0.001
    elif abs_t > 2.6:
        p = 0.01
    elif abs_t > 1.96:
        p = 0.05
    elif abs_t > 1.65:
        p = 0.10
    elif abs_t > 1.28:
        p = 0.20
    else:
        p = 0.50
    return round(t, 4), p


def _bootstrap_ci(data: list, n_boot: int = 500, ci: float = 0.95) -> dict:
    """Bootstrap confidence interval for the mean."""
    if len(data) < 5:
        return {"lower": 0.0, "upper": 0.0, "level": ci}
    n = len(data)
    boot_means = []
    for _ in range(n_boot):
        sample = [data[random.randint(0, n - 1)] for _ in range(n)]
        boot_means.append(_mean(sample))
    boot_means.sort()
    lo = int((1 - ci) / 2 * n_boot)
    hi = int((1 + ci) / 2 * n_boot)
    return {"lower": round(boot_means[lo], 4), "upper": round(boot_means[hi], 4), "level": ci}


def _verdict(win_rate: float, p_value: float, sample_size: int) -> tuple[str, bool]:
    """Determine verdict and significance."""
    if sample_size < 10:
        return "inconclusive", False
    if win_rate >= 0.55 and p_value <= 0.05 and sample_size >= 30:
        return "supported", True
    if win_rate >= 0.52 and p_value <= 0.10:
        return "weak_support", True
    if win_rate < 0.45 or p_value > 0.20:
        return "rejected", False
    return "inconclusive", False


# ─────────────────────────────────────────────
# Feature-based historical data retrieval
# ─────────────────────────────────────────────

async def _get_historical_returns(
    db: AsyncSession, symbol: str, lookback_days: int
) -> list[dict]:
    """
    Fetch daily returns and key features for a symbol.
    Uses ComputedFeatureStore as source of truth.
    Returns list of {trade_date, daily_return, features} dicts.
    """
    cutoff = date.today() - timedelta(days=lookback_days)
    result = await db.execute(
        select(ComputedFeatureStore.trade_date, ComputedFeatureStore.features)
        .where(and_(
            ComputedFeatureStore.symbol == symbol,
            ComputedFeatureStore.trade_date >= cutoff,
        ))
        .order_by(ComputedFeatureStore.trade_date.asc())
    )
    rows = result.all()
    records = []
    for trade_date, features in rows:
        daily_return = features.get("price_daily_return") or features.get("daily_return", 0.0)
        records.append({"trade_date": trade_date, "daily_return": daily_return, "features": features})
    return records


# ─────────────────────────────────────────────
# Per-category testers
# ─────────────────────────────────────────────

def _test_regime_hypothesis(hypothesis: ResearchHypothesis, records: list[dict]) -> dict:
    """Test regime-based hypotheses using historical regime feature data."""
    condition = hypothesis.condition or {}
    when_str = condition.get("when", "")

    # Extract returns for days matching regime condition
    matching_returns = []
    for r in records:
        feat = r["features"]
        regime = feat.get("market_regime", "")
        adx = feat.get("adx_14", 0) or 0
        match = False

        if "trending_up" in when_str and regime == "trending_up":
            match = True
        elif "trending_down" in when_str and regime == "trending_down":
            match = True
        elif "ranging" in when_str and regime == "ranging":
            match = True
        elif "low_vol_squeeze" in when_str and regime == "low_vol_squeeze":
            match = True

        if match:
            matching_returns.append(r["daily_return"] or 0.0)

    if not matching_returns:
        return {"sample_size": 0, "win_rate": 0.0, "avg_return": 0.0, "p_value": 1.0}

    is_bullish = "return > 0" in (condition.get("then", "")) or "bullish" in when_str.lower()
    if is_bullish:
        wins = [x for x in matching_returns if x > 0]
    else:
        wins = [x for x in matching_returns if x < 0]

    win_rate = len(wins) / len(matching_returns)
    t_stat, p_val = _t_statistic(matching_returns)
    return {
        "sample_size": len(matching_returns),
        "win_rate": round(win_rate, 4),
        "avg_return": round(_mean(matching_returns), 4),
        "t_statistic": t_stat,
        "p_value": p_val,
        "confidence_interval": _bootstrap_ci(matching_returns),
    }


def _test_options_hypothesis(hypothesis: ResearchHypothesis, records: list[dict]) -> dict:
    """Test options-based hypotheses (PCR, OI signals)."""
    condition = hypothesis.condition or {}
    when_str = condition.get("when", "")
    matching_returns = []

    for r in records:
        feat = r["features"]
        pcr = feat.get("pcr_oi") or feat.get("pcr", 0)
        match = False
        if "pcr_oi>" in when_str and pcr:
            threshold = float(when_str.split("pcr_oi>")[1].split(" ")[0])
            match = pcr > threshold
        elif "pcr_oi<" in when_str and pcr:
            threshold = float(when_str.split("pcr_oi<")[1].split(" ")[0])
            match = pcr < threshold
        elif "oi_buildup" in when_str:
            match = True  # simplified — use all records

        if match:
            matching_returns.append(r["daily_return"] or 0.0)

    if not matching_returns:
        return {"sample_size": 0, "win_rate": 0.0, "avg_return": 0.0, "p_value": 1.0}

    is_bullish = "return > 0" in condition.get("then", "") or "bullish" in when_str.lower()
    wins = [x for x in matching_returns if (x > 0 if is_bullish else x < 0)]
    win_rate = len(wins) / len(matching_returns)
    t_stat, p_val = _t_statistic(matching_returns)
    return {
        "sample_size": len(matching_returns),
        "win_rate": round(win_rate, 4),
        "avg_return": round(_mean(matching_returns), 4),
        "t_statistic": t_stat,
        "p_value": p_val,
        "confidence_interval": _bootstrap_ci(matching_returns),
    }


def _test_general_hypothesis(hypothesis: ResearchHypothesis, records: list[dict]) -> dict:
    """General fallback tester — uses all available daily returns."""
    if not records:
        return {"sample_size": 0, "win_rate": 0.0, "avg_return": 0.0, "p_value": 1.0}

    returns = [r["daily_return"] or 0.0 for r in records]
    is_bullish = "return > 0" in (hypothesis.condition or {}).get("then", "")
    wins = [x for x in returns if (x > 0 if is_bullish else x < 0)]
    win_rate = len(wins) / len(returns) if returns else 0.0
    t_stat, p_val = _t_statistic(returns)
    return {
        "sample_size": len(returns),
        "win_rate": round(win_rate, 4),
        "avg_return": round(_mean(returns), 4),
        "t_statistic": t_stat,
        "p_value": p_val,
        "confidence_interval": _bootstrap_ci(returns),
    }


CATEGORY_TESTERS = {
    "REGIME": _test_regime_hypothesis,
    "OPTIONS": _test_options_hypothesis,
}


# ─────────────────────────────────────────────
# Main orchestrator
# ─────────────────────────────────────────────

async def run_daily_testing(
    trade_date: Optional[date] = None,
    triggered_by: str = "scheduler",
    batch_size: int = 30,
) -> dict:
    """
    Test all pending hypotheses. Limits to batch_size per run to stay memory-safe.
    Updates hypothesis status to 'testing' → 'verified' or 'rejected'.
    """
    if trade_date is None:
        trade_date = date.today()

    start_time = time.time()

    async with AsyncSessionLocal() as db:
        log = ResearchPipelineLog(
            pipeline_phase="hypothesis_testing",
            trade_date=trade_date, status="running",
            triggered_by=triggered_by,
        )
        db.add(log)
        await db.flush()

        try:
            # Fetch pending hypotheses
            pending = await db.execute(
                select(ResearchHypothesis)
                .where(ResearchHypothesis.status == "generated")
                .order_by(ResearchHypothesis.priority.asc())
                .limit(batch_size)
            )
            hypotheses = pending.scalars().all()

            tested = 0
            supported = 0
            rejected = 0

            # Cache historical records per symbol
            records_cache = {}

            for hyp in hypotheses:
                if hyp.symbol not in records_cache:
                    records_cache[hyp.symbol] = await _get_historical_returns(
                        db, hyp.symbol, hyp.condition.get("lookback_days", 252) if hyp.condition else 252
                    )
                records = records_cache[hyp.symbol]

                tester = CATEGORY_TESTERS.get(hyp.category, _test_general_hypothesis)
                stats = tester(hyp, records)

                win_rate = stats.get("win_rate", 0.0)
                p_value = stats.get("p_value", 1.0)
                sample_size = stats.get("sample_size", 0)

                verdict_str, is_sig = _verdict(win_rate, p_value, sample_size)

                test_result = HypothesisTestResult(
                    hypothesis_id=hyp.hypothesis_id,
                    test_type="composite",
                    sample_size=sample_size,
                    test_period_start=date.today() - timedelta(days=252),
                    test_period_end=date.today(),
                    win_rate=win_rate,
                    avg_return=stats.get("avg_return"),
                    p_value=p_value,
                    t_statistic=stats.get("t_statistic"),
                    confidence_interval=stats.get("confidence_interval"),
                    is_significant=is_sig,
                    verdict=verdict_str,
                    details=stats,
                )
                db.add(test_result)

                # Update hypothesis status
                new_status = "verified" if verdict_str in ("supported", "weak_support") else \
                             "rejected" if verdict_str == "rejected" else "generated"
                hyp.status = new_status

                tested += 1
                if new_status == "verified":
                    supported += 1
                elif new_status == "rejected":
                    rejected += 1

            duration = round(time.time() - start_time, 2)
            log.status = "success"
            log.items_processed = tested
            log.items_generated = supported
            log.completed_at = datetime.utcnow()
            log.duration_seconds = duration
            log.details = {"tested": tested, "supported": supported, "rejected": rejected}
            await db.commit()

            logger.info("hypothesis_testing_done", tested=tested, supported=supported,
                        rejected=rejected, duration_s=duration)

            return {"status": "success", "tested": tested, "supported": supported,
                    "rejected": rejected, "duration_seconds": duration}

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)[:500]
            log.completed_at = datetime.utcnow()
            log.duration_seconds = round(time.time() - start_time, 2)
            await db.commit()
            logger.error("hypothesis_testing_failed", error=str(e))
            return {"status": "failed", "error": str(e)[:200]}
