"""
Cooldown System — 30-minute lock per pair after each entry signal.
Prevents overtrading and signal spam.
"""

import time
from typing import Dict, Optional, Set
from dataclasses import dataclass, field

from config import COOLDOWN_MINUTES
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CooldownEntry:
    """Tracks cooldown state for a trading pair."""
    pair: str
    last_signal_time: float = 0.0
    signals_count: int = 0


class CooldownManager:
    """Manages cooldown state for all trading pairs."""
    
    def __init__(self, cooldown_minutes: int = COOLDOWN_MINUTES):
        self.cooldown_seconds = cooldown_minutes * 60
        self._cooldowns: Dict[str, CooldownEntry] = {}
        self._cooldown_minutes = cooldown_minutes
    
    def is_on_cooldown(self, pair: str) -> bool:
        """Check if a pair is currently on cooldown."""
        entry = self._cooldowns.get(pair)
        if entry is None:
            return False
        
        elapsed = time.time() - entry.last_signal_time
        return elapsed < self.cooldown_seconds
    
    def time_remaining(self, pair: str) -> float:
        """Get remaining cooldown time in seconds for a pair."""
        entry = self._cooldowns.get(pair)
        if entry is None:
            return 0.0
        
        elapsed = time.time() - entry.last_signal_time
        remaining = self.cooldown_seconds - elapsed
        return max(0.0, remaining)
    
    def trigger(self, pair: str) -> None:
        """Trigger cooldown for a pair after a signal is sent."""
        now = time.time()
        
        if pair not in self._cooldowns:
            self._cooldowns[pair] = CooldownEntry(pair=pair)
        
        self._cooldowns[pair].last_signal_time = now
        self._cooldowns[pair].signals_count += 1
        
        logger.info("Cooldown triggered for %s (30 min)", pair)
    
    def reset(self, pair: str) -> None:
        """Manually reset cooldown for a pair."""
        if pair in self._cooldowns:
            self._cooldowns[pair].last_signal_time = 0.0
            logger.info("Cooldown manually reset for %s", pair)
    
    def reset_all(self) -> None:
        """Reset all cooldowns."""
        self._cooldowns = {}
        logger.info("All cooldowns reset")
    
    def get_status(self) -> Dict[str, Dict]:
        """Get cooldown status for all tracked pairs."""
        status = {}
        for pair, entry in self._cooldowns.items():
            remaining = self.time_remaining(pair)
            status[pair] = {
                "on_cooldown": remaining > 0,
                "remaining_seconds": round(remaining, 0),
                "remaining_minutes": round(remaining / 60, 1),
                "total_signals": entry.signals_count,
                "last_signal_ago": round(time.time() - entry.last_signal_time, 0),
            }
        return status
    
    def get_active_cooldowns(self) -> Dict[str, float]:
        """Get pairs currently on cooldown with remaining seconds."""
        return {
            pair: round(self.time_remaining(pair), 0)
            for pair in self._cooldowns
            if self.is_on_cooldown(pair)
        }