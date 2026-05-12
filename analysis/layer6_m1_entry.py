"""
Layer 6 — M1 Precision Entry Confirmation
Fine-grained entry confirmation using M1 candle patterns,
microstructure analysis, and momentum confirmation.
"""

from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)


def calculate_momentum(df: pd.DataFrame, period: int = 5) -> float:
    """Calculate momentum score from recent price action."""
    if len(df) < period + 1:
        return 0.0
    
    closes = df["close"].tail(period)
    momentum = (closes.iloc[-1] - closes.iloc[0]) / closes.iloc[0] * 100
    return float(momentum)


def detect_engulfing(df: pd.DataFrame) -> Optional[Dict]:
    """
    Detect engulfing candle patterns.
    
    Bullish engulfing: current bullish candle's body completely engulfs
                       previous bearish candle's body
    Bearish engulfing: current bearish candle's body completely engulfs
                       previous bullish candle's body
    """
    if len(df) < 3:
        return None
    
    closed = df.iloc[:-1]  # Exclude current candle
    
    curr = closed.iloc[-1]
    prev = closed.iloc[-2]
    
    curr_body = abs(curr["close"] - curr["open"])
    prev_body = abs(prev["close"] - prev["open"])
    
    # Bullish engulfing
    if (curr["close"] > curr["open"] and  # Current bullish
        prev["close"] < prev["open"] and  # Previous bearish
        curr["open"] <= prev["close"] and  # Open at or below prev close
        curr["close"] >= prev["open"]):    # Close at or above prev open
        return {
            "type": "bullish_engulfing",
            "strength": float(curr_body / (prev_body + 1e-10)),
            "index": len(closed) - 1,
        }
    
    # Bearish engulfing
    if (curr["close"] < curr["open"] and  # Current bearish
        prev["close"] > prev["open"] and  # Previous bullish
        curr["open"] >= prev["close"] and  # Open at or above prev close
        curr["close"] <= prev["open"]):    # Close at or below prev open
        return {
            "type": "bearish_engulfing",
            "strength": float(curr_body / (prev_body + 1e-10)),
            "index": len(closed) - 1,
        }
    
    return None


def detect_pin_bar(df: pd.DataFrame, direction: str) -> Optional[Dict]:
    """
    Detect pin bar (hammer/shooting star) patterns on M1.
    
    Bullish pin bar: long lower wick, small body at top (hammer)
    Bearish pin bar: long upper wick, small body at bottom (shooting star)
    """
    if len(df) < 3:
        return None
    
    closed = df.iloc[:-1]
    candle = closed.iloc[-1]
    
    body = abs(candle["close"] - candle["open"])
    upper_wick = candle["high"] - max(candle["open"], candle["close"])
    lower_wick = min(candle["open"], candle["close"]) - candle["low"]
    total_range = candle["high"] - candle["low"]
    
    if total_range == 0:
        return None
    
    if direction == "bullish":
        # Hammer: long lower wick, small body at top
        if (lower_wick > body * 2 and 
            candle["close"] > candle["open"] and  # Bullish close
            body / total_range < 0.3):  # Small body
            return {
                "type": "bullish_pin_bar",
                "lower_wick_ratio": float(lower_wick / total_range),
                "body_ratio": float(body / total_range),
                "index": len(closed) - 1,
            }
    
    elif direction == "bearish":
        # Shooting star: long upper wick, small body at bottom
        if (upper_wick > body * 2 and
            candle["close"] < candle["open"] and  # Bearish close
            body / total_range < 0.3):
            return {
                "type": "bearish_pin_bar",
                "upper_wick_ratio": float(upper_wick / total_range),
                "body_ratio": float(body / total_range),
                "index": len(closed) - 1,
            }
    
    return None


def check_volume_confirmation(df: pd.DataFrame) -> bool:
    """Check if recent volume is above average (confirming move)."""
    if len(df) < 10 or "volume" not in df.columns:
        return True  # Skip volume check if no volume data
    
    recent_volume = df["volume"].tail(3).mean()
    avg_volume = df["volume"].tail(20).mean()
    
    if avg_volume == 0:
        return True
    
    return recent_volume >= avg_volume * 0.8  # Within 20% of average


def analyze_m1_entry(pair: str, df: pd.DataFrame, direction: str) -> Dict:
    """
    Main entry for M1 precision entry confirmation.
    
    Args:
        pair: Instrument symbol
        df: M1 OHLCV DataFrame
        direction: "bullish" or "bearish" from higher timeframe analysis
        
    Returns:
        Dict with entry confirmation analysis
    """
    if df is None or len(df) < 20:
        logger.warning("Insufficient M1 data for %s", pair)
        return {
            "valid": False,
            "reason": "insufficient_data",
            "pair": pair,
            "timeframe": "M1",
        }
    
    # Check momentum
    momentum = calculate_momentum(df)
    momentum_aligned = (
        (direction == "bullish" and momentum > 0) or
        (direction == "bearish" and momentum < 0)
    )
    
    # Check engulfing pattern
    engulfing = detect_engulfing(df)
    engulfing_aligned = engulfing is not None and direction in engulfing["type"]
    
    # Check pin bar
    pin_bar = detect_pin_bar(df, direction)
    
    # Check volume
    volume_ok = check_volume_confirmation(df)
    
    # Count confirmation signals
    confirmations = sum([
        momentum_aligned,
        engulfing_aligned,
        pin_bar is not None,
        volume_ok,
    ])
    
    # Valid if at least 2 confirmations present
    valid = confirmations >= 2
    
    logger.info(
        "M1 Entry for %s (%s): momentum=%.4f, engulfing=%s, pin_bar=%s, volume=%s, confirmations=%d/4",
        pair, direction, momentum,
        engulfing_aligned, pin_bar is not None, volume_ok, confirmations
    )
    
    return {
        "valid": valid,
        "momentum": round(momentum, 6),
        "momentum_aligned": momentum_aligned,
        "engulfing": engulfing,
        "pin_bar": pin_bar,
        "volume_ok": volume_ok,
        "confirmations": confirmations,
        "direction": direction,
        "pair": pair,
        "timeframe": "M1",
    }