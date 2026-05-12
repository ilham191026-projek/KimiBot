"""
Spread Filter — Check if spread is acceptable at M5/M1 timeframes.
Spread must be ≤ 2 pips for valid entry.
"""

from typing import Dict
import pandas as pd

from config import MAX_SPREAD_PIPS
from utils.logger import get_logger
from utils.pip_calculator import price_to_pips

logger = get_logger(__name__)


def calculate_spread(df: pd.DataFrame) -> float:
    """
    Estimate spread from OHLCV data.
    Uses the difference between high and low of the most recent M1/M5 candle
    as a proxy for spread.
    """
    if df is None or len(df) < 1:
        return float('inf')
    
    # Use the most recent closed candle
    last_candle = df.iloc[-2] if len(df) > 1 else df.iloc[-1]
    
    # Spread estimate: high - low of the candle
    spread = last_candle["high"] - last_candle["low"]
    
    return float(spread)


def check_spread(pair: str, df: pd.DataFrame) -> Dict:
    """
    Check if spread is within acceptable limits.
    
    Args:
        pair: Instrument symbol
        df: M5 or M1 OHLCV DataFrame
        
    Returns:
        Dict with spread check results
    """
    spread_price = calculate_spread(df)
    spread_pips = price_to_pips(pair, spread_price)
    
    passed = spread_pips <= MAX_SPREAD_PIPS
    
    logger.info(
        "Spread check for %s: %.2f pips (max %.1f) | %s",
        pair, spread_pips, MAX_SPREAD_PIPS, "PASSED" if passed else "FAILED"
    )
    
    return {
        "passed": passed,
        "spread_pips": round(spread_pips, 2),
        "max_spread_pips": MAX_SPREAD_PIPS,
        "pair": pair,
    }