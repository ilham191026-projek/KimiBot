"""
Lot Size Calculator.
Computes position size from account capital and risk percentage per trade.
"""

from typing import Dict

from utils.logger import get_logger
from utils.pip_calculator import (
    get_pip_value,
    get_contract_size,
    pips_to_price,
)

logger = get_logger(__name__)


def calculate_lot_size(
    capital: float,
    risk_pct: float,
    sl_pips: float,
    instrument: str,
) -> Dict:
    """
    Calculate lot size based on capital, risk percentage, and SL distance.
    
    Formula:
    - Dollar Risk = Capital × Risk%
    - Pip Value per Lot = pip_value × contract_size
    - Lot Size = Dollar Risk / (SL_pips × Pip Value per Lot)
    
    Args:
        capital: Account balance in USD
        risk_pct: Risk per trade as percentage (e.g., 1.0 = 1%)
        sl_pips: Stop loss distance in pips
        instrument: Symbol (e.g., "EURUSD")
        
    Returns:
        Dict:
        {
            lot_size: float,
            dollar_risk: float,
            pip_risk: float,
            margin_required: float | None,
        }
    """
    # Calculate dollar risk amount
    dollar_risk = capital * (risk_pct / 100.0)
    
    # Get instrument specifications
    pip_val = get_pip_value(instrument)
    contract = get_contract_size(instrument)
    
    # Calculate pip value per standard lot
    pip_value_per_lot = pip_val * contract
    
    # Calculate lot size
    if sl_pips <= 0:
        logger.warning("Invalid SL pips: %.1f, using minimum lot", sl_pips)
        return {
            "lot_size": 0.01,
            "dollar_risk": dollar_risk,
            "pip_risk": sl_pips,
            "margin_required": None,
        }
    
    lot_size = dollar_risk / (sl_pips * pip_value_per_lot)
    
    # Round to standard lot sizes (0.01 increments for micro lots)
    lot_size = max(0.01, round(lot_size, 2))
    
    # Recalculate actual dollar risk with rounded lot size
    actual_dollar_risk = lot_size * sl_pips * pip_value_per_lot
    
    logger.info(
        "Lot size for %s: capital=$%.0f, risk=%.1f%%, SL=%.1f pips → lot=%.2f, $risk=$%.2f",
        instrument, capital, risk_pct, sl_pips, lot_size, actual_dollar_risk
    )
    
    return {
        "lot_size": lot_size,
        "dollar_risk": round(actual_dollar_risk, 2),
        "pip_risk": round(sl_pips, 1),
        "margin_required": None,  # Would require leverage info
    }