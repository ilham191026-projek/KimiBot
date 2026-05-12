"""
Trailing Stop Logic — 8-pip trailing stop that activates after breakeven.
Moves SL to lock in profits as price advances in the trade direction.
"""

from typing import Dict, Optional

from config import TRAILING_STOP_PIPS
from utils.logger import get_logger
from utils.pip_calculator import pips_to_price, price_to_pips

logger = get_logger(__name__)


class TrailingStopManager:
    """Manages trailing stop logic for an open position."""
    
    def __init__(
        self,
        instrument: str,
        direction: str,
        entry_price: float,
        initial_sl: float,
        trailing_pips: float = TRAILING_STOP_PIPS,
    ):
        """
        Initialize trailing stop manager.
        
        Args:
            instrument: Symbol (e.g., "EURUSD")
            direction: "bullish" or "bearish"
            entry_price: Position entry price
            initial_sl: Initial stop loss price
            trailing_pips: Number of pips to trail (default 8)
        """
        self.instrument = instrument
        self.direction = direction
        self.entry_price = entry_price
        self.initial_sl = initial_sl
        self.current_sl = initial_sl
        self.trailing_distance = pips_to_price(instrument, trailing_pips)
        self.breakeven_reached = False
        self.active = False
        
        logger.info(
            "TrailingStop initialized: %s %s entry=%.5f SL=%.5f trail=%.1f pips",
            instrument, direction, entry_price, initial_sl, trailing_pips
        )
    
    def update(self, current_price: float) -> Dict:
        """
        Update trailing stop based on current price.
        
        Args:
            current_price: Current market price
            
        Returns:
            Dict with updated SL and status
        """
        if self.direction == "bullish":
            return self._update_bullish(current_price)
        else:
            return self._update_bearish(current_price)
    
    def _update_bullish(self, current_price: float) -> Dict:
        """Update trailing stop for long position."""
        # Check if breakeven reached (price moved favorably by at least SL distance)
        profit_pips = price_to_pips(self.instrument, current_price - self.entry_price)
        
        if not self.breakeven_reached and current_price > self.entry_price:
            sl_distance = self.entry_price - self.initial_sl
            if current_price >= self.entry_price + sl_distance:
                self.breakeven_reached = True
                self.current_sl = self.entry_price  # Move to breakeven
                logger.info("Breakeven reached for %s long", self.instrument)
        
        # Activate trailing stop after breakeven
        if self.breakeven_reached:
            self.active = True
            new_sl = current_price - self.trailing_distance
            
            # Only move SL up, never down
            if new_sl > self.current_sl:
                self.current_sl = new_sl
                logger.info(
                    "Trailing stop moved: %.5f → %.5f (price=%.5f)",
                    self.current_sl, new_sl, current_price
                )
        
        return {
            "active": self.active,
            "breakeven_reached": self.breakeven_reached,
            "current_sl": round(self.current_sl, 5),
            "profit_pips": round(profit_pips, 1),
        }
    
    def _update_bearish(self, current_price: float) -> Dict:
        """Update trailing stop for short position."""
        # Check if breakeven reached
        profit_pips = price_to_pips(self.instrument, self.entry_price - current_price)
        
        if not self.breakeven_reached and current_price < self.entry_price:
            sl_distance = self.initial_sl - self.entry_price
            if current_price <= self.entry_price - sl_distance:
                self.breakeven_reached = True
                self.current_sl = self.entry_price  # Move to breakeven
                logger.info("Breakeven reached for %s short", self.instrument)
        
        # Activate trailing stop after breakeven
        if self.breakeven_reached:
            self.active = True
            new_sl = current_price + self.trailing_distance
            
            # Only move SL down, never up
            if new_sl < self.current_sl:
                self.current_sl = new_sl
                logger.info(
                    "Trailing stop moved: %.5f → %.5f (price=%.5f)",
                    self.current_sl, new_sl, current_price
                )
        
        return {
            "active": self.active,
            "breakeven_reached": self.breakeven_reached,
            "current_sl": round(self.current_sl, 5),
            "profit_pips": round(profit_pips, 1),
        }
    
    def should_exit(self, current_price: float) -> bool:
        """Check if price has hit the trailing stop."""
        if self.direction == "bullish":
            return current_price <= self.current_sl
        else:
            return current_price >= self.current_sl
    
    def get_status(self) -> Dict:
        """Get current trailing stop status."""
        return {
            "instrument": self.instrument,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "initial_sl": self.initial_sl,
            "current_sl": round(self.current_sl, 5),
            "breakeven_reached": self.breakeven_reached,
            "active": self.active,
        }