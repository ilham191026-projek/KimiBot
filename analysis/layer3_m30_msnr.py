"""
Layer 3 — M30 MSNR (Mean Session Night Range) Wick Detection + Liquidity Sweep
Detects wick patterns outside the Asian session range that indicate liquidity grabs.
"""

from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from utils.logger import get_logger
from utils.time_utils import now_gmt

logger = get_logger(__name__)


def detect_asian_range(df: pd.DataFrame) -> Dict:
    """
    Detect the Asian session range (20:00-00:00 GMT) from recent data.
    Returns the high, low, and midpoint of the Asian range.
    """
    if len(df) < 48:  # Need at least ~24 hours of M30 data
        return {"high": None, "low": None, "mid": None}
    
    # Use the last 48 candles (24 hours) to find Asian session
    recent = df.tail(48)
    
    asian_high = recent["high"].max()
    asian_low = recent["low"].min()
    asian_mid = (asian_high + asian_low) / 2
    
    return {
        "high": float(asian_high),
        "low": float(asian_low),
        "mid": float(asian_mid),
        "range": float(asian_high - asian_low),
    }


def detect_msnr_wicks(df: pd.DataFrame, asian_range: Dict) -> Dict:
    """
    Detect MSNR wick patterns — price wicking beyond Asian range highs/lows.
    
    Bullish MSNR: Price sweeps below Asian low (takes SSL) with long lower wick
    Bearish MSNR: Price sweeps above Asian high (takes BSL) with long upper wick
    
    Returns dict with sweep detection results.
    """
    if asian_range["high"] is None or len(df) < 5:
        return {"found": False, "reason": "insufficient_data"}
    
    # Look at recent candles (closed only - exclude last)
    recent = df.iloc[:-1].tail(10)
    
    bullish_sweeps = []
    bearish_sweeps = []
    
    for i in range(len(recent)):
        candle = recent.iloc[i]
        
        # Calculate wick sizes
        upper_wick = candle["high"] - max(candle["open"], candle["close"])
        lower_wick = min(candle["open"], candle["close"]) - candle["low"]
        body = abs(candle["close"] - candle["open"])
        
        # Bullish MSNR: sweep below Asian low with long lower wick
        if candle["low"] < asian_range["low"]:
            wick_ratio = lower_wick / (body + 1e-10)
            if wick_ratio > 1.5:  # Lower wick is 1.5x the body
                bullish_sweeps.append({
                    "type": "bullish_msnr",
                    "candle_index": i,
                    "sweep_level": float(candle["low"]),
                    "asian_low": float(asian_range["low"]),
                    "sweep_depth": float(asian_range["low"] - candle["low"]),
                    "lower_wick": float(lower_wick),
                    "body": float(body),
                    "wick_ratio": float(wick_ratio),
                })
        
        # Bearish MSNR: sweep above Asian high with long upper wick
        if candle["high"] > asian_range["high"]:
            wick_ratio = upper_wick / (body + 1e-10)
            if wick_ratio > 1.5:
                bearish_sweeps.append({
                    "type": "bearish_msnr",
                    "candle_index": i,
                    "sweep_level": float(candle["high"]),
                    "asian_high": float(asian_range["high"]),
                    "sweep_depth": float(candle["high"] - asian_range["high"]),
                    "upper_wick": float(upper_wick),
                    "body": float(body),
                    "wick_ratio": float(wick_ratio),
                })
    
    # Prefer the most recent sweep
    result = {"found": False}
    
    if bullish_sweeps:
        best = min(bullish_sweeps, key=lambda x: x["candle_index"])
        result = {
            "found": True,
            "type": "bullish_msnr",
            "sweep": best,
            "all_sweeps": bullish_sweeps,
        }
    
    if bearish_sweeps:
        best = min(bearish_sweeps, key=lambda x: x["candle_index"])
        # Prefer the most recent between bullish and bearish
        if not result["found"] or best["candle_index"] <= result["sweep"]["candle_index"]:
            result = {
                "found": True,
                "type": "bearish_msnr",
                "sweep": best,
                "all_sweeps": bearish_sweeps,
            }
    
    return result


def analyze_m30_msnr(pair: str, df: pd.DataFrame) -> Dict:
    """
    Main entry for M30 MSNR analysis.
    
    Args:
        pair: Instrument symbol
        df: M30 OHLCV DataFrame
        
    Returns:
        Dict with MSNR sweep detection results
    """
    if df is None or len(df) < 48:
        logger.warning("Insufficient M30 data for %s (need 48+, got %d)", pair, len(df) if df is not None else 0)
        return {"valid": False, "reason": "insufficient_data", "pair": pair, "timeframe": "M30"}
    
    asian_range = detect_asian_range(df)
    msnr = detect_msnr_wicks(df, asian_range)
    
    valid = msnr.get("found", False)
    
    logger.info(
        "M30 MSNR for %s: asian_range=(%.5f, %.5f), sweep_found=%s, type=%s",
        pair, asian_range.get("low", 0), asian_range.get("high", 0),
        msnr.get("found", False), msnr.get("type", "none") if msnr.get("found") else "none"
    )
    
    return {
        "valid": valid,
        "asian_range": asian_range,
        "msnr": msnr,
        "pair": pair,
        "timeframe": "M30",
    }