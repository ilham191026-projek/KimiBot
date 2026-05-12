"""
Layer 1 — H4 Market Structure Analysis
Identifies Higher Highs (HH), Higher Lows (HL), Lower Highs (LH), Lower Lows (LL)
Detects Break of Structure (BOS) and Change of Character (CHoCH).
"""

from typing import Dict, Optional
import pandas as pd
import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)


def detect_swing_points(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """
    Detect swing highs and lows using a rolling window.
    
    A swing high: high is the maximum in [i-window, i+window]
    A swing low: low is the minimum in [i-window, i+window]
    """
    df = df.copy()
    df["swing_high"] = df["high"] == df["high"].rolling(window=window*2+1, center=True).max()
    df["swing_low"] = df["low"] == df["low"].rolling(window=window*2+1, center=True).min()
    return df


def identify_structure(df: pd.DataFrame) -> Dict:
    """
    Identify market structure: HH/HL/LH/LL pattern and BOS/CHoCH.
    
    Returns dict with:
        - bias: "bullish" | "bearish" | "neutral"
        - structure: list of swing points with labels
        - last_bos: last break of structure level
        - last_choch: last change of character level
        - confidence: 0.0-1.0
    """
    df = detect_swing_points(df)
    
    # Extract swing points
    highs = df[df["swing_high"]].copy()
    lows = df[df["swing_low"]].copy()
    
    if len(highs) < 2 or len(lows) < 2:
        return {
            "bias": "neutral",
            "structure": [],
            "last_bos": None,
            "last_choch": None,
            "confidence": 0.0,
        }
    
    # Analyze swing highs sequence
    hh_lh = []
    for i in range(1, len(highs)):
        if highs["high"].iloc[i] > highs["high"].iloc[i-1]:
            hh_lh.append("HH")
        else:
            hh_lh.append("LH")
    
    # Analyze swing lows sequence
    hl_ll = []
    for i in range(1, len(lows)):
        if lows["low"].iloc[i] > lows["low"].iloc[i-1]:
            hl_ll.append("HL")
        else:
            hl_ll.append("LL")
    
    # Determine bias
    bullish_signals = hh_lh.count("HH") + hl_ll.count("HL")
    bearish_signals = hh_lh.count("LH") + hl_ll.count("LL")
    total = len(hh_lh) + len(hl_ll)
    
    if total == 0:
        bias = "neutral"
        confidence = 0.0
    else:
        bullish_ratio = bullish_signals / total
        bearish_ratio = bearish_signals / total
        
        if bullish_ratio > 0.6:
            bias = "bullish"
            confidence = bullish_ratio
        elif bearish_ratio > 0.6:
            bias = "bearish"
            confidence = bearish_ratio
        else:
            bias = "neutral"
            confidence = max(bullish_ratio, bearish_ratio)
    
    # Detect BOS (Break of Structure)
    last_bos = None
    if len(hh_lh) >= 2 and hh_lh[-1] == "HH" and hh_lh[-2] == "LH":
        last_bos = {
            "type": "bullish_bos",
            "level": float(highs["high"].iloc[-1]),
            "broken_level": float(highs["high"].iloc[-2]),
        }
    elif len(hh_lh) >= 2 and hh_lh[-1] == "LH" and hh_lh[-2] == "HH":
        last_bos = {
            "type": "bearish_bos",
            "level": float(highs["high"].iloc[-1]),
            "broken_level": float(highs["high"].iloc[-2]),
        }
    
    # Detect CHoCH (Change of Character)
    last_choch = None
    if len(hl_ll) >= 2:
        if hl_ll[-1] == "LL" and hl_ll[-2] == "HL":
            last_choch = {
                "type": "bullish_to_bearish",
                "level": float(lows["low"].iloc[-1]),
            }
        elif hl_ll[-1] == "HL" and hl_ll[-2] == "LL":
            last_choch = {
                "type": "bearish_to_bullish",
                "level": float(lows["low"].iloc[-1]),
            }
    
    structure = {
        "swing_highs": len(highs),
        "swing_lows": len(lows),
        "hh_lh_sequence": hh_lh,
        "hl_ll_sequence": hl_ll,
        "recent_high": float(highs["high"].iloc[-1]) if len(highs) > 0 else None,
        "recent_low": float(lows["low"].iloc[-1]) if len(lows) > 0 else None,
    }
    
    logger.info(
        "H4 Bias: %s (confidence=%.2f), HH/LH=%s, HL/LL=%s",
        bias, confidence, hh_lh[-3:] if hh_lh else [], hl_ll[-3:] if hl_ll else []
    )
    
    return {
        "bias": bias,
        "structure": structure,
        "last_bos": last_bos,
        "last_choch": last_choch,
        "confidence": round(confidence, 3),
    }


def analyze_h4(pair: str, df: pd.DataFrame) -> Dict:
    """
    Main entry point for H4 market structure analysis.
    
    Args:
        pair: Instrument symbol
        df: H4 OHLCV DataFrame
        
    Returns:
        Analysis result dict with bias, structure, BOS, CHoCH
    """
    if df is None or len(df) < 20:
        logger.warning("Insufficient H4 data for %s (rows=%d)", pair, len(df) if df is not None else 0)
        return {
            "bias": "neutral",
            "structure": {},
            "last_bos": None,
            "last_choch": None,
            "confidence": 0.0,
            "valid": False,
        }
    
    result = identify_structure(df)
    result["valid"] = result["confidence"] >= 0.5 and result["bias"] != "neutral"
    result["pair"] = pair
    result["timeframe"] = "H4"
    
    return result