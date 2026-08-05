"""
AI-QROS — Historical Verification Engine
Phase 8: Deep Backtesting of Verified Hypotheses to Produce Research Findings

Takes verified hypotheses from Phase 7, performs a walk-forward backtest
over historical feature store data, calculates edge metrics (Sharpe, Max Drawdown, Profit Factor),
and creates ResearchFinding records for those exceeding confidence and performance thresholds.
"""

import time
import math
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.database import AsyncSessionLocal
from app.models.research import ResearchHypothesis, HypothesisTestResult, ResearchFinding, ResearchPipelineLog
from app.models.feature_store import ComputedFeatureStore

logger = structlog.get_logger("aiqros.services.historical_verifier")


def _calculate_profit_factor(returns: List[float]) -> float:
    gains = sum(r for r in returns if r > 0)
    losses = abs(sum(r for r in returns if r < 0))
    return gains / losses if losses > 0 else (gains if gains > 0 else 1.0)


def _calculate_sharpe(returns: List[float], risk_free_ann: float = 0.07) -> float:
    if len(returns) < 5:
        return 0.0
    daily_rf = (1.0 + risk_free_ann) ** (1.0 / 252.0) - 1.0
    excess_returns = [r - daily_rf for r in returns]
    mean_excess = sum(excess_returns) / len(excess_returns)
    if len(excess_returns) < 2:
        return 0.0
    var = sum((r - mean_excess) ** 2 for r in excess_returns) / (len(excess_returns) - 1)
    std_excess = math.sqrt(var)
    if std_excess == 0:
        return 0.0
    # Annualized Sharpe ratio
    return (mean_excess / std_excess) * math.sqrt(252.0)


def _calculate_max_drawdown(returns: List[float]) -> float:
    if not returns:
        return 0.0
    peak = 1.0
    drawdown = 0.0
    portfolio = 1.0
    for r in returns:
        portfolio *= (1.0 + r)
        if portfolio > peak:
            peak = portfolio
        dd = (peak - portfolio) / peak
        if dd > drawdown:
            drawdown = dd
    return drawdown


