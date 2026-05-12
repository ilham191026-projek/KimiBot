"""
Layer 4 — M15 Candle Range Theory (CRT) Detection
The most critical detection layer. Implements a 3-step pattern that identifies
engineered liquidity sweeps followed by reversal confirmation.

3-Step CRT Setup:
  Step 1: Sweep — price breaks beyond a swing point (takes liquidity)
  Step 2: Return — price returns back into the previous range
  Step 3: Close — candle closes in the direction of the anticipated reversal
"""

from typing import Dict, List, Optional
import pandas as pd
import numpy as np

from utils.logger import get_logger
from utils.time_utils import now_gmt, candle_age_minutes
from config import CRT_LOOKBACK, MAX_CANDLE_AGE_HOURS

logger = get_logger(__name__)


def detect_crt(df: pd.DataFrame, direction: str) -> Dict:
    """
    Detect Candle Range Theory (CRT) 3-step pattern.
    
    Args:
        df: M15 OHLCV DataFrame (must include columns: open, high, low, close)
        direction: "bullish" or "bearish"
        
    Returns:
        Dict with CRT detection results:
        {
            found: bool,
            direction: str ("bullish" | "bearish"),
            candle_ago: int,  # how many candles back the CRT was found
            sweep_level: float,  # the price level that was swept
            sweep_depth_pip: float,
            age_min: float,  # age of the CRT pattern in minutes
            stale: bool,  # True if pattern is older than 4 hours
            in_ob_zone: bool,  # True if CRT occurred in/near an order block
        }
        If no valid CRT found: {found: False}
    """
    if df is None or len(df) < CRT_LOOKBACK + 5:
        return {"found": False, "reason": "insufficient_data"}
    
    # Use only closed candles (exclude current candle)
    closed_df = df.iloc[:-1]
    
    crts: List[Dict] = []
    lookback_end = len(closed_df) - 3  # Need room for 3-candle pattern
    lookback_start = max(0, lookback_end - CRT_LOOKBACK)
    
    for i in range(lookback_start, lookback_end):
        prev = closed_df.iloc[i]
        curr = closed_df.iloc[i + 1]
        next_candle = closed_df.iloc[i + 2] if i + 2 < len(closed_df) else None
        
        crt_candidate = None
        
        if direction == "bullish":
            crt_candidate = _check_bullish_crt(
                prev=prev, curr=curr, next_candle=next_candle,
                df=closed_df, index=i+1
            )
        elif direction == "bearish":
            crt_candidate = _check_bearish_crt(
                prev=prev, curr=curr, next_candle=next_candle,
                df=closed_df, index=i+1
            )
        
        if crt_candidate:
            crts.append(crt_candidate)
    
    if not crts:
        return {"found": False}
    
    # Select the best CRT: prefer fresh, then most recent
    def score_crt(crt: Dict) -> tuple:
        # Lower candle_ago = more recent = better
        # Not stale = better
        return (not crt["stale"], -crt["candle_ago"])
    
    best = max(crts, key=score_crt)
    
    logger.info(
        "CRT %s found on M15: candle_ago=%d, sweep=%.5f, stale=%s",
        direction, best["candle_ago"], best["sweep_level"], best["stale"]
    )
    
    return best


def _check_bullish_crt(
    prev: pd.Series,
    curr: pd.Series,
    next_candle: Optional[pd.Series],
    df: pd.DataFrame,
    index: int
) -> Optional[Dict]:
    """
    Check for bullish CRT 3-step pattern:
    
    Step 1: curr.low < prev.low - 1_pip (sweep of SSL)
    Step 2: curr.close > prev.low (return into range)
    Step 3: curr.close > curr.open (bullish close)
    Body ratio: (close - open) / (high - low) >= 0.4
    """
    # Step 1: Sweep below previous low (takes Sell Side Liquidity)
    pip_buffer = 0.0001  # 1 pip for standard pairs
    if curr["low"] >= prev["low"] - pip_buffer:
        return None
    
    # Step 2: Return — close back above the previous low
    if curr["close"] <= prev["low"]:
        return None
    
    # Step 3: Bullish close
    if curr["close"] <= curr["open"]:
        return None
    
    # Body ratio check
    body = curr["close"] - curr["open"]
    range_size = curr["high"] - curr["low"]
    if range_size == 0:
        return None
    body_ratio = body / range_size
    if body_ratio < 0.4:
        return None
    
    # Calculate age and staleness
    candles_ago = len(df) - 1 - index
    age_min = candles_ago * 15  # M15 candles = 15 min each
    stale = age_min > (MAX_CANDLE_AGE_HOURS * 60)
    
    # Check if in OB zone (simplified: near recent swing low)
    recent_lows = df["low"].tail(20)
    in_ob_zone = curr["low"] <= recent_lows.quantile(0.2)
    
    return {
        "found": True,
        "direction": "bullish",
        "candle_ago": candles_ago,
        "sweep_level": float(curr["low"]),
        "sweep_depth_pip": float((prev["low"] - curr["low"]) / 0.0001),
        "age_min": round(age_min, 1),
        "stale": stale,
        "in_ob_zone": in_ob_zone,
        "body_ratio": round(float(body_ratio), 3),
        "return_level": float(prev["low"]),
        "close_price": float(curr["close"]),
    }


