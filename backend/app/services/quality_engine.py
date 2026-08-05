"""
AI-QROS — Data Quality Engine
Phase 3: Data Quality

Runs 6 categories of quality checks on all stored market data:
1. Completeness — null percentages, expected column presence
2. Freshness — stale data detection
3. Consistency — OHLC logic, non-negative volume/OI
4. Duplicates — exact duplicate detection
5. Outliers — Z-score anomaly detection on price/volume
6. Gaps — missing trading days in time series

Each check returns a score (0-100). The overall source score
is a weighted average of all checks.
"""

import time
from datetime import datetime, date, timedelta
from typing import Optional
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text, and_

from app.db.database import AsyncSessionLocal
from app.models.data_quality import DataQualityReport, DataQualityCheck
from app.models.market_data import OptionSettlement, GlobalMarketData, OHLCVCandle

logger = structlog.get_logger("aiqros.services.quality_engine")

# Check category weights for overall score calculation
CHECK_WEIGHTS = {
    "completeness": 0.25,
    "freshness": 0.20,
    "consistency": 0.25,
    "duplicates": 0.10,
    "outliers": 0.10,
    "gaps": 0.10,
}


# ─────────────────────────────────────────────
# INDIVIDUAL CHECK FUNCTIONS
# Each returns: {name, category, status, score, rows_scanned, issues_found, message, details}
# ─────────────────────────────────────────────

async def _check_completeness(db: AsyncSession, source: str) -> list[dict]:
    """Check for null values and missing data in each source table."""
    checks = []

    if source in ("NSE_BHAVCOPY", "ALL"):
        total = (await db.execute(select(func.count(OptionSettlement.id)))).scalar() or 0
        if total == 0:
            checks.append({
                "check_name": "completeness_settlements_empty",
                "check_category": "completeness",
                "status": "warning",
                "score": 0.0,
                "rows_scanned": 0,
                "issues_found": 0,
                "message": "No option settlement data found. Run data ingestion first.",
            })
        else:
            # Check null percentages on critical columns
            null_close = (await db.execute(
                select(func.count()).where(OptionSettlement.close == None)  # noqa: E711
            )).scalar() or 0
            null_oi = (await db.execute(
                select(func.count()).where(OptionSettlement.oi == None)  # noqa: E711
            )).scalar() or 0

            null_pct = round((null_close / total) * 100, 2) if total > 0 else 0
            oi_null_pct = round((null_oi / total) * 100, 2) if total > 0 else 0
            score = max(0, 100 - (null_pct * 10) - (oi_null_pct * 2))

            checks.append({
                "check_name": "completeness_settlements_nulls",
                "check_category": "completeness",
                "status": "passed" if score >= 90 else ("warning" if score >= 70 else "failed"),
                "score": round(score, 1),
                "rows_scanned": total,
                "issues_found": null_close + null_oi,
                "message": f"Close null: {null_pct}%, OI null: {oi_null_pct}% of {total} rows",
                "details": {"null_close_pct": null_pct, "null_oi_pct": oi_null_pct},
            })

    if source in ("YFINANCE", "ALL"):
        total = (await db.execute(select(func.count(GlobalMarketData.id)))).scalar() or 0
        if total == 0:
            checks.append({
                "check_name": "completeness_global_empty",
                "check_category": "completeness",
                "status": "warning",
                "score": 0.0,
                "rows_scanned": 0,
                "issues_found": 0,
                "message": "No global market data found. Run data ingestion first.",
            })
        else:
            null_close = (await db.execute(
                select(func.count()).where(GlobalMarketData.close == None)  # noqa: E711
            )).scalar() or 0
            null_pct = round((null_close / total) * 100, 2) if total > 0 else 0
            score = max(0, 100 - (null_pct * 10))
            checks.append({
                "check_name": "completeness_global_nulls",
                "check_category": "completeness",
                "status": "passed" if score >= 90 else ("warning" if score >= 70 else "failed"),
                "score": round(score, 1),
                "rows_scanned": total,
                "issues_found": null_close,
                "message": f"Close null: {null_pct}% of {total} rows",
            })

    if source in ("ANGEL_ONE", "ALL"):
        total = (await db.execute(select(func.count(OHLCVCandle.id)))).scalar() or 0
        if total == 0:
            checks.append({
                "check_name": "completeness_candles_empty",
                "check_category": "completeness",
                "status": "warning",
                "score": 0.0,
                "rows_scanned": 0,
                "issues_found": 0,
                "message": "No candle data found. Configure Angel One credentials and run ingestion.",
            })
        else:
            score = 100.0
            checks.append({
                "check_name": "completeness_candles_present",
                "check_category": "completeness",
                "status": "passed",
                "score": score,
                "rows_scanned": total,
                "issues_found": 0,
                "message": f"{total} candle rows present",
            })

    return checks


