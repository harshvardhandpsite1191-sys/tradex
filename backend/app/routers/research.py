"""
AI-QROS — Research Pipeline Router
Phase 6-9: Hypothesis Generation → Testing → Verification → Synthesis
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from typing import Optional, List
from datetime import date, datetime
from app.db.database import get_db
from app.models.research import ResearchHypothesis, HypothesisTestResult, ResearchFinding, ResearchPipelineLog
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/research", tags=["Research Pipeline"])


# ═══════════════════════════════════════════════════════════════
# TRIGGER — Admin Only
# ═══════════════════════════════════════════════════════════════

@router.post("/generate/hypotheses", dependencies=[Depends(require_admin)])
async def trigger_hypothesis_generation(
    trade_date: Optional[date] = None,
    symbol: Optional[str] = None,
):
    """Trigger Phase 6: Hypothesis Generation."""
    td = trade_date or date.today()
    if symbol:
        from app.services.hypothesis_engine import generate_hypotheses_for_date
        return await generate_hypotheses_for_date(symbol.upper(), td, triggered_by="manual")
    from app.services.hypothesis_engine import generate_daily_hypotheses
    return await generate_daily_hypotheses(td, triggered_by="manual")


@router.post("/test/hypotheses", dependencies=[Depends(require_admin)])
async def trigger_hypothesis_testing(trade_date: Optional[date] = None):
    """Trigger Phase 7: Hypothesis Testing."""
    td = trade_date or date.today()
    from app.services.hypothesis_tester import run_daily_testing
    return await run_daily_testing(td, triggered_by="manual")


@router.post("/verify/historical", dependencies=[Depends(require_admin)])
async def trigger_historical_verification(trade_date: Optional[date] = None):
    """Trigger Phase 8: Historical Verification."""
    td = trade_date or date.today()
    from app.services.historical_verifier import run_historical_verification
    return await run_historical_verification(td, triggered_by="manual")


@router.post("/synthesize", dependencies=[Depends(require_admin)])
async def trigger_synthesis(trade_date: Optional[date] = None):
    """Trigger Phase 9: Research Synthesis."""
    td = trade_date or date.today()
    from app.services.research_synthesizer import run_synthesis
    return await run_synthesis(td, triggered_by="manual")


@router.post("/run/full", dependencies=[Depends(require_admin)])
async def trigger_full_pipeline(trade_date: Optional[date] = None):
    """Trigger full Phase 6-9 research pipeline."""
    td = trade_date or date.today()
    from celery_tasks.research_tasks import run_full_research_pipeline_task
    task = run_full_research_pipeline_task.delay(td.isoformat())
    return {"status": "accepted", "task_id": task.id, "trade_date": str(td)}


# ═══════════════════════════════════════════════════════════════
# HYPOTHESES — Viewer+
# ═══════════════════════════════════════════════════════════════

@router.get("/hypotheses", dependencies=[Depends(require_viewer)])
async def list_hypotheses(
    symbol: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None, description="generated,testing,verified,rejected"),
    min_priority: int = Query(1, ge=1, le=10),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List research hypotheses with filters."""
    q = select(ResearchHypothesis)
    if symbol:
        q = q.where(ResearchHypothesis.symbol == symbol.upper())
    if category:
        q = q.where(ResearchHypothesis.category == category.upper())
    if status:
        q = q.where(ResearchHypothesis.status == status.lower())
    q = q.where(ResearchHypothesis.priority <= min_priority + 4)
    q = q.order_by(ResearchHypothesis.priority.asc(), ResearchHypothesis.generated_at.desc()).limit(limit)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [{"id": r.id, "hypothesis_id": r.hypothesis_id, "symbol": r.symbol,
             "category": r.category, "title": r.title, "status": r.status,
             "priority": r.priority, "confidence_prior": r.confidence_prior,
             "source_behaviour": r.source_behaviour, "generated_at": str(r.generated_at)} for r in rows]


