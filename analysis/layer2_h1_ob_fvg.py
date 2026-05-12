"""
Layer 2 — H1 Order Block (OB) + Fair Value Gap (FVG) Detection (ICT)
Identifies supply/demand zones and price imbalances.
"""

from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from utils.logger import get_logger

logger = get_logger(__name__)


def detect_order_blocks(df: pd.DataFrame, direction: str, lookback: int = 10) -> List[Dict]:
    """
    Detect Order Blocks — the last opposing candle before a strong impulse.
    
    Bullish OB: last bearish candle before a bullish impulse
    Bearish OB: last bullish candle before a bearish impulse
    
    Returns list of OB zones with top, bottom, and type.
    """
    obs = []
    
    for i in range(lookback, len(df) - 1):
        # Identify impulse move
        if direction == "bullish":
            # Look for bullish impulse: strong close above previous highs
            impulse_strength = (df["close"].iloc[i] - df["open"].iloc[i]) / (df["high"].iloc[i] - df["low"].iloc[i] + 1e-10)
            if impulse_strength < 0.5 or df["close"].iloc[i] <= df["open"].iloc[i]:
                continue
            
            # Find last bearish candle before impulse
            for j in range(i-1, max(i-lookback, -1), -1):
                if df["close"].iloc[j] < df["open"].iloc[j]:  # Bearish candle
                    ob = {
                        "type": "bullish_ob",
                        "top": float(df["high"].iloc[j]),
                        "bottom": float(df["low"].iloc[j]),
                        "candle_index": j,
                        "impulse_index": i,
                        "strength": impulse_strength,
                    }
                    obs.append(ob)
                    break
                    
        elif direction == "bearish":
            # Look for bearish impulse
            impulse_strength = abs(df["close"].iloc[i] - df["open"].iloc[i]) / (df["high"].iloc[i] - df["low"].iloc[i] + 1e-10)
            if impulse_strength < 0.5 or df["close"].iloc[i] >= df["open"].iloc[i]:
                continue
            
            # Find last bullish candle before impulse
            for j in range(i-1, max(i-lookback, -1), -1):
                if df["close"].iloc[j] > df["open"].iloc[j]:  # Bullish candle
                    ob = {
                        "type": "bearish_ob",
                        "top": float(df["high"].iloc[j]),
                        "bottom": float(df["low"].iloc[j]),
                        "candle_index": j,
                        "impulse_index": i,
                        "strength": impulse_strength,
                    }
                    obs.append(ob)
                    break
    
    # Return the most recent OB
    return obs[-3:] if obs else []


def detect_fvg(df: pd.DataFrame, lookback: int = 20) -> List[Dict]:
    """
    Detect Fair Value Gaps (FVG) — price imbalances between candles.
    
    Bullish FVG: current low > previous high (gap up)
    Bearish FVG: current high < previous low (gap down)
    
    Returns list of FVG zones.
    """
    fvgs = []
    
    for i in range(2, len(df)):
        # Bullish FVG: gap between candle[i-2] high and candle[i] low
        if df["low"].iloc[i] > df["high"].iloc[i-2]:
            fvg = {
                "type": "bullish_fvg",
                "top": float(df["low"].iloc[i]),
                "bottom": float(df["high"].iloc[i-2]),
                "index": i,
                "size": float(df["low"].iloc[i] - df["high"].iloc[i-2]),
            }
            fvgs.append(fvg)
        
        # Bearish FVG: gap between candle[i-2] low and candle[i] high
        elif df["high"].iloc[i] < df["low"].iloc[i-2]:
            fvg = {
                "type": "bearish_fvg",
                "top": float(df["low"].iloc[i-2]),
                "bottom": float(df["high"].iloc[i]),
                "index": i,
                "size": float(df["low"].iloc[i-2] - df["high"].iloc[i]),
            }
            fvgs.append(fvg)
    
    # Return the most recent FVGs
    return fvgs[-3:] if fvgs else []


def analyze_h1_ob_fvg(pair: str, df: pd.DataFrame, h4_bias: str) -> Dict:
    """
    Main entry for H1 Order Block + FVG analysis.
    
    Args:
        pair: Instrument symbol
        df: H1 OHLCV DataFrame
        h4_bias: "bullish" | "bearish" | "neutral" from Layer 1
        
    Returns:
        Dict with OB/FVG analysis results
    """
    if df is None or len(df) < 20:
        logger.warning("Insufficient H1 data for %s", pair)
        return {"valid": False, "reason": "insufficient_data"}
    
    direction = h4_bias if h4_bias in ["bullish", "bearish"] else "bullish"
    
    # Detect Order Blocks
    obs = detect_order_blocks(df, direction)
    
    # Detect FVGs
    fvgs = detect_fvg(df)
    
    # Check if price is near an OB zone
    current_price = df["close"].iloc[-1]
    near_ob = False
    relevant_ob = None
    
    for ob in reversed(obs):
        if ob["bottom"] <= current_price <= ob["top"]:
            near_ob = True
            relevant_ob = ob
            break
    
    # Check for unmitigated FVG
    unmitigated_fvgs = []
    for fvg in reversed(fvgs):
        # FVG is unmitigated if price hasn't returned to fill it
        if fvg["type"] == "bullish_fvg":
            if current_price > fvg["top"]:
                unmitigated_fvgs.append(fvg)
        else:
            if current_price < fvg["bottom"]:
                unmitigated_fvgs.append(fvg)
    
    valid = len(obs) > 0 and (near_ob or len(unmitigated_fvgs) > 0)
    
    logger.info(
        "H1 OB/FVG for %s: %d OBs, %d FVGs, near_ob=%s, unmitigated_fvgs=%d",
        pair, len(obs), len(fvgs), near_ob, len(unmitigated_fvgs)
    )
    
    return {
        "valid": valid,
        "direction": direction,
        "order_blocks": obs,
        "fvgs": fvgs,
        "unmitigated_fvgs": unmitigated_fvgs,
        "near_ob": near_ob,
        "relevant_ob": relevant_ob,
        "pair": pair,
        "timeframe": "H1",
    }