async def _check_freshness(db: AsyncSession, source: str) -> list[dict]:
    """Check if data is stale (last ingestion older than expected)."""
    checks = []
    today = date.today()

    if source in ("NSE_BHAVCOPY", "ALL"):
        result = await db.execute(
            select(func.max(OptionSettlement.trade_date))
        )
        latest = result.scalar()
        if latest is None:
            days_stale = 999
        else:
            days_stale = (today - latest).days

        # Settlements should be at most 3 days old (weekend tolerance)
        score = 100.0 if days_stale <= 3 else max(0, 100 - (days_stale - 3) * 15)
        checks.append({
            "check_name": "freshness_settlements",
            "check_category": "freshness",
            "status": "passed" if days_stale <= 3 else ("warning" if days_stale <= 7 else "failed"),
            "score": round(score, 1),
            "rows_scanned": 1,
            "issues_found": 1 if days_stale > 3 else 0,
            "message": f"Latest settlement: {latest or 'none'} ({days_stale} days ago)",
            "details": {"latest_date": str(latest), "days_stale": days_stale},
        })

    if source in ("YFINANCE", "ALL"):
        result = await db.execute(
            select(func.max(GlobalMarketData.trade_date))
        )
        latest = result.scalar()
        days_stale = (today - latest).days if latest else 999
        score = 100.0 if days_stale <= 3 else max(0, 100 - (days_stale - 3) * 15)
        checks.append({
            "check_name": "freshness_global",
            "check_category": "freshness",
            "status": "passed" if days_stale <= 3 else ("warning" if days_stale <= 7 else "failed"),
            "score": round(score, 1),
            "rows_scanned": 1,
            "issues_found": 1 if days_stale > 3 else 0,
            "message": f"Latest global data: {latest or 'none'} ({days_stale} days ago)",
            "details": {"latest_date": str(latest), "days_stale": days_stale},
        })

    if source in ("ANGEL_ONE", "ALL"):
        result = await db.execute(
            select(func.max(OHLCVCandle.timestamp))
        )
        latest = result.scalar()
        if latest:
            days_stale = (datetime.utcnow() - latest).days
        else:
            days_stale = 999
        score = 100.0 if days_stale <= 3 else max(0, 100 - (days_stale - 3) * 15)
        checks.append({
            "check_name": "freshness_candles",
            "check_category": "freshness",
            "status": "passed" if days_stale <= 3 else ("warning" if days_stale <= 7 else "failed"),
            "score": round(score, 1),
            "rows_scanned": 1,
            "issues_found": 1 if days_stale > 3 else 0,
            "message": f"Latest candle: {latest or 'none'} ({days_stale} days ago)",
            "details": {"latest_timestamp": str(latest), "days_stale": days_stale},
        })

    return checks


