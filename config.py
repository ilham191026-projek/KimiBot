"""
SMC/ICT/CRT/MSNR Bot v3.0 - Configuration
All constants, settings, pip values, and session times.
"""

import os
from dataclasses import dataclass
from typing import Dict, List
from dotenv import load_dotenv

load_dotenv()

# ── Trading Sessions (GMT) ──────────────────────────────────────────────────
SESSION_LONDON_START = os.getenv("SESSION_LONDON_START", "07:00")
SESSION_LONDON_END = os.getenv("SESSION_LONDON_END", "12:00")
SESSION_NY_START = os.getenv("SESSION_NY_START", "13:00")
SESSION_NY_END = os.getenv("SESSION_NY_END", "17:00")

# ── Scan Settings ────────────────────────────────────────────────────────────
SCAN_INTERVAL_SECONDS = int(os.getenv("SCAN_INTERVAL_SECONDS", "60"))
COOLDOWN_MINUTES = 30
CRT_LOOKBACK = 30

# ── Volatility Gate Thresholds ──────────────────────────────────────────────
ADX_THRESHOLD = 25
ATR_MIN_PIPS = 8
ATR_MAX_PIPS = 35

# ── Spread Filter ────────────────────────────────────────────────────────────
MAX_SPREAD_PIPS = 2

# ── Risk Defaults ────────────────────────────────────────────────────────────
DEFAULT_CAPITAL = float(os.getenv("DEFAULT_CAPITAL", "1000"))
DEFAULT_RISK_PCT = float(os.getenv("DEFAULT_RISK_PCT", "1.0"))
MIN_SL_PIPS = 15
MAX_SL_PIPS = 20
TP1_RR = 1.5
TP2_RR = 2.5
TRAILING_STOP_PIPS = 8

# ── Confluence Settings ─────────────────────────────────────────────────────
MIN_CONFLUENCE_SCORE = 5  # Out of 6 layers
MAX_CANDLE_AGE_HOURS = 4

# ── API Keys ─────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY", "")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "")
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ── Monitored Pairs ──────────────────────────────────────────────────────────
DEFAULT_PAIRS: List[str] = [
    "XAUUSD",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "GBPJPY",
    "USDCHF",
    "AUDUSD",
    "USDCAD",
]

# ── Timeframe Mapping ────────────────────────────────────────────────────────
TIMEFRAMES = {
    "M1": "1min",
    "M5": "5min",
    "M15": "15min",
    "M30": "30min",
    "H1": "1hour",
    "H4": "4hour",
}

# ── Instrument Specifications ────────────────────────────────────────────────
@dataclass
class InstrumentSpec:
    symbol: str
    pip_value: float
    contract_size: float
    digits: int
    spread_avg: float  # Average spread in pips


INSTRUMENTS: Dict[str, InstrumentSpec] = {
    "XAUUSD": InstrumentSpec("XAUUSD", 0.1, 100, 2, 0.3),
    "EURUSD": InstrumentSpec("EURUSD", 0.0001, 100000, 5, 0.1),
    "GBPUSD": InstrumentSpec("GBPUSD", 0.0001, 100000, 5, 0.2),
    "USDJPY": InstrumentSpec("USDJPY", 0.01, 100000, 3, 0.1),
    "GBPJPY": InstrumentSpec("GBPJPY", 0.01, 100000, 3, 0.3),
    "USDCHF": InstrumentSpec("USDCHF", 0.0001, 100000, 5, 0.2),
    "AUDUSD": InstrumentSpec("AUDUSD", 0.0001, 100000, 5, 0.1),
    "USDCAD": InstrumentSpec("USDCAD", 0.0001, 100000, 5, 0.2),
}

# ── Layer Weights for Confluence Scoring ────────────────────────────────────
LAYER_WEIGHTS = {
    "h4_bias": 1.0,
    "h1_ob_fvg": 1.0,
    "m30_msnr": 1.0,
    "m15_crt": 1.0,
    "m5_mss": 1.0,
    "m1_entry": 1.0,
}

# ── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"