@router.get("/hypotheses/{hypothesis_id}", dependencies=[Depends(require_viewer)])
async def get_hypothesis(hypothesis_id: str, db: AsyncSession = Depends(get_db)):
    """Get full hypothesis details including test results."""
    r = await db.execute(
        select(ResearchHypothesis).where(ResearchHypothesis.hypothesis_id == hypothesis_id)
    )
    h = r.scalar_one_or_none()
    if not h:
        raise HTTPException(status_code=404, detail="Hypothesis not found")

    tests = await db.execute(
        select(HypothesisTestResult).where(HypothesisTestResult.hypothesis_id == hypothesis_id)
    )
    return {
        "hypothesis": {"id": h.id, "hypothesis_id": h.hypothesis_id, "symbol": h.symbol,
                       "category": h.category, "title": h.title, "description": h.description,
                       "condition": h.condition, "expected_outcome": h.expected_outcome,
                       "status": h.status, "priority": h.priority, "tags": h.tags},
        "test_results": [{"test_type": t.test_type, "win_rate": t.win_rate, "p_value": t.p_value,
                          "is_significant": t.is_significant, "verdict": t.verdict,
                          "sample_size": t.sample_size} for t in tests.scalars().all()],
    }


# ═══════════════════════════════════════════════════════════════
# FINDINGS — Viewer+
# ═══════════════════════════════════════════════════════════════

@router.get("/findings", dependencies=[Depends(require_viewer)])
async def list_findings(
    symbol: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    min_confidence: float = Query(0.5, ge=0.0, le=1.0),
    status: str = Query("active"),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List verified research findings."""
    q = (select(ResearchFinding)
         .where(ResearchFinding.status == status)
         .where(ResearchFinding.confidence_score >= min_confidence))
    if symbol:
        q = q.where(ResearchFinding.symbol == symbol.upper())
    if category:
        q = q.where(ResearchFinding.category == category.upper())
    q = q.order_by(ResearchFinding.confidence_score.desc()).limit(limit)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [{"finding_id": r.finding_id, "symbol": r.symbol, "category": r.category,
             "title": r.title, "summary": r.summary, "actionable_insight": r.actionable_insight,
             "win_rate": r.win_rate, "avg_return": r.avg_return, "sample_size": r.sample_size,
             "confidence_score": r.confidence_score, "applicable_regimes": r.applicable_regimes} for r in rows]


# ═══════════════════════════════════════════════════════════════
# SUMMARY & LOGS
# ═══════════════════════════════════════════════════════════════

@router.get("/summary", dependencies=[Depends(require_viewer)])
async def research_summary(db: AsyncSession = Depends(get_db)):
    """Summary stats for the research pipeline."""
    hyp_by_status = await db.execute(
        select(ResearchHypothesis.status, func.count(ResearchHypothesis.id))
        .group_by(ResearchHypothesis.status)
    )
    findings_count = await db.execute(
        select(func.count(ResearchFinding.id)).where(ResearchFinding.status == "active")
    )
    avg_win_rate = await db.execute(
        select(func.avg(ResearchFinding.win_rate)).where(ResearchFinding.status == "active")
    )
    return {
        "hypotheses_by_status": {r[0]: r[1] for r in hyp_by_status.all()},
        "active_findings": findings_count.scalar() or 0,
        "avg_finding_win_rate": round(float(avg_win_rate.scalar() or 0), 4),
    }


@router.get("/logs", dependencies=[Depends(require_viewer)])
async def research_logs(
    pipeline_phase: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """View research pipeline execution logs."""
    q = select(ResearchPipelineLog)
    if pipeline_phase:
        q = q.where(ResearchPipelineLog.pipeline_phase == pipeline_phase)
    q = q.order_by(ResearchPipelineLog.started_at.desc()).limit(limit)
    result = await db.execute(q)
    rows = result.scalars().all()
    return [{"id": r.id, "pipeline_phase": r.pipeline_phase, "symbol": r.symbol,
             "status": r.status, "items_generated": r.items_generated,
             "started_at": str(r.started_at), "duration_seconds": r.duration_seconds,
             "error_message": r.error_message} for r in rows]
