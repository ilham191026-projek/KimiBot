"""
Volatility Gate — Filters pairs before any analysis runs.
Requires: ADX(14) H1 > 25 and ATR(14) H1 between 8-35 pips.
"""

from typing import Dict, Optional
import pandas as pd
import numpy as np

from config import ADX_THRESHOLD, ATR_MIN_PIPS, ATR_MAX_PIPS
from utils.logger import get_logger
from utils.pip_calculator import price_to_pips

logger = get_logger(__name__)


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate Average True Range (ATR).
    
    TR = max(high-low, |high-prev_close|, |low-prev_close|)
    ATR = SMA(TR, period)
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    return atr


def calculate_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate Average Directional Index (ADX).
    
    +DM = max(high - prev_high, 0) if positive, else 0
    -DM = max(prev_low - low, 0) if positive, else 0
    DX = 100 * |+DI - -DI| / (+DI + -DI)
    ADX = SMA(DX, period)
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    
    # True Range
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # +DM and -DM
    plus_dm = high.diff()
    minus_dm = -low.diff()
    
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    
    # Smoothed averages
    atr = tr.rolling(window=period).mean()
    plus_di = 100 * plus_dm.rolling(window=period).mean() / atr
    minus_di = 100 * minus_dm.rolling(window=period).mean() / atr
    
    # DX and ADX
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    adx = dx.rolling(window=period).mean()
    
    return adx


def check_volatility_gate(pair: str, df: pd.DataFrame) -> Dict:
    """
    Check if a pair passes the volatility gate.
    
    Requirements:
    - ADX(14) on H1 > 25 (trending market)
    - ATR(14) on H1 between 8-35 pips (sufficient but not excessive volatility)
    
    Args:
        pair: Instrument symbol
        df: H1 OHLCV DataFrame
        
    Returns:
        Dict with gate check results
    """
    if df is None or len(df) < 20:
        return {
            "passed": False,
            "reason": "insufficient_data",
            "adx": None,
            "atr_pips": None,
            "pair": pair,
        }
    
    # Calculate ADX and ATR
    adx_series = calculate_adx(df, period=14)
    atr_series = calculate_atr(df, period=14)
    
    current_adx = adx_series.iloc[-1]
    current_atr = atr_series.iloc[-1]
    
    # Convert ATR to pips
    atr_pips = price_to_pips(pair, current_atr) if current_atr and not pd.isna(current_atr) else 0
    adx_value = float(current_adx) if current_adx and not pd.isna(current_adx) else 0
    
    # Check thresholds
    adx_ok = adx_value > ADX_THRESHOLD
    atr_ok = ATR_MIN_PIPS <= atr_pips <= ATR_MAX_PIPS
    
    passed = adx_ok and atr_ok
    
    reasons = []
    if not adx_ok:
        reasons.append(f"ADX({adx_value:.1f}) <= {ADX_THRESHOLD}")
    if not atr_ok:
        reasons.append(f"ATR({atr_pips:.1f} pips) not in [{ATR_MIN_PIPS}-{ATR_MAX_PIPS}]")
    
    logger.info(
        "Volatility Gate for %s: ADX=%.1f, ATR=%.1f pips | %s",
        pair, adx_value, atr_pips, "PASSED" if passed else f"FAILED ({', '.join(reasons)})"
    )
    
    return {
        "passed": passed,
        "reason": "; ".join(reasons) if reasons else "all_ok",
        "adx": round(adx_value, 2),
        "atr_pips": round(atr_pips, 2),
        "adx_ok": adx_ok,
        "atr_ok": atr_ok,
        "pair": pair,
    }