def _check_bearish_crt(
    prev: pd.Series,
    curr: pd.Series,
    next_candle: Optional[pd.Series],
    df: pd.DataFrame,
    index: int
) -> Optional[Dict]:
    """
    Check for bearish CRT 3-step pattern (mirror of bullish):
    
    Step 1: curr.high > prev.high + 1_pip (sweep of BSL)
    Step 2: curr.close < prev.high (return into range)
    Step 3: curr.close < curr.open (bearish close)
    Body ratio: |close - open| / (high - low) >= 0.4
    """
    # Step 1: Sweep above previous high (takes Buy Side Liquidity)
    pip_buffer = 0.0001
    if curr["high"] <= prev["high"] + pip_buffer:
        return None
    
    # Step 2: Return — close back below the previous high
    if curr["close"] >= prev["high"]:
        return None
    
    # Step 3: Bearish close
    if curr["close"] >= curr["open"]:
        return None
    
    # Body ratio check
    body = abs(curr["close"] - curr["open"])
    range_size = curr["high"] - curr["low"]
    if range_size == 0:
        return None
    body_ratio = body / range_size
    if body_ratio < 0.4:
        return None
    
    # Calculate age and staleness
    candles_ago = len(df) - 1 - index
    age_min = candles_ago * 15
    stale = age_min > (MAX_CANDLE_AGE_HOURS * 60)
    
    # Check if in OB zone (near recent swing high)
    recent_highs = df["high"].tail(20)
    in_ob_zone = curr["high"] >= recent_highs.quantile(0.8)
    
    return {
        "found": True,
        "direction": "bearish",
        "candle_ago": candles_ago,
        "sweep_level": float(curr["high"]),
        "sweep_depth_pip": float((curr["high"] - prev["high"]) / 0.0001),
        "age_min": round(age_min, 1),
        "stale": stale,
        "in_ob_zone": in_ob_zone,
        "body_ratio": round(float(body_ratio), 3),
        "return_level": float(prev["high"]),
        "close_price": float(curr["close"]),
    }


def analyze_m15_crt(pair: str, df: pd.DataFrame, direction: str) -> Dict:
    """
    Main entry for M15 CRT analysis.
    
    Args:
        pair: Instrument symbol
        df: M15 OHLCV DataFrame
        direction: "bullish" or "bearish" from higher timeframe bias
        
    Returns:
        Dict with full CRT analysis including validity
    """
    if df is None or len(df) < CRT_LOOKBACK + 5:
        logger.warning("Insufficient M15 data for %s CRT (need %d+, got %d)",
                      pair, CRT_LOOKBACK + 5, len(df) if df is not None else 0)
        return {
            "valid": False,
            "reason": "insufficient_data",
            "pair": pair,
            "timeframe": "M15",
            "direction": direction,
        }
    
    crt = detect_crt(df, direction)
    
    valid = crt.get("found", False) and not crt.get("stale", True)
    
    logger.info(
        "M15 CRT for %s (%s): valid=%s, found=%s, stale=%s",
        pair, direction, valid, crt.get("found", False), crt.get("stale", True)
    )
    
    return {
        "valid": valid,
        "crt": crt,
        "direction": direction,
        "pair": pair,
        "timeframe": "M15",
    }


# ── Unit Test Cases (in comments) ────────────────────────────────────────────
"""
TEST CASE 1: Bullish CRT
--------------------------
prev: open=1.0850, high=1.0860, low=1.0845, close=1.0855  (bullish candle)
curr: open=1.0854, high=1.0858, low=1.0843, close=1.0857  (sweeps prev.low=1.0845)
- Step 1: curr.low(1.0843) < prev.low(1.0845) - 0.0001 → TRUE (sweep)
- Step 2: curr.close(1.0857) > prev.low(1.0845) → TRUE (return)
- Step 3: curr.close(1.0857) > curr.open(1.0854) → TRUE (bullish close)
- Body ratio: (1.0857-1.0854)/(1.0858-1.0843) = 0.0003/0.0015 = 0.2 → FAIL

TEST CASE 2: Bullish CRT (valid)
----------------------------------
prev: open=1.0850, high=1.0855, low=1.0845, close=1.0852  (bearish candle)
curr: open=1.0846, high=1.0860, low=1.0843, close=1.0858  (sweeps prev.low=1.0845)
- Step 1: curr.low(1.0843) < prev.low(1.0845) - 0.0001 → TRUE
- Step 2: curr.close(1.0858) > prev.low(1.0845) → TRUE
- Step 3: curr.close(1.0858) > curr.open(1.0846) → TRUE
- Body ratio: (1.0858-1.0846)/(1.0860-1.0843) = 0.0012/0.0017 = 0.706 → PASS

TEST CASE 3: Bearish CRT (valid)
----------------------------------
prev: open=1.0850, high=1.0860, low=1.0845, close=1.0858  (bullish candle)
curr: open=1.0857, high=1.0862, low=1.0848, close=1.0850  (sweeps prev.high=1.0860)
- Step 1: curr.high(1.0862) > prev.high(1.0860) + 0.0001 → TRUE
- Step 2: curr.close(1.0850) < prev.high(1.0860) → TRUE
- Step 3: curr.close(1.0850) < curr.open(1.0857) → TRUE
- Body ratio: |1.0850-1.0857|/(1.0862-1.0848) = 0.0007/0.0014 = 0.5 → PASS

TEST CASE 4: No CRT (no sweep)
--------------------------------
prev: open=1.0850, high=1.0860, low=1.0845, close=1.0855
curr: open=1.0854, high=1.0858, low=1.0846, close=1.0857
- Step 1: curr.low(1.0846) < prev.low(1.0845) - 0.0001 → FALSE (no sweep)
→ No CRT detected

TEST CASE 5: Stale CRT
------------------------
Same as TEST CASE 2 but candle_ago = 20 → age_min = 300 min = 5 hours
→ stale = True (exceeds MAX_CANDLE_AGE_HOURS=4)
→ CRT found but marked stale, valid = False
"""