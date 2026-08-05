"""
AI-QROS — Historical Similarity Engine
Phase 14: Historical Similarity (Pattern Matching)

Calculates multi-dimensional distance/similarity between the current day's feature vector
and historical days using Cosine Similarity and K-Nearest Neighbors (KNN) to find similar historical days.
"""

import time
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Tuple
import structlog
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler
from sklearn.neighbors import NearestNeighbors
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.database import AsyncSessionLocal
from app.models.feature_store import ComputedFeatureStore

logger = structlog.get_logger("aiqros.services.similarity_engine")


def calculate_cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    """Helper to calculate cosine similarity between two vectors."""
    dot = np.dot(v1, v2)
    norm_a = np.linalg.norm(v1)
    norm_b = np.linalg.norm(v2)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(dot / (norm_a * norm_b))


async def find_similar_dates(
    symbol: str,
    target_date: date,
    db: AsyncSession,
    top_n: int = 5,
    lookback_days: int = 500
) -> List[Dict]:
    """
    Find top-N historical dates that have the most similar feature vector to target_date.
    Uses K-Nearest Neighbors (KNN) Euclidean distance and Cosine Similarity.
    """
    cutoff = target_date - timedelta(days=lookback_days)
    
    # 1. Fetch historical feature store data
    feat_q = select(ComputedFeatureStore.trade_date, ComputedFeatureStore.features).where(
        and_(
            ComputedFeatureStore.symbol == symbol,
            ComputedFeatureStore.trade_date >= cutoff,
            ComputedFeatureStore.trade_date <= target_date
        )
    ).order_by(ComputedFeatureStore.trade_date.asc())
    
    feat_res = await db.execute(feat_q)
    rows = feat_res.all()
    if len(rows) < 10:
        logger.warn("insufficient_historical_features_for_similarity", count=len(rows))
        return []

    # Features to use for similarity vector matching
    feature_keys = [
        "adx_14", "rsi_14", "bb_20_bandwidth", "pcr_oi", "macd_value", 
        "price_daily_return", "vol_ratio_5_20"
    ]

    dates_list = []
    vectors = []
    
    target_vector = None
    
    for dt, feat in rows:
        vec = []
        for k in feature_keys:
            val = feat.get(k)
            # handle NaN/None
            vec.append(float(val) if val is not None and not math.isnan(val) else 0.0)
            
        if dt == target_date:
            target_vector = np.array(vec)
        else:
            dates_list.append(dt)
            vectors.append(vec)

    if target_vector is None:
        logger.warn("target_date_not_found_in_feature_store", target_date=str(target_date))
        return []

    X = np.array(vectors)
    
    # Scale vectors
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)
    target_scaled = scaler.transform(target_vector.reshape(1, -1))

    # K-Nearest Neighbors
    nn = NearestNeighbors(n_neighbors=min(top_n * 2, len(dates_list)), metric="euclidean")
    nn.fit(X_scaled)
    
    distances, indices = nn.kneighbors(target_scaled)
    
    results = []
    for idx, dist in zip(indices[0], distances[0]):
        hist_dt = dates_list[idx]
        hist_vec = X[idx]
        
        # Calculate Cosine Similarity
        cosine_sim = calculate_cosine_similarity(target_vector, hist_vec)
        
        # Load next-day return of the historical date to see how the market behaved subsequently
        hist_nxt_q = select(ComputedFeatureStore.features).where(
            and_(
                ComputedFeatureStore.symbol == symbol,
                ComputedFeatureStore.trade_date > hist_dt
            )
        ).order_by(ComputedFeatureStore.trade_date.asc()).limit(1)
        hist_nxt_res = await db.execute(hist_nxt_q)
        hist_nxt_feat = hist_nxt_res.scalar_one_or_none()
        nxt_ret = hist_nxt_feat.get("price_daily_return") if hist_nxt_feat else 0.0

        results.append({
            "trade_date": str(hist_dt),
            "distance": float(dist),
            "cosine_similarity": float(cosine_sim),
            "subsequent_return": float(nxt_ret) if nxt_ret else 0.0
        })

    # Sort primarily by Cosine Similarity desc
    results.sort(key=lambda x: x["cosine_similarity"], reverse=True)
    return results[:top_n]


async def run_similarity_analysis(
    trade_date: Optional[date] = None
) -> dict:
    """Run daily pattern matching similarity check."""
    td = trade_date or date.today()
    results = {}
    async with AsyncSessionLocal() as db:
        for symbol in ["NIFTY", "BANKNIFTY"]:
            similar = await find_similar_dates(symbol, td, db)
            results[symbol] = similar
    return {"status": "success", "trade_date": str(td), "similarity_results": results}