async def _check_consistency(db: AsyncSession, source: str) -> list[dict]:
    """Check OHLC logic: High >= Open/Close >= Low, non-negative volume/OI."""
    checks = []

    if source in ("NSE_BHAVCOPY", "ALL"):
        total = (await db.execute(select(func.count(OptionSettlement.id)))).scalar() or 0
        if total > 0:
            # Check: High should be >= Open and Close
            bad_ohlc = (await db.execute(
                select(func.count(OptionSettlement.id)).where(
                    (OptionSettlement.high < OptionSettlement.open) |
                    (OptionSettlement.high < OptionSettlement.close) |
                    (OptionSettlement.low > OptionSettlement.open) |
                    (OptionSettlement.low > OptionSettlement.close)
                )
            )).scalar() or 0

            bad_pct = round((bad_ohlc / total) * 100, 2) if total > 0 else 0
            score = max(0, 100 - (bad_pct * 20))
            checks.append({
                "check_name": "consistency_settlements_ohlc",
                "check_category": "consistency",
                "status": "passed" if bad_pct < 1 else ("warning" if bad_pct < 5 else "failed"),
                "score": round(score, 1),
                "rows_scanned": total,
                "issues_found": bad_ohlc,
                "message": f"OHLC logic violations: {bad_ohlc} rows ({bad_pct}%)",
            })

            # Check: negative OI
            neg_oi = (await db.execute(
                select(func.count(OptionSettlement.id)).where(OptionSettlement.oi < 0)
            )).scalar() or 0
            score_oi = 100.0 if neg_oi == 0 else max(0, 100 - (neg_oi / total * 100 * 20))
            checks.append({
                "check_name": "consistency_settlements_negative_oi",
                "check_category": "consistency",
                "status": "passed" if neg_oi == 0 else "failed",
                "score": round(score_oi, 1),
                "rows_scanned": total,
                "issues_found": neg_oi,
                "message": f"Negative OI rows: {neg_oi}",
            })

    if source in ("ANGEL_ONE", "ALL"):
        total = (await db.execute(select(func.count(OHLCVCandle.id)))).scalar() or 0
        if total > 0:
            bad_ohlc = (await db.execute(
                select(func.count(OHLCVCandle.id)).where(
                    (OHLCVCandle.high < OHLCVCandle.open) |
                    (OHLCVCandle.high < OHLCVCandle.close) |
                    (OHLCVCandle.low > OHLCVCandle.open) |
                    (OHLCVCandle.low > OHLCVCandle.close)
                )
            )).scalar() or 0
            bad_pct = round((bad_ohlc / total) * 100, 2) if total > 0 else 0
            score = max(0, 100 - (bad_pct * 20))
            checks.append({
                "check_name": "consistency_candles_ohlc",
                "check_category": "consistency",
                "status": "passed" if bad_pct < 1 else ("warning" if bad_pct < 5 else "failed"),
                "score": round(score, 1),
                "rows_scanned": total,
                "issues_found": bad_ohlc,
                "message": f"OHLC logic violations: {bad_ohlc} candle rows ({bad_pct}%)",
            })

    return checks


async def _check_duplicates(db: AsyncSession, source: str) -> list[dict]:
    """Detect duplicate rows that slipped past unique constraints."""
    checks = []

    if source in ("YFINANCE", "ALL"):
        total = (await db.execute(select(func.count(GlobalMarketData.id)))).scalar() or 0
        if total > 0:
            distinct_count = (await db.execute(
                select(func.count()).select_from(
                    select(
                        GlobalMarketData.trade_date,
                        GlobalMarketData.factor_name
                    ).distinct().subquery()
                )
            )).scalar() or 0
            dupes = total - distinct_count
            score = 100.0 if dupes == 0 else max(0, 100 - (dupes / total * 100 * 10))
            checks.append({
                "check_name": "duplicates_global",
                "check_category": "duplicates",
                "status": "passed" if dupes == 0 else "warning",
                "score": round(score, 1),
                "rows_scanned": total,
                "issues_found": dupes,
                "message": f"Duplicate global rows: {dupes} of {total}",
            })

    if source in ("NSE_BHAVCOPY", "ALL"):
        total = (await db.execute(select(func.count(OptionSettlement.id)))).scalar() or 0
        if total > 0:
            distinct_count = (await db.execute(
                select(func.count()).select_from(
                    select(
                        OptionSettlement.trade_date,
                        OptionSettlement.underlying,
                        OptionSettlement.expiry_date,
                        OptionSettlement.strike,
                        OptionSettlement.option_type,
                    ).distinct().subquery()
                )
            )).scalar() or 0
            dupes = total - distinct_count
            score = 100.0 if dupes == 0 else max(0, 100 - (dupes / total * 100 * 10))
            checks.append({
                "check_name": "duplicates_settlements",
                "check_category": "duplicates",
                "status": "passed" if dupes == 0 else "warning",
                "score": round(score, 1),
                "rows_scanned": total,
                "issues_found": dupes,
                "message": f"Duplicate settlement rows: {dupes} of {total}",
            })

    return checks


