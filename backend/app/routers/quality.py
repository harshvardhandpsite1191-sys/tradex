"""
AI-QROS — Data Quality API Router
Phase 3: Data Quality & Governance
Endpoints for running quality checks, viewing reports, and monitoring data health.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
from app.db.database import get_db
from app.models.data_quality import DataQualityReport, DataQualityCheck
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/quality", tags=["Data Quality"])


# ─────────────────────────────────────────────
# Response Schemas
# ─────────────────────────────────────────────

class QualityCheckResponse(BaseModel):
    id: str
    check_name: str
    check_category: str
    status: str
    score: float
    rows_scanned: int
    issues_found: int
    message: Optional[str]
    details: Optional[dict]

    class Config:
        from_attributes = True


class QualityReportResponse(BaseModel):
    id: str
    source: str
    overall_score: float
    total_checks: int
    checks_passed: int
    checks_failed: int
    checks_warning: int
    total_rows_scanned: int
    total_issues_found: int
    run_at: datetime
    duration_seconds: Optional[float]
    triggered_by: str
    details: Optional[dict]

    class Config:
        from_attributes = True


class QualityReportDetailResponse(QualityReportResponse):
    checks: List[QualityCheckResponse]

    class Config:
        from_attributes = True


class RunQualityRequest(BaseModel):
    source: str = "ALL"  # NSE_BHAVCOPY, YFINANCE, ANGEL_ONE, ALL


class RunQualityResponse(BaseModel):
    status: str
    report_id: Optional[str] = None
    source: str
    overall_score: float
    total_checks: int
    checks_passed: int
    checks_failed: int
    checks_warning: int
    total_issues: int
    duration_seconds: float
    message: Optional[str] = None
    task_id: Optional[str] = None


class LatestScoresResponse(BaseModel):
    scores: dict


# ═══════════════════════════════════════════════════════════════
# TRIGGER QUALITY CHECKS (Admin only)
# ═══════════════════════════════════════════════════════════════

@router.post("/run", response_model=RunQualityResponse,
             dependencies=[Depends(require_admin)])
async def run_quality_checks(request: RunQualityRequest):
    """
    Run quality checks synchronously for a given data source.
    Returns the complete report summary immediately.
    Source options: NSE_BHAVCOPY, YFINANCE, ANGEL_ONE, ALL
    """
    valid_sources = {"NSE_BHAVCOPY", "YFINANCE", "ANGEL_ONE", "ALL"}
    source = request.source.upper()
    if source not in valid_sources:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source '{request.source}'. Must be one of: {', '.join(valid_sources)}"
        )

    from app.services.quality_engine import run_quality_checks as _run_checks
    result = await _run_checks(source=source, triggered_by="manual")
    return RunQualityResponse(**result)


@router.post("/run/async", dependencies=[Depends(require_admin)])
async def run_quality_checks_async(request: RunQualityRequest):
    """
    Dispatch quality checks as a background Celery task.
    Returns task_id for tracking.
    """
    valid_sources = {"NSE_BHAVCOPY", "YFINANCE", "ANGEL_ONE", "ALL"}
    source = request.source.upper()
    if source not in valid_sources:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid source '{request.source}'. Must be one of: {', '.join(valid_sources)}"
        )

    from celery_tasks.quality_tasks import run_quality_checks_task
    task = run_quality_checks_task.delay(source)
    return {
        "status": "accepted",
        "message": f"Quality checks dispatched for source: {source}",
        "task_id": task.id,
    }


# ═══════════════════════════════════════════════════════════════
# QUERY REPORTS (Viewer+)
# ═══════════════════════════════════════════════════════════════

@router.get("/reports", response_model=List[QualityReportResponse],
            dependencies=[Depends(require_viewer)])
async def list_quality_reports(
    source: Optional[str] = Query(None, description="Filter: NSE_BHAVCOPY, YFINANCE, ANGEL_ONE, ALL"),
    limit: int = Query(20, le=100),
    offset: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    """List quality reports, most recent first."""
    query = select(DataQualityReport)

    if source:
        query = query.where(DataQualityReport.source == source.upper())

    query = query.order_by(DataQualityReport.run_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    return result.scalars().all()


@router.get("/reports/{report_id}", response_model=QualityReportDetailResponse,
            dependencies=[Depends(require_viewer)])
async def get_quality_report(
    report_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get a single quality report with all individual check results."""
    result = await db.execute(
        select(DataQualityReport).where(DataQualityReport.id == report_id)
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # Eagerly load checks
    checks_result = await db.execute(
        select(DataQualityCheck).where(DataQualityCheck.report_id == report_id)
    )
    checks = checks_result.scalars().all()

    return QualityReportDetailResponse(
        id=report.id,
        source=report.source,
        overall_score=report.overall_score,
        total_checks=report.total_checks,
        checks_passed=report.checks_passed,
        checks_failed=report.checks_failed,
        checks_warning=report.checks_warning,
        total_rows_scanned=report.total_rows_scanned,
        total_issues_found=report.total_issues_found,
        run_at=report.run_at,
        duration_seconds=report.duration_seconds,
        triggered_by=report.triggered_by,
        details=report.details,
        checks=[QualityCheckResponse.model_validate(c) for c in checks],
    )


@router.get("/latest", response_model=LatestScoresResponse,
            dependencies=[Depends(require_viewer)])
async def get_latest_quality_scores():
    """Get the latest quality score for each data source."""
    from app.services.quality_engine import get_latest_scores
    scores = await get_latest_scores()
    return LatestScoresResponse(scores=scores)


@router.get("/checks", response_model=List[QualityCheckResponse],
            dependencies=[Depends(require_viewer)])
async def list_quality_checks(
    category: Optional[str] = Query(None, description="Filter: completeness, freshness, consistency, duplicates, outliers, gaps"),
    status: Optional[str] = Query(None, description="Filter: passed, failed, warning"),
    report_id: Optional[str] = Query(None, description="Filter by report ID"),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
):
    """Query individual quality check results across reports."""
    query = select(DataQualityCheck)

    if category:
        query = query.where(DataQualityCheck.check_category == category.lower())
    if status:
        query = query.where(DataQualityCheck.status == status.lower())
    if report_id:
        query = query.where(DataQualityCheck.report_id == report_id)

    # Join to report to sort by run_at
    query = query.join(DataQualityReport).order_by(
        DataQualityReport.run_at.desc()
    ).limit(limit)

    result = await db.execute(query)
    return result.scalars().all()
