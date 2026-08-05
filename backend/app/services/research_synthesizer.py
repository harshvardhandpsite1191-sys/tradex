"""
AI-QROS — Research Synthesis Engine
Phase 9: Research Synthesis

Synthesises all active, verified Research Findings into consolidated quantitative intelligence.
Monitors recent performance to flag/deprecate stale or decaying findings, aggregates finding edge
by market regime, and outputs synthesized instructions for the Phase 10 Regime Engine and Phase 15 Signal Generator.
"""

import time
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, update

from app.db.database import AsyncSessionLocal
from app.models.research import ResearchFinding, ResearchPipelineLog
from app.models.feature_store import ComputedFeatureStore

logger = structlog.get_logger("aiqros.services.research_synthesizer")


async def run_synthesis(
    trade_date: Optional[date] = None,
    triggered_by: str = "scheduler",
) -> dict:
    """
    Synthesise all active research findings, evaluate recent 20-day decay,
    deprecate decaying findings, and produce synthesized regime insights.
    """
    if trade_date is None:
        trade_date = date.today()

    start_time = time.time()

    async with AsyncSessionLocal() as db:
        log = ResearchPipelineLog(
            pipeline_phase="research_synthesis",
            trade_date=trade_date,
            status="running",
            triggered_by=triggered_by,
        )
        db.add(log)
        await db.flush()

        try:
            # 1. Fetch active findings
            active_q = select(ResearchFinding).where(ResearchFinding.status == "active")
            res = await db.execute(active_q)
            findings = res.scalars().all()

            processed = 0
            deprecated = 0
            synthesized_regimes = {}

            # Cache recent 20-day returns for decay check
            recent_cutoff = date.today() - timedelta(days=30)  # ~20 trading days
            
            for symbol in ["NIFTY", "BANKNIFTY", "SENSEX"]:
                feat_q = select(ComputedFeatureStore.trade_date, ComputedFeatureStore.features).where(
                    and_(
                        ComputedFeatureStore.symbol == symbol,
                        ComputedFeatureStore.trade_date >= recent_cutoff
                    )
                ).order_by(ComputedFeatureStore.trade_date.asc())
                feat_res = await db.execute(feat_q)
                rows = feat_res.all()
                
                # Check performance of findings active on this symbol
                symbol_findings = [f for f in findings if f.symbol == symbol]
                for finding in symbol_findings:
                    processed += 1
                    
                    # Simulate trade decisions over the last 20 trading days
                    recent_trades = []
                    for trade_dt, features in rows:
                        when_str = finding.applicable_conditions.get("when", "")
                        condition_met = False
                        
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
                            condition_met = True

                        if condition_met:
                            ret = features.get("price_daily_return") or features.get("daily_return", 0.0)
                            is_bullish = "return > 0" in finding.applicable_conditions.get("then", "") or "bullish" in when_str.lower()
                            recent_trades.append(ret if is_bullish else -ret)

                    # Decay/Out of sample tracking
                    if len(recent_trades) >= 5:
                        recent_win_rate = len([r for r in recent_trades if r > 0]) / len(recent_trades)
                        # If win rate has completely collapsed in recent sample, flag/deprecate finding
                        if recent_win_rate < 0.40:
                            finding.status = "deprecated"
                            deprecated += 1
                            logger.info("finding_deprecated", finding_id=finding.finding_id, reason="performance_decay", recent_win_rate=recent_win_rate)
                            continue
                    
                    # Update last validated timestamp
                    finding.last_validated = datetime.utcnow()
                    
                    # Populate regime mapping for synthesis output
                    regimes = finding.applicable_regimes.get("regimes", []) if finding.applicable_regimes else []
                    for regime in regimes:
                        if regime not in synthesized_regimes:
                            synthesized_regimes[regime] = []
                        synthesized_regimes[regime].append({
                            "finding_id": finding.finding_id,
                            "symbol": finding.symbol,
                            "category": finding.category,
                            "insight": finding.actionable_insight,
                            "confidence": finding.confidence_score,
                            "win_rate": finding.win_rate
                        })

            duration = round(time.time() - start_time, 2)
            log.status = "success"
            log.items_processed = processed
            log.items_generated = len(synthesized_regimes)
            log.completed_at = datetime.utcnow()
            log.duration_seconds = duration
            log.details = {
                "active_findings_evaluated": processed,
                "deprecated_findings": deprecated,
                "synthesized_regimes_count": len(synthesized_regimes),
                "regimes": list(synthesized_regimes.keys())
            }
            await db.commit()

            logger.info("research_synthesis_completed", processed=processed, deprecated=deprecated, regimes_count=len(synthesized_regimes))
            return {
                "status": "success",
                "evaluated_findings": processed,
                "deprecated_findings": deprecated,
                "synthesized_regimes": synthesized_regimes,
                "duration_seconds": duration
            }

        except Exception as e:
            log.status = "failed"
            log.error_message = str(e)[:500]
            log.completed_at = datetime.utcnow()
            log.duration_seconds = round(time.time() - start_time, 2)
            await db.commit()
            logger.error("research_synthesis_failed", error=str(e))
            return {"status": "failed", "error": str(e)[:200]}