async def _check_outliers(db: AsyncSession, source: str) -> list[dict]:
    """Detect statistical outliers using Z-score (> 3 std dev from mean)."""
    checks = []

    if source in ("YFINANCE", "ALL"):
        # Check outliers in global close prices per factor
        result = await db.execute(text("""
            SELECT COUNT(*) as outlier_count, COUNT(*) FILTER (WHERE 1=1) as total FROM (
                SELECT close,
                    AVG(close) OVER (PARTITION BY factor_name) as avg_close,
                    STDDEV(close) OVER (PARTITION BY factor_name) as std_close
                FROM global_market_data
                WHERE close IS NOT NULL
            ) sub
            WHERE std_close > 0 AND ABS(close - avg_close) > 3 * std_close
        """))
        row = result.fetchone()
        if row:
            outliers = row[0] or 0
            total = (await db.execute(
                select(func.count(GlobalMarketData.id)).where(GlobalMarketData.close != None)  # noqa: E711
            )).scalar() or 1
            score = 100.0 if outliers == 0 else max(0, 100 - (outliers / total * 100 * 5))
            checks.append({
                "check_name": "outliers_global_close",
                "check_category": "outliers",
                "status": "passed" if outliers == 0 else ("warning" if outliers < 10 else "failed"),
                "score": round(score, 1),
                "rows_scanned": total,
                "issues_found": outliers,
                "message": f"Close price outliers (Z>3): {outliers} of {total} rows",
            })

    return checks


async def _check_gaps(db: AsyncSession, source: str) -> list[dict]:
    """Detect missing trading days in time series."""
    checks = []

    if source in ("NSE_BHAVCOPY", "ALL"):
        result = await db.execute(
            select(
                func.min(OptionSettlement.trade_date),
                func.max(OptionSettlement.trade_date),
            )
        )
        row = result.fetchone()
        if row and row[0] and row[1]:
            min_date, max_date = row[0], row[1]
            # Count distinct trading days present
            distinct_days = (await db.execute(
                select(func.count(OptionSettlement.trade_date.distinct()))
            )).scalar() or 0

            # Estimate expected trading days (weekdays minus ~15 holidays/year)
            total_days = (max_date - min_date).days
            expected_trading_days = max(1, int(total_days * 5 / 7) - int(total_days / 365 * 15))
            missing = max(0, expected_trading_days - distinct_days)
            gap_pct = round((missing / expected_trading_days) * 100, 1) if expected_trading_days > 0 else 0
            score = max(0, 100 - gap_pct * 2)

            checks.append({
                "check_name": "gaps_settlements_trading_days",
                "check_category": "gaps",
                "status": "passed" if gap_pct < 5 else ("warning" if gap_pct < 15 else "failed"),
                "score": round(score, 1),
                "rows_scanned": distinct_days,
                "issues_found": missing,
                "message": f"Trading days present: {distinct_days}, expected ~{expected_trading_days}, missing ~{missing} ({gap_pct}%)",
                "details": {
                    "date_range": f"{min_date} to {max_date}",
                    "days_present": distinct_days,
                    "days_expected": expected_trading_days,
                    "days_missing": missing,
                },
            })

    return checks


# ─────────────────────────────────────────────
# MAIN QUALITY CHECK RUNNER
# ─────────────────────────────────────────────