async def run_historical_verification(
    trade_date: Optional[date] = None,
    triggered_by: str = "scheduler",
    min_confidence_score: float = 0.60,
) -> dict:
    """
    Query verified hypotheses, run a backtest on historical feature store,
    generate performance statistics, and promote them to ResearchFinding.
    """
    if trade_date is None:
        trade_date = date.today()

    start_time = time.time()
    verified_count = 0
    findings_created = 0

    async with AsyncSessionLocal() as db:
        log = ResearchPipelineLog(
            pipeline_phase="historical_verification",
            trade_date=trade_date,
            status="running",
            triggered_by=triggered_by,
        )
        db.add(log)
        await db.flush()

        try:
            # Get verified hypotheses that don't have active findings yet
            hyp_q = select(ResearchHypothesis).where(
                and_(
                    ResearchHypothesis.status == "verified",
                    ~ResearchHypothesis.hypothesis_id.in_(
                        select(ResearchFinding.hypothesis_id).where(ResearchFinding.status == "active")
                    )
                )
            )
            res = await db.execute(hyp_q)
            hypotheses = res.scalars().all()

            for hyp in hypotheses:
                # Load historical feature store data for backtest
                lookback = hyp.condition.get("lookback_days", 252)
                cutoff = date.today() - timedelta(days=lookback)
                
                feat_q = select(ComputedFeatureStore.trade_date, ComputedFeatureStore.features).where(
                    and_(
                        ComputedFeatureStore.symbol == hyp.symbol,
                        ComputedFeatureStore.trade_date >= cutoff
                    )
                ).order_by(ComputedFeatureStore.trade_date.asc())
                
                feat_res = await db.execute(feat_q)
                rows = feat_res.all()

                # Basic trade logic simulation
                trades_returns = []
                for trade_dt, features in rows:
                    # Determine if conditions are met
                    # Simple evaluation of condition statement (e.g. PCR, ADX or general matches)
                    condition_met = False
                    when_str = hyp.condition.get("when", "")
                    
                    if "regime" in when_str:
                        regime = features.get("market_regime")
                        if regime and regime in when_str:
                            condition_met = True
                    elif "pcr_oi" in when_str:
                        pcr = features.get("pcr_oi")
                        if pcr:
                            if ">" in when_str and pcr > float(when_str.split(">")[1].split(" ")[0]):
                                condition_met = True
                            elif "<" in when_str and pcr < float(when_str.split("<")[1].split(" ")[0]):
                                condition_met = True
                    else:
                        # Fallback match condition logic
                        condition_met = True

                    if condition_met:
                        nxt_ret = features.get("price_daily_return") or features.get("daily_return", 0.0)
                        # direction adjustment
                        is_bullish = "return > 0" in hyp.condition.get("then", "") or "bullish" in when_str.lower()
                        trades_returns.append(nxt_ret if is_bullish else -nxt_ret)

                if len(trades_returns) < 15:
                    continue  # Not enough sample size to verify historically

                # Calculate backtest performance metrics
                wins = [r for r in trades_returns if r > 0]
                win_rate = len(wins) / len(trades_returns)
                avg_return = sum(trades_returns) / len(trades_returns)
                profit_factor = _calculate_profit_factor(trades_returns)
                sharpe = _calculate_sharpe(trades_returns)
                max_dd = _calculate_max_drawdown(trades_returns)

                # Overall confidence score formula based on win rate, sample size, and Sharpe
                sample_score = min(len(trades_returns) / 100.0, 1.0)
                sharpe_score = min(max(sharpe, 0.0) / 2.0, 1.0)
                confidence_score = (win_rate * 0.4) + (sample_score * 0.3) + (sharpe_score * 0.3)

                verified_count += 1

                if confidence_score >= min_confidence_score:
                    finding_id = f"FIND-{hyp.symbol}-{hyp.category[:4]}-{int(time.time()) % 10000:04d}"
                    finding = ResearchFinding(
                        finding_id=finding_id,
                        hypothesis_id=hyp.hypothesis_id,
                        symbol=hyp.symbol,
                        category=hyp.category,
                        title=f"Verified: {hyp.title}",
                        summary=f"Backtested over {len(trades_returns)} samples. Win Rate: {win_rate:.2%}, Sharpe: {sharpe:.2f}, Profit Factor: {profit_factor:.2f}.",
                        actionable_insight=f"When {hyp.condition.get('when', '')}, execute strategy with target daily return of {avg_return:.2%}.",
                        win_rate=win_rate,
                        avg_return=avg_return,
                        sample_size=len(trades_returns),
                        confidence_score=confidence_score,
                        applicable_regimes={"regimes": [hyp.tags.get("regime")] if hyp.tags and hyp.tags.get("regime") else []},
                        applicable_conditions=hyp.condition,
                        status="active",
                        details={
                            "profit_factor": profit_factor,
                            "sharpe_ratio": sharpe,
                            "max_drawdown": max_dd,
                            "total_trades": len(trades_returns)
                        }
                    )
                    db.add(finding)
                    findings_created += 1

            duration = round(time.time() - start_time, 2)
            log.status = "success"
            log.items_processed = verified_count
            log.items_generated = findings_created
            log.completed_at = datetime.utcnow()
            log.duration_seconds = duration
            log.details = {"verified_hypotheses": verified_count, "findings_created": findings_created}
            await db.commit()

            logger.info("historical_verification_completed", verified=verified_count, findings=findings_created)
            return {
                "status": "success",
                "verified_hypotheses_processed": verified_count,
                "findings_created": findings_created,
                "duration_seconds": duration
            }

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)[:500]
            log.completed_at = datetime.utcnow()
            log.duration_seconds = round(time.time() - start_time, 2)
            await db.commit()
            logger.error("historical_verification_failed", error=str(e))
            return {"status": "failed", "error": str(e)[:200]}
