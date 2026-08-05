"""
AI-QROS — ML Model Trainer
Phase 16: AI Decision Engine

Implements training and daily incremental updates of LightGBM models
predicting next-day price movement and option premium outcomes.
Uses float32 and strict memory constraints to fit within 512MB RAM.
"""

import os
import time
import pickle
import math
import numpy as np
import pandas as pd
import lightgbm as lgb
import structlog
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Tuple
from sklearn.preprocessing import StandardScaler
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.db.database import AsyncSessionLocal
from app.models.feature_store import ComputedFeatureStore
from app.ml.training_strategy import LIGHTGBM_INCREMENTAL_PARAMS, INCREMENTAL_NUM_BOOST_ROUND

logger = structlog.get_logger("aiqros.ml.trainer")

MODEL_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
os.makedirs(MODEL_DIR, exist_ok=True)

# ── Feature Definition ──
FEATURE_KEYS = [
    "adx_14", "rsi_14", "bb_20_bandwidth", "pcr_oi", "macd_value", 
    "price_daily_return", "vol_ratio_5_20"
]


def _prepare_data(rows: List[Tuple]) -> Tuple[np.ndarray, np.ndarray]:
    """Helper to scale features and create binary target labels (price direction)."""
    X_list = []
    y_list = []
    
    for i in range(len(rows) - 1):
        feat = rows[i][1]
        next_feat = rows[i+1][1]
        
        # Current day features
        vec = []
        for k in FEATURE_KEYS:
            val = feat.get(k)
            vec.append(float(val) if val is not None and not math.isnan(val) else 0.0)
            
        # Target label: 1 if next day return > 0 else 0
        nxt_ret = next_feat.get("price_daily_return") or next_feat.get("daily_return", 0.0)
        label = 1 if nxt_ret > 0 else 0
        
        X_list.append(vec)
        y_list.append(label)
        
    return np.array(X_list, dtype=np.float32), np.array(y_list, dtype=np.float32)


async def train_initial_model(symbol: str, db: AsyncSession) -> str:
    """
    Perform baseline offline-style training on last 90 trading days.
    Fits in Render free tier (90 samples is lightweight).
    """
    start_time = time.time()
    cutoff = date.today() - timedelta(days=120)
    
    result = await db.execute(
        select(ComputedFeatureStore.trade_date, ComputedFeatureStore.features).where(
            and_(
                ComputedFeatureStore.symbol == symbol,
                ComputedFeatureStore.trade_date >= cutoff
            )
        ).order_by(ComputedFeatureStore.trade_date.asc())
    )
    rows = result.all()
    if len(rows) < 15:
        raise ValueError("insufficient_historical_features_for_initial_training")

    X, y = _prepare_data(rows)
    
    train_data = lgb.Dataset(X, label=y)
    
    # Train booster
    booster = lgb.train(
        LIGHTGBM_INCREMENTAL_PARAMS,
        train_data,
        num_boost_round=50
    )
    
    # Save booster artifact
    model_path = os.path.join(MODEL_DIR, f"{symbol}_lgb.pkl")
    with open(model_path, "wb") as f:
        pickle.dump(booster, f)
        
    duration = round(time.time() - start_time, 2)
    logger.info("initial_model_training_completed", symbol=symbol, path=model_path, duration_s=duration)
    return model_path


async def update_model_incrementally(symbol: str, db: AsyncSession) -> str:
    """
    Load existing model booster, fit incremental updates on recent 30-day window,
    and save updated model.
    """
    model_path = os.path.join(MODEL_DIR, f"{symbol}_lgb.pkl")
    if not os.path.exists(model_path):
        logger.info("no_existing_model_found_triggering_initial_train", symbol=symbol)
        return await train_initial_model(symbol, db)
        
    # Fetch recent 30-day window
    cutoff = date.today() - timedelta(days=45)
    result = await db.execute(
        select(ComputedFeatureStore.trade_date, ComputedFeatureStore.features).where(
            and_(
                ComputedFeatureStore.symbol == symbol,
                ComputedFeatureStore.trade_date >= cutoff
            )
        ).order_by(ComputedFeatureStore.trade_date.asc())
    )
    rows = result.all()
    if len(rows) < 5:
        logger.warn("insufficient_recent_data_for_incremental_update", count=len(rows))
        return model_path
        
    X, y = _prepare_data(rows)
    
    # Load existing booster
    with open(model_path, "rb") as f:
        booster = pickle.load(f)
        
    # Fit incrementally
    train_data = lgb.Dataset(X, label=y)
    updated_booster = lgb.train(
        LIGHTGBM_INCREMENTAL_PARAMS,
        train_data,
        num_boost_round=INCREMENTAL_NUM_BOOST_ROUND,
        init_model=booster
    )
    
    # Save updated booster
    with open(model_path, "wb") as f:
        pickle.dump(updated_booster, f)
        
    logger.info("incremental_model_update_completed", symbol=symbol)
    return model_path


async def run_daily_ml_update(trade_date: Optional[date] = None) -> dict:
    """Run daily incremental update pipeline for all models."""
    td = trade_date or date.today()
    results = {}
    async with AsyncSessionLocal() as db:
        for symbol in ["NIFTY", "BANKNIFTY"]:
            try:
                path = await update_model_incrementally(symbol, db)
                results[symbol] = {"status": "success", "artifact_path": path}
            except Exception as e:
                logger.error("ml_model_update_failed", symbol=symbol, error=str(e))
                results[symbol] = {"status": "failed", "error": str(e)}
        await db.commit()
    return {"status": "success", "trade_date": str(td), "updates": results}