async def run_quality_checks(
    source: str = "ALL",
    triggered_by: str = "scheduler",
) -> dict:
    """
    Run all quality checks for a given source (or all sources).
    Creates a DataQualityReport with individual DataQualityCheck entries.
    Returns summary dict.
    """
    start_time = time.time()

    async with AsyncSessionLocal() as db:
        # Collect all checks
        all_checks = []
        all_checks.extend(await _check_completeness(db, source))
        all_checks.extend(await _check_freshness(db, source))
        all_checks.extend(await _check_consistency(db, source))
        all_checks.extend(await _check_duplicates(db, source))
        all_checks.extend(await _check_outliers(db, source))
        all_checks.extend(await _check_gaps(db, source))

        if not all_checks:
            return {
                "status": "no_data",
                "message": "No data to check. Run data ingestion first.",
                "overall_score": 0,
            }

        # Calculate overall score (weighted average by category)
        category_scores = {}
        for check in all_checks:
            cat = check["check_category"]
            if cat not in category_scores:
                category_scores[cat] = []
            category_scores[cat].append(check["score"])

        weighted_sum = 0.0
        total_weight = 0.0
        for cat, scores in category_scores.items():
            weight = CHECK_WEIGHTS.get(cat, 0.1)
            avg_score = sum(scores) / len(scores) if scores else 0
            weighted_sum += avg_score * weight
            total_weight += weight

        overall_score = round(weighted_sum / total_weight, 1) if total_weight > 0 else 0.0

        # Count statuses
        passed = sum(1 for c in all_checks if c.get("status") == "passed")
        failed = sum(1 for c in all_checks if c.get("status") == "failed")
        warning = sum(1 for c in all_checks if c.get("status") == "warning")
        total_rows = sum(c.get("rows_scanned", 0) for c in all_checks)
        total_issues = sum(c.get("issues_found", 0) for c in all_checks)

        duration = round(time.time() - start_time, 2)

        # Create report
        report = DataQualityReport(
            source=source,
            overall_score=overall_score,
            total_checks=len(all_checks),
            checks_passed=passed,
            checks_failed=failed,
            checks_warning=warning,
            total_rows_scanned=total_rows,
            total_issues_found=total_issues,
            run_at=datetime.utcnow(),
            duration_seconds=duration,
            triggered_by=triggered_by,
            details={"category_scores": {k: round(sum(v)/len(v), 1) for k, v in category_scores.items()}},
        )
        db.add(report)
        await db.flush()

        # Create individual check records
        for check_data in all_checks:
            check = DataQualityCheck(
                report_id=report.id,
                check_name=check_data["check_name"],
                check_category=check_data["check_category"],
                status=check_data["status"],
                score=check_data["score"],
                rows_scanned=check_data.get("rows_scanned", 0),
                issues_found=check_data.get("issues_found", 0),
                message=check_data.get("message"),
                details=check_data.get("details"),
            )
            db.add(check)

        await db.commit()

        logger.info(
            "quality_checks_complete",
            source=source,
            overall_score=overall_score,
            total_checks=len(all_checks),
            passed=passed,
            failed=failed,
            warning=warning,
            duration_s=duration,
        )

        return {
            "status": "complete",
            "report_id": report.id,
            "source": source,
            "overall_score": overall_score,
            "total_checks": len(all_checks),
            "checks_passed": passed,
            "checks_failed": failed,
            "checks_warning": warning,
            "total_issues": total_issues,
            "duration_seconds": duration,
        }


async def get_latest_scores() -> dict:
    """Get the latest quality score for each data source."""
    async with AsyncSessionLocal() as db:
        scores = {}
        for source in ["NSE_BHAVCOPY", "YFINANCE", "ANGEL_ONE", "ALL"]:
            result = await db.execute(
                select(DataQualityReport)
                .where(DataQualityReport.source == source)
                .order_by(DataQualityReport.run_at.desc())
                .limit(1)
            )
            report = result.scalar_one_or_none()
            if report:
                scores[source] = {
                    "overall_score": report.overall_score,
                    "checks_passed": report.checks_passed,
                    "checks_failed": report.checks_failed,
                    "checks_warning": report.checks_warning,
                    "run_at": report.run_at.isoformat(),
                }
            else:
                scores[source] = None

        return scores
