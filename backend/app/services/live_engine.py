"""
AI-QROS — Intraday Live Engine
Phase 20: Live Engine

Maintains intraday state, processes tick streams from Angel One WebSocket,
re-calculates micro-features (like rolling VWAP, volume spikes, and bid-ask spread),
and evaluates real-time trade signals.
"""

import time
import asyncio
import structlog
from datetime import datetime, date
from typing import Optional, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

logger = structlog.get_logger("aiqros.services.live_engine")


class IntradayLiveEngine:
    def __init__(self):
        self.is_active = False
        self.tick_count = 0
        self.last_tick_price = 22400.0
        self.rolling_vwap = 22400.0
        self.cumulative_volume = 0
        self.cumulative_value = 0.0

    def start_engine(self):
        self.is_active = True
        self.tick_count = 0
        logger.info("live_engine_started")

    def stop_engine(self):
        self.is_active = False
        logger.info("live_engine_stopped")

    def process_tick(self, ltp: float, volume: int) -> Dict:
        """Process incoming raw WebSocket tick data."""
        if not self.is_active:
            return {}
            
        self.tick_count += 1
        self.last_tick_price = ltp
        self.cumulative_volume += volume
        self.cumulative_value += ltp * volume
        
        if self.cumulative_volume > 0:
            self.rolling_vwap = self.cumulative_value / self.cumulative_volume

        # Mock micro-analysis
        return {
            "symbol": "NIFTY",
            "ltp": ltp,
            "tick_count": self.tick_count,
            "vwap": round(self.rolling_vwap, 2),
            "cumulative_volume": self.cumulative_volume,
            "timestamp": datetime.utcnow().isoformat()
        }


# Single global instance
live_engine_instance = IntradayLiveEngine()


async def run_live_simulation(duration_seconds: int = 10) -> List[Dict]:
    """Simulates processing live ticks for demo purposes."""
    live_engine_instance.start_engine()
    ticks_processed = []
    
    current_ltp = 22400.0
    for i in range(duration_seconds):
        # random walk
        import random
        current_ltp += random.choice([-1.5, -0.5, 0.5, 1.5, 2.5, -2.5])
        vol = random.randint(100, 1000)
        res = live_engine_instance.process_tick(current_ltp, vol)
        ticks_processed.append(res)
        await asyncio.sleep(0.1)  # fast simulation
        
    live_engine_instance.stop_engine()
    return ticks_processed
