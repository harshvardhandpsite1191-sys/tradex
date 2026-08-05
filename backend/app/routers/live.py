"""
AI-QROS — Intraday Live Engine Router
Phase 20: Live Engine
"""

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional, List, Dict
from app.auth.auth import require_admin, require_viewer

router = APIRouter(prefix="/live", tags=["Intraday Live Engine"])


@router.post("/start", dependencies=[Depends(require_admin)])
async def start_live_stream():
    """Start streaming options tick data."""
    from app.services.live_engine import live_engine_instance
    live_engine_instance.start_engine()
    return {"status": "success", "message": "Live engine started."}


@router.post("/stop", dependencies=[Depends(require_admin)])
async def stop_live_stream():
    """Stop streaming options tick data."""
    from app.services.live_engine import live_engine_instance
    live_engine_instance.stop_engine()
    return {"status": "success", "message": "Live engine stopped."}


@router.get("/status", dependencies=[Depends(require_viewer)])
async def get_live_status():
    """Get active status of WebSocket stream."""
    from app.services.live_engine import live_engine_instance
    return {
        "is_active": live_engine_instance.is_active,
        "last_price": live_engine_instance.last_tick_price,
        "vwap": round(live_engine_instance.rolling_vwap, 2),
        "tick_count": live_engine_instance.tick_count
    }


@router.post("/simulate", dependencies=[Depends(require_admin)])
async def run_live_feed_simulation(seconds: int = 10):
    """Simulate 10 seconds of options ticks."""
    from app.services.live_engine import run_live_simulation
    ticks = await run_live_simulation(seconds)
    return {"status": "simulation_complete", "ticks_count": len(ticks), "ticks": ticks}
