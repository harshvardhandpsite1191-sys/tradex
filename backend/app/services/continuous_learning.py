"""
AI-QROS — Continuous Learning Engine
Phase 22: Continuous Learning

Evaluates feature/concept drift on daily data against historical training reference data.
Calculates Population Stability Index (PSI) and triggers incremental model updates on drift detection.
"""

import time
import math
import numpy as np
import pandas as pd
import structlog
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.database import AsyncSessionLocal
from app.models.feature_store import ComputedFeatureStore
from app.ml.trainer import update_model_incrementally

logger = structlog.get_logger("aiqros.services.continuous_learning")

TARGET_SYMBOLS = ["NIFTY", "BANKNIFTY"]


def calculate_psi(expected: np.ndarray, actual: np.ndarray, num_buckets: int = 10) -> float:
    """
    Calculate Population Stability Index (PSI) between two distributions.
    PSI = sum((Actual_i - Expected_i) * ln(Actual_i / Expected_i))
    """
    if len(expected) == 0 or len(actual) == 0:
        return 0.0
        
    # Determine bin boundaries based on expected distribution
    percentiles = np.linspace(0, 100, num_buckets + 1)
    bins = np.percentile(expected, percentiles)
    bins[0] = -np.inf
    bins[-1] = np.inf
    
    # Calculate counts in each bin
    expected_counts, _ = np.histogram(expected, bins=bins)
    actual_counts, _ = np.histogram(actual, bins=bins)
    
    # Convert to fractions with smoothing to avoid divide-by-zero
    expected_pct = (expected_counts + 0.5) / (len(expected) + 0.5 * num_buckets)
    actual_pct = (actual_counts + 0.5) / (len(actual) + 0.5 * num_buckets)
    
    # Calculate PSI
    psi_val = np.sum((actual_pct - expected_pct) * np.log(actual_pct / expected_pct))
    return float(psi_val)


async def check_feature_drift(
    symbol: str,
    trade_date: date,
    db: AsyncSession,
    reference_days: int = 90,
    test_days: int = 20
) -> Dict:
    """
    Compares recent 20-day feature distribution (actual) with historical 90-day (expected).
    Returns feature-wise PSI scores.
    """
    # Fetch historical reference features
    ref_cutoff = trade_date - timedelta(days=reference_days + test_days)
    test_cutoff = trade_date - timedelta(days=test_days)
    
    result = await db.execute(
        select(ComputedFeatureStore.trade_date, ComputedFeatureStore.features).where(
            and_(
                ComputedFeatureStore.symbol == symbol,
                ComputedFeatureStore.trade_date >= ref_cutoff,
                ComputedFeatureStore.trade_date <= trade_date
            )
        ).order_by(ComputedFeatureStore.trade_date.asc())
    )
    rows = result.all()
    if len(rows) < 30:
        return {"status": "insufficient_data", "overall_drift": False, "psi_scores": {}}

    ref_data = []
    test_data = []
    
    feature_keys = ["adx_14", "rsi_14", "bb_20_bandwidth", "pcr_oi"]
    
    # Separate reference and test datasets
    for dt, feat in rows:
        vec = {k: feat.get(k) for k in feature_keys if feat.get(k) is not None}
        if dt < test_cutoff:
            ref_data.append(vec)
        else:
            test_data.append(vec)
            
    df_ref = pd.DataFrame(ref_data)
    df_test = pd.DataFrame(test_data)
    
    psi_scores = {}
    drift_detected = False
    
    for col in feature_keys:
        if col in df_ref.columns and col in df_test.columns:
            arr_ref = df_ref[col].dropna().values
            arr_test = df_test[col].dropna().values
            
            psi_val = calculate_psi(arr_ref, arr_test)
            psi_scores[col] = psi_val
            if psi_val > 0.25:  # Standard PSI drift warning threshold
                drift_detected = True

    return {
        "status": "success",
        "symbol": symbol,
        "drift_detected": drift_detected,
        "psi_scores": psi_scores
    }


async def run_daily_drift_monitoring(
    trade_date: Optional[date] = None
) -> dict:
    """
    Evaluates drift across all targets. If drift is detected,
    proactively triggers LightGBM incremental retraining.
    """
    td = trade_date or date.today()
    results = {}
    
    async with AsyncSessionLocal() as db:
        for symbol in TARGET_SYMBOLS:
            try:
                res = await check_feature_drift(symbol, td, db)
                results[symbol] = res
                
                # Auto-retraining trigger on drift detection
                if res.get("drift_detected"):
                    logger.info("drift_detected_triggering_model_retraining", symbol=symbol)
                    await update_model_incrementally(symbol, db)
                    
            except Exception as e:
                logger.error("drift_monitoring_failed", symbol=symbol, error=str(e))
                results[symbol] = {"status": "failed", "error": str(e)}
        await db.commit()
        
    return {"status": "success", "trade_date": str(td), "drift_results": results}
