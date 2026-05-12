"""
Signal Builder — Assembles the final signal object from all analysis layers.
Combines confluence results, SL/TP calculations, risk parameters, and AI narrative.
"""

from typing import Dict, Optional, List
import asyncio

from utils.logger import get_logger
from utils.time_utils import now_gmt, get_current_session, format_gmt
from risk.sl_tp_calculator import calculate_sl_tp, find_m15_swing, find_m30_swing
from risk.lot_sizer import calculate_lot_size
from ai.signal_narrator import generate_narrative
from config import (
    DEFAULT_CAPITAL,
    DEFAULT_RISK_PCT,
    MIN_CONFLUENCE_SCORE,
)

logger = get_logger(__name__)


class SignalBuilder:
    """Builds complete trading signals from analysis results."""
    
    def __init__(self):
        self.user_capital = {}  # chat_id -> capital
        self.user_risk = {}     # chat_id -> risk_pct
    
    def set_user_risk(self, chat_id: int, capital: float, risk_pct: float) -> None:
        """Set risk parameters for a user."""
        self.user_capital[chat_id] = capital
        self.user_risk[chat_id] = risk_pct
        logger.info("Risk set for user %d: capital=$%.0f, risk=%.1f%%", chat_id, capital, risk_pct)
    
    def get_user_risk(self, chat_id: int) -> tuple:
        """Get risk parameters for a user (with defaults)."""
        capital = self.user_capital.get(chat_id, DEFAULT_CAPITAL)
        risk_pct = self.user_risk.get(chat_id, DEFAULT_RISK_PCT)
        return capital, risk_pct
    
    def build_signal(
        self,
        pair: str,
        confluence_results: Dict,
        dataframes: Dict,
        news_events: List,
        chat_id: int = 0,
    ) -> Optional[Dict]:
        """
        Build a complete signal from confluence analysis results.
        
        Args:
            pair: Instrument symbol
            confluence_results: Results from confluence.run_full_analysis()
            dataframes: Dict of OHLCV DataFrames for all timeframes
            news_events: List of upcoming economic events
            chat_id: Telegram chat ID for user-specific risk settings
            
        Returns:
            Complete signal dict or None if signal is invalid
        """
        # Check confluence passed
        if not confluence_results.get("confluence_passed", False):
            logger.info("Signal for %s rejected: confluence failed (%d/6)",
                       pair, confluence_results.get("confluence_score", 0))
            return None
        
        direction = confluence_results.get("direction")
        if not direction:
            logger.info("Signal for %s rejected: no direction", pair)
            return None
        
        # Get current price from M1
        m1_df = dataframes.get("M1")
        if m1_df is None or len(m1_df) < 1:
            logger.warning("No M1 data for entry price on %s", pair)
            return None
        
        entry_price = float(m1_df["close"].iloc[-1])
        
        # Find swing points for SL
        m15_df = dataframes.get("M15")
        m30_df = dataframes.get("M30")
        
        crt_data = confluence_results.get("layers", {}).get("m15_crt", {})
        crt_sweep_level = crt_data.get("crt", {}).get("sweep_level") if crt_data.get("crt") else None
        
        crt_swing = find_m15_swing(m15_df, direction, crt_sweep_level)
        m30_swing = find_m30_swing(m30_df, direction)
        
        # Calculate SL/TP
        sl_tp = calculate_sl_tp(
            direction=direction,
            entry_price=entry_price,
            crt_swing=crt_swing,
            m30_swing=m30_swing,
            instrument=pair,
        )
        
        if not sl_tp.get("valid", False):
            logger.info("Signal for %s rejected: invalid SL/TP (%s)",
                       pair, sl_tp.get("reason", "unknown"))
            return None
        
        # Calculate risk parameters
        capital, risk_pct = self.get_user_risk(chat_id)
        risk = calculate_lot_size(
            capital=capital,
            risk_pct=risk_pct,
            sl_pips=sl_tp["sl_pip"],
            instrument=pair,
        )
        
        # Build signal object
        now = now_gmt()
        session = get_current_session(now)
        
        signal = {
            "pair": pair,
            "direction": direction,
            "session": session,
            "timestamp": format_gmt(now),
            "confluence_score": confluence_results["confluence_score"],
            "entry_price": round(entry_price, 5),
            "sl_tp": sl_tp,
            "risk": risk,
            "capital": capital,
            "risk_pct": risk_pct,
            "layers": confluence_results.get("layers", {}),
            "layer_results": confluence_results.get("layer_results", []),
            "news": news_events,
            "layer_summary": self._build_layer_summary(confluence_results),
        }
        
        logger.info(
            "Signal built for %s %s: entry=%.5f, SL=%.5f, TP1=%.5f, lot=%.2f",
            pair, direction, entry_price, sl_tp["sl"], sl_tp["tp1"], risk["lot_size"]
        )
        
        return signal
    
    @staticmethod
    def _build_layer_summary(confluence_results: Dict) -> str:
        """Build text summary of layer results."""
        lines = []
        for lr in confluence_results.get("layer_results", []):
            icon = "PASS" if lr.get("valid", False) else "FAIL"
            lines.append(f"{lr.get('name', 'Unknown')}: {icon}")
        return " | ".join(lines)
    
    async def build_with_narrative(
        self,
        pair: str,
        confluence_results: Dict,
        dataframes: Dict,
        news_events: List,
        chat_id: int = 0,
    ) -> Optional[Dict]:
        """
        Build signal and generate AI narrative.
        
        Args:
            pair: Instrument symbol
            confluence_results: Results from confluence analysis
            dataframes: Dict of OHLCV DataFrames
            news_events: List of upcoming economic events
            chat_id: Telegram chat ID
            
        Returns:
            Signal dict with AI narrative, or None if invalid
        """
        signal = self.build_signal(pair, confluence_results, dataframes, news_events, chat_id)
        if not signal:
            return None
        
        # Generate AI narrative
        narrative = await generate_narrative(signal)
        signal["narrative"] = narrative
        
        return signal