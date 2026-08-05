"""
AI-QROS — ML Model Predictor
Phase 16: AI Decision Engine

Loads saved LightGBM model boosters to predict the probability of next-day positive returns.
"""

import os
import pickle
import math
import numpy as np
import pandas as pd
import lightgbm as lgb
import structlog
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.models.feature_store import ComputedFeatureStore
from app.ml.trainer import FEATURE_KEYS, MODEL_DIR

logger = structlog.get_logger("aiqros.ml.predictor")


async def predict_next_day_direction(
    symbol: str,
    trade_date: date,
    db: AsyncSession
) -> Tuple[float, float]:
    """
    Predict next-day direction probability.
    Returns (probability_up, probability_down).
    """
    model_path = os.path.join(MODEL_DIR, f"{symbol}_lgb.pkl")
    if not os.path.exists(model_path):
        logger.info("model_booster_not_found_using_heuristic_probability", symbol=symbol)
        # Fallback heuristic
        return 0.52, 0.48

    # 1. Fetch target date's feature vector
    feat_q = select(ComputedFeatureStore.features).where(
        and_(
            ComputedFeatureStore.symbol == symbol,
            ComputedFeatureStore.trade_date == trade_date
        )
    ).order_by(ComputedFeatureStore.computation_version.desc()).limit(1)
    
    feat_res = await db.execute(feat_q)
    features = feat_res.scalar_one_or_none()
    
    if not features:
        logger.warn("no_features_found_for_target_prediction_date", symbol=symbol, trade_date=str(trade_date))
        return 0.50, 0.50

    # 2. Extract feature values in exact sequence matching model columns
    vec = []
    for k in FEATURE_KEYS:
        val = features.get(k)
        vec.append(float(val) if val is not None and not math.isnan(val) else 0.0)

    X = np.array([vec], dtype=np.float32)

    # 3. Load model and predict
    try:
        with open(model_path, "rb") as f:
            booster = pickle.load(f)
            
        prob_up = float(booster.predict(X)[0])
        prob_down = 1.0 - prob_up
        
        logger.info("prediction_completed", symbol=symbol, prob_up=round(prob_up, 4))
        return prob_up, prob_down
    except Exception as e:
        logger.error("prediction_failed", symbol=symbol, error=str(e))
        return 0.52, 0.48
