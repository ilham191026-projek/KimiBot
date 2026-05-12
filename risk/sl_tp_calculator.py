"""
Stop Loss and Take Profit Calculator.
SL from CRT M15 swing points ± 2 pip buffer.
TP1 = 1.5x SL distance, TP2 = 2.5x SL distance.
"""

from typing import Dict, Optional, Tuple
import pandas as pd

from config import MIN_SL_PIPS, MAX_SL_PIPS, TP1_RR, TP2_RR
from utils.logger import get_logger
from utils.pip_calculator import (
    get_pip_value,
    pips_to_price,
    price_to_pips,
    calculate_pip_difference,
)

logger = get_logger(__name__)


def find_m15_swing(
    df: pd.DataFrame,
    direction: str,
    crt_sweep_level: Optional[float] = None
) -> Dict:
    """
    Find the M15 swing point for SL calculation.
    
    For bullish: uses the swing low
    For bearish: uses the swing high
    
    If crt_sweep_level is provided, uses it as the swing point.
    """
    if df is None or len(df) < 5:
        return {"valid": False, "swing_low": None, "swing_high": None}
    
    # Use closed candles
    closed = df.iloc[:-1]
    
    if crt_sweep_level:
        # Use the CRT sweep level as the swing point
        if direction == "bullish":
            return {
                "valid": True,
                "swing_low": crt_sweep_level,
                "swing_high": None,
            }
        else:
            return {
                "valid": True,
                "swing_low": None,
                "swing_high": crt_sweep_level,
            }
    
    # Find swing points using rolling window
    window = 3
    swing_lows = []
    swing_highs = []
    
    for i in range(window, len(closed) - window):
        if closed["low"].iloc[i] == closed["low"].iloc[i-window:i+window+1].min():
            swing_lows.append(float(closed["low"].iloc[i]))
        if closed["high"].iloc[i] == closed["high"].iloc[i-window:i+window+1].max():
            swing_highs.append(float(closed["high"].iloc[i]))
    
    return {
        "valid": True,
        "swing_low": swing_lows[-1] if swing_lows else float(closed["low"].tail(5).min()),
        "swing_high": swing_highs[-1] if swing_highs else float(closed["high"].tail(5).max()),
    }


def find_m30_swing(df: pd.DataFrame, direction: str) -> Dict:
    """Find M30 swing point as fallback for SL."""
    if df is None or len(df) < 5:
        return {"valid": False, "swing_low": None, "swing_high": None}
    
    closed = df.iloc[:-1]
    
    window = 3
    swing_lows = []
    swing_highs = []
    
    for i in range(window, len(closed) - window):
        if closed["low"].iloc[i] == closed["low"].iloc[i-window:i+window+1].min():
            swing_lows.append(float(closed["low"].iloc[i]))
        if closed["high"].iloc[i] == closed["high"].iloc[i-window:i+window+1].max():
            swing_highs.append(float(closed["high"].iloc[i]))
    
    return {
        "valid": True,
        "swing_low": swing_lows[-1] if swing_lows else float(closed["low"].tail(5).min()),
        "swing_high": swing_highs[-1] if swing_highs else float(closed["high"].tail(5).max()),
    }


def calculate_sl_tp(
    direction: str,
    entry_price: float,
    crt_swing: Optional[Dict],
    m30_swing: Optional[Dict],
    instrument: str,
) -> Dict:
    """
    Calculate SL and TP levels based on CRT M15 swing points.
    
    Args:
        direction: "bullish" or "bearish"
        entry_price: The proposed entry price
        crt_swing: Dict with swing_low/swing_high from M15 CRT detection
        m30_swing: Dict with swing_low/swing_high from M30 (fallback)
        instrument: Symbol (e.g., "EURUSD")
        
    Returns:
        Dict:
        {
            valid: bool,
            sl: float | None,
            tp1: float | None,
            tp2: float | None,
            sl_pip: float,
            rr1: float,
            rr2: float,
            fallback_used: bool,
            reason: str | None,
        }
    """
    pip_value = get_pip_value(instrument)
    buffer = pips_to_price(instrument, 2)  # 2 pip buffer
    
    # Determine SL level
    if direction == "bullish":
        # For bullish: SL below the swing low
        if crt_swing and crt_swing.get("swing_low"):
            sl_price = crt_swing["swing_low"] - buffer
        elif m30_swing and m30_swing.get("swing_low"):
            sl_price = m30_swing["swing_low"] - buffer
        else:
            # Fallback: SL 15 pips below entry
            sl_price = entry_price - pips_to_price(instrument, 15)
    
    elif direction == "bearish":
        # For bearish: SL above the swing high
        if crt_swing and crt_swing.get("swing_high"):
            sl_price = crt_swing["swing_high"] + buffer
        elif m30_swing and m30_swing.get("swing_high"):
            sl_price = m30_swing["swing_high"] + buffer
        else:
            # Fallback: SL 15 pips above entry
            sl_price = entry_price + pips_to_price(instrument, 15)
    
    else:
        return {"valid": False, "reason": "invalid_direction", "sl": None, "tp1": None, "tp2": None, "sl_pip": 0, "rr1": 0, "rr2": 0, "fallback_used": False}
    
    # Calculate SL distance in pips
    sl_distance = abs(entry_price - sl_price)
    sl_pips = price_to_pips(instrument, sl_distance)
    
    fallback_used = False
    
    # Check if SL is too tight (< 15 pips), use M30 fallback
    if sl_pips < MIN_SL_PIPS and m30_swing:
        logger.info("SL too tight (%.1f pips < %d), using M30 fallback", sl_pips, MIN_SL_PIPS)
        fallback_used = True
        
        if direction == "bullish" and m30_swing.get("swing_low"):
            sl_price = m30_swing["swing_low"] - buffer
        elif direction == "bearish" and m30_swing.get("swing_high"):
            sl_price = m30_swing["swing_high"] + buffer
        
        sl_distance = abs(entry_price - sl_price)
        sl_pips = price_to_pips(instrument, sl_distance)
    
    # Check if SL exceeds max (20 pips)
    if sl_pips > MAX_SL_PIPS:
        logger.warning("SL exceeds max %.0f pips (%.1f), signal invalid", MAX_SL_PIPS, sl_pips)
        return {
            "valid": False,
            "reason": f"SL exceeds max {MAX_SL_PIPS} pip",
            "sl": None,
            "tp1": None,
            "tp2": None,
            "sl_pip": round(sl_pips, 1),
            "rr1": 0,
            "rr2": 0,
            "fallback_used": fallback_used,
        }
    
    # Calculate TP levels
    tp1_distance = sl_distance * TP1_RR  # 1.5x
    tp2_distance = sl_distance * TP2_RR  # 2.5x
    
    if direction == "bullish":
        tp1 = entry_price + tp1_distance
        tp2 = entry_price + tp2_distance
    else:
        tp1 = entry_price - tp1_distance
        tp2 = entry_price - tp2_distance
    
    logger.info(
        "SL/TP for %s %s: entry=%.5f, SL=%.5f (%.1f pips), TP1=%.5f (RR=%.1f), TP2=%.5f (RR=%.1f)",
        instrument, direction, entry_price, sl_price, sl_pips,
        tp1, TP1_RR, tp2, TP2_RR
    )
    
    return {
        "valid": True,
        "sl": round(sl_price, 5),
        "tp1": round(tp1, 5),
        "tp2": round(tp2, 5),
        "sl_pip": round(sl_pips, 1),
        "rr1": TP1_RR,
        "rr2": TP2_RR,
        "fallback_used": fallback_used,
        "reason": None,
    }