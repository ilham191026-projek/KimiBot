"""
OHLCV Data Fetcher with fallback chain:
Bloomberg B-PIPE API → Polygon.io → Twelve Data → Alpha Vantage
"""

import os
import time
from typing import Optional
from datetime import datetime, timedelta

import pandas as pd
import requests
import aiohttp
import asyncio

from config import (
    POLYGON_API_KEY,
    TWELVE_DATA_API_KEY,
    ALPHA_VANTAGE_API_KEY,
    TIMEFRAMES,
)
from data.cache import get as cache_get, set as cache_set
from utils.logger import get_logger
from utils.pip_calculator import get_pip_value

logger = get_logger(__name__)


class DataUnavailableError(Exception):
    """Raised when all data sources fail to provide OHLCV data."""
    pass


class DataFetcher:
    """Fetches OHLCV candlestick data with multi-source fallback."""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"Accept": "application/json"})
    
    def get_ohlcv(
        self,
        pair: str,
        timeframe: str,
        limit: int = 100
    ) -> pd.DataFrame:
        """
        Fetch OHLCV data with caching and fallback chain.
        
        Args:
            pair: Instrument symbol (e.g., 'XAUUSD', 'EURUSD')
            timeframe: One of M1, M5, M15, M30, H1, H4
            limit: Number of candles to fetch
            
        Returns:
            DataFrame with columns [timestamp, open, high, low, close, volume]
            Timestamps are UTC. No NaN rows.
            
        Raises:
            DataUnavailableError: If all sources fail
        """
        # Check cache first
        cached = cache_get(pair, timeframe, limit)
        if cached is not None:
            return cached
        
        # Format pair for APIs (replace / with empty or appropriate separator)
        api_pair = pair.replace("/", "")
        
        # Try each source in order
        errors = []
        
        # Source 1: Bloomberg B-PIPE (if available)
        try:
            result = self._fetch_bloomberg(api_pair, timeframe, limit)
            if result is not None and len(result) > 0:
                cache_set(pair, timeframe, limit, result)
                return result
        except Exception as e:
            errors.append(f"Bloomberg: {str(e)}")
        
        # Source 2: Polygon.io
        try:
            result = self._fetch_polygon(api_pair, timeframe, limit)
            if result is not None and len(result) > 0:
                cache_set(pair, timeframe, limit, result)
                return result
        except Exception as e:
            errors.append(f"Polygon: {str(e)}")
        
        # Source 3: Twelve Data
        try:
            result = self._fetch_twelve_data(api_pair, timeframe, limit)
            if result is not None and len(result) > 0:
                cache_set(pair, timeframe, limit, result)
                return result
        except Exception as e:
            errors.append(f"Twelve Data: {str(e)}")
        
        # Source 4: Alpha Vantage
        try:
            result = self._fetch_alpha_vantage(api_pair, timeframe, limit)
            if result is not None and len(result) > 0:
                cache_set(pair, timeframe, limit, result)
                return result
        except Exception as e:
            errors.append(f"Alpha Vantage: {str(e)}")
        
        # All sources failed
        error_msg = f"All data sources failed for {pair} {timeframe}: {'; '.join(errors)}"
        logger.error(error_msg)
        raise DataUnavailableError(error_msg)
    
    def _fetch_bloomberg(
        self,
        pair: str,
        timeframe: str,
        limit: int
    ) -> Optional[pd.DataFrame]:
        """Fetch from Bloomberg B-PIPE API via blpapi."""
        try:
            import blpapi
        except ImportError:
            logger.debug("blpapi not installed, skipping Bloomberg")
            return None
        
        # Bloomberg requires complex setup - placeholder for production
        logger.debug("Bloomberg fetch not yet implemented")
        return None
    
    def _fetch_polygon(
        self,
        pair: str,
        timeframe: str,
        limit: int
    ) -> Optional[pd.DataFrame]:
        """Fetch from Polygon.io REST API."""
        if not POLYGON_API_KEY:
            logger.debug("No Polygon API key configured")
            return None
        
        # Convert timeframe to Polygon format
        multiplier, timespan = self._convert_timeframe(timeframe)
        
        # Build ticker symbol (Polygon uses C:EURUSD format for forex)
        ticker = f"C:{pair[:3]}{pair[3:]}" if len(pair) == 6 else pair
        
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - self._estimate_duration(timeframe, limit)
        
        url = (
            f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/"
            f"{multiplier}/{timespan}/"
            f"{start_date.strftime('%Y-%m-%d')}/"
            f"{end_date.strftime('%Y-%m-%d')}"
        )
        
        params = {"apiKey": POLYGON_API_KEY, "limit": limit, "sort": "desc"}
        
        response = self.session.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if data.get("resultsCount", 0) == 0:
            return None
        
        df = pd.DataFrame(data["results"])
        df = df.rename(columns={
            "t": "timestamp",
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume",
        })
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df[["timestamp", "open", "high", "low", "close", "volume"]]
        df = df.sort_values("timestamp").reset_index(drop=True)
        df = df.dropna()
        
        logger.info("Fetched %d rows from Polygon for %s %s", len(df), pair, timeframe)
        return df
    
    def _fetch_twelve_data(
        self,
        pair: str,
        timeframe: str,
        limit: int
    ) -> Optional[pd.DataFrame]:
        """Fetch from Twelve Data API."""
        if not TWELVE_DATA_API_KEY:
            logger.debug("No Twelve Data API key configured")
            return None
        
        # Format symbol for Twelve Data (EUR/USD)
        symbol = f"{pair[:3]}/{pair[3:]}" if len(pair) == 6 else pair
        interval = TIMEFRAMES.get(timeframe, "1h")
        
        url = "https://api.twelvedata.com/time_series"
        params = {
            "symbol": symbol,
            "interval": interval,
            "outputsize": limit,
            "apikey": TWELVE_DATA_API_KEY,
            "format": "JSON",
        }
        
        response = self.session.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        if "values" not in data:
            return None
        
        df = pd.DataFrame(data["values"])
        df = df.rename(columns={
            "datetime": "timestamp",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        })
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df = df.sort_values("timestamp").reset_index(drop=True)
        df = df.dropna()
        
        logger.info("Fetched %d rows from Twelve Data for %s %s", len(df), pair, timeframe)
        return df
    
    def _fetch_alpha_vantage(
        self,
        pair: str,
        timeframe: str,
        limit: int
    ) -> Optional[pd.DataFrame]:
        """Fetch from Alpha Vantage API."""
        if not ALPHA_VANTAGE_API_KEY:
            logger.debug("No Alpha Vantage API key configured")
            return None
        
        # Alpha Vantage has rate limits (5 calls/min for free tier)
        from_symbol = pair[:3]
        to_symbol = pair[3:] if len(pair) == 6 else "USD"
        
        # Map timeframe to Alpha Vantage function
        av_intervals = {
            "M1": "FX_INTRADAY",
            "M5": "FX_INTRADAY", 
            "M15": "FX_INTRADAY",
            "M30": "FX_INTRADAY",
            "H1": "FX_INTRADAY",
            "H4": "FX_INTRADAY",
        }
        
        interval_map = {
            "M1": "1min",
            "M5": "5min",
            "M15": "15min",
            "M30": "30min",
            "H1": "60min",
            "H4": "60min",
        }
        
        interval = interval_map.get(timeframe, "60min")
        
        url = "https://www.alphavantage.co/query"
        params = {
            "function": "FX_INTRADAY",
            "from_symbol": from_symbol,
            "to_symbol": to_symbol,
            "interval": interval,
            "apikey": ALPHA_VANTAGE_API_KEY,
        }
        
        response = self.session.get(url, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        time_series_key = f"Time Series FX ({interval})"
        if time_series_key not in data:
            return None
        
        records = []
        for ts, values in data[time_series_key].items():
            records.append({
                "timestamp": ts,
                "open": float(values["1. open"]),
                "high": float(values["2. high"]),
                "low": float(values["3. low"]),
                "close": float(values["4. close"]),
            })
        
        df = pd.DataFrame(records)
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
        df["volume"] = 0  # Alpha Vantage doesn't provide volume for FX
        df = df.sort_values("timestamp").reset_index(drop=True)
        df = df.dropna()
        df = df.tail(limit)
        
        logger.info("Fetched %d rows from Alpha Vantage for %s %s", len(df), pair, timeframe)
        return df
    
    @staticmethod
    def _convert_timeframe(timeframe: str) -> tuple:
        """Convert our timeframe format to Polygon multiplier/timespan."""
        mapping = {
            "M1": (1, "minute"),
            "M5": (5, "minute"),
            "M15": (15, "minute"),
            "M30": (30, "minute"),
            "H1": (1, "hour"),
            "H4": (4, "hour"),
        }
        return mapping.get(timeframe, (1, "hour"))
    
    @staticmethod
    def _estimate_duration(timeframe: str, limit: int) -> timedelta:
        """Estimate duration needed for the given number of candles."""
        multipliers = {
            "M1": 1,
            "M5": 5,
            "M15": 15,
            "M30": 30,
            "H1": 60,
            "H4": 240,
        }
        minutes = multipliers.get(timeframe, 60) * limit
        return timedelta(minutes=minutes * 2)  # 2x buffer for weekends/holidays