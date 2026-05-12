"""
Layer 5 — M5 Market Structure Shift (MSS) + FVG Trigger
Detects when M5 structure breaks in the direction of the trade,
confirming a shift in market structure with a Fair Value Gap.
"""

from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)


def detect_mss(df: pd.DataFrame, direction: str) -> Dict:
    """
    Detect Market Structure Shift on M5.
    
    Bullish MSS: Price breaks above the most recent swing high
                 (previous structure point becomes support)
    Bearish MSS: Price breaks below the most recent swing low
                 (previous structure point becomes resistance)
    
    Returns dict with MSS details.
    """
    if df is None or len(df) < 20:
        return {"found": False, "reason": "insufficient_data"}
    
    # Use closed candles only
    closed = df.iloc[:-1]
    
    # Find recent swing points (simplified: local maxima/minima)
    window = 3
    swing_highs = []
    swing_lows = []
    
    for i in range(window, len(closed) - window):
        # Swing high
        if closed["high"].iloc[i] == closed["high"].iloc[i-window:i+window+1].max():
            swing_highs.append({
                "index": i,
                "price": float(closed["high"].iloc[i]),
            })
        # Swing low
        if closed["low"].iloc[i] == closed["low"].iloc[i-window:i+window+1].min():
            swing_lows.append({
                "index": i,
                "price": float(closed["low"].iloc[i]),
            })
    
    if not swing_highs or not swing_lows:
        return {"found": False, "reason": "no_swing_points"}
    
    # Get the most recent structure points
    last_swing_high = swing_highs[-1]
    last_swing_low = swing_lows[-1]
    
    # Get the recent candles for MSS check
    recent = closed.tail(5)
    
    mss_found = False
    mss_type = None
    mss_level = None
    
    if direction == "bullish":
        # Bullish MSS: close above last swing high
        for i in range(len(recent)):
            if recent["close"].iloc[i] > last_swing_high["price"]:
                mss_found = True
                mss_type = "bullish_mss"
                mss_level = float(last_swing_high["price"])
                break
    
    elif direction == "bearish":
        # Bearish MSS: close below last swing low
        for i in range(len(recent)):
            if recent["close"].iloc[i] < last_swing_low["price"]:
                mss_found = True
                mss_type = "bearish_mss"
                mss_level = float(last_swing_low["price"])
                break
    
    return {
        "found": mss_found,
        "type": mss_type,
        "level": mss_level,
        "last_swing_high": last_swing_high,
        "last_swing_low": last_swing_low,
        "direction": direction,
    }


def detect_m5_fvg(df: pd.DataFrame, direction: str) -> List[Dict]:
    """
    Detect Fair Value Gaps on M5 that align with the MSS direction.
    
    Bullish FVG: gap up between candles
    Bearish FVG: gap down between candles
    """
    if df is None or len(df) < 5:
        return []
    
    fvgs = []
    closed = df.iloc[:-1]
    
    for i in range(2, len(closed)):
        if direction == "bullish":
            # Bullish FVG: low of current > high of candle 2 ago
            if closed["low"].iloc[i] > closed["high"].iloc[i-2]:
                fvgs.append({
                    "type": "bullish_fvg",
                    "top": float(closed["low"].iloc[i]),
                    "bottom": float(closed["high"].iloc[i-2]),
                    "size": float(closed["low"].iloc[i] - closed["high"].iloc[i-2]),
                    "index": i,
                })
        
        elif direction == "bearish":
            # Bearish FVG: high of current < low of candle 2 ago
            if closed["high"].iloc[i] < closed["low"].iloc[i-2]:
                fvgs.append({
                    "type": "bearish_fvg",
                    "top": float(closed["low"].iloc[i-2]),
                    "bottom": float(closed["high"].iloc[i]),
                    "size": float(closed["low"].iloc[i-2] - closed["high"].iloc[i]),
                    "index": i,
                })
    
    return fvgs[-3:] if fvgs else []


def analyze_m5_mss(pair: str, df: pd.DataFrame, direction: str) -> Dict:
    """
    Main entry for M5 Market Structure Shift + FVG analysis.
    
    Args:
        pair: Instrument symbol
        df: M5 OHLCV DataFrame
        direction: "bullish" or "bearish" from higher timeframe
        
    Returns:
        Dict with MSS and FVG analysis results
    """
    if df is None or len(df) < 20:
        logger.warning("Insufficient M5 data for %s", pair)
        return {
            "valid": False,
            "reason": "insufficient_data",
            "pair": pair,
            "timeframe": "M5",
        }
    
    mss = detect_mss(df, direction)
    fvgs = detect_m5_fvg(df, direction)
    
    # Valid if MSS found and at least one FVG exists
    valid = mss.get("found", False) and len(fvgs) > 0
    
    # Also accept if strong MSS without FVG
    if not valid and mss.get("found", False):
        valid = True  # MSS alone is sufficient
    
    logger.info(
        "M5 MSS for %s (%s): mss_found=%s, fvgs=%d, valid=%s",
        pair, direction, mss.get("found", False), len(fvgs), valid
    )
    
    return {
        "valid": valid,
        "mss": mss,
        "fvgs": fvgs,
        "direction": direction,
        "pair": pair,
        "timeframe": "M5",
    }