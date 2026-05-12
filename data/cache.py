"""
In-memory cache layer for OHLCV data.
Caches results for 55 seconds (just under the 60s loop interval).
"""

import time
from typing import Dict, Optional, Any
import pandas as pd

from utils.logger import get_logger

logger = get_logger(__name__)

# In-memory cache: key -> {"data": DataFrame, "timestamp": float}
_cache: Dict[str, Any] = {}
DEFAULT_TTL = 55  # seconds


def _make_key(pair: str, timeframe: str, limit: int) -> str:
    """Create a cache key from request parameters."""
    return f"{pair}:{timeframe}:{limit}"


def get(pair: str, timeframe: str, limit: int) -> Optional[pd.DataFrame]:
    """Retrieve cached OHLCV data if not expired."""
    key = _make_key(pair, timeframe, limit)
    entry = _cache.get(key)
    if entry is None:
        return None
    
    age = time.time() - entry["timestamp"]
    if age > DEFAULT_TTL:
        logger.debug("Cache expired for %s (age=%.0fs)", key, age)
        del _cache[key]
        return None
    
    logger.debug("Cache hit for %s (age=%.0fs)", key, age)
    return entry["data"].copy()


def set(pair: str, timeframe: str, limit: int, data: pd.DataFrame) -> None:
    """Cache OHLCV data with current timestamp."""
    key = _make_key(pair, timeframe, limit)
    _cache[key] = {
        "data": data.copy(),
        "timestamp": time.time(),
    }
    logger.debug("Cached %d rows for %s", len(data), key)


def clear() -> None:
    """Clear all cached data."""
    global _cache
    _cache = {}
    logger.info("Cache cleared")


def stats() -> Dict[str, int]:
    """Return cache statistics."""
    now = time.time()
    total = len(_cache)
    expired = sum(1 for v in _cache.values() if (now - v["timestamp"]) > DEFAULT_TTL)
    return {"total_entries": total, "expired": expired, "ttl_seconds": DEFAULT_TTL}