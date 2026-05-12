"""
Instrument-specific pip value calculations.
"""

from typing import Dict
from config import INSTRUMENTS


def get_pip_value(instrument: str) -> float:
    """Return the pip value for a given instrument.
    
    JPY pairs = 0.01
    Gold (XAUUSD) = 0.1
    Standard forex pairs = 0.0001
    """
    spec = INSTRUMENTS.get(instrument)
    if spec:
        return spec.pip_value
    
    # Fallback detection
    if "JPY" in instrument:
        return 0.01
    elif "XAU" in instrument or "GOLD" in instrument.upper():
        return 0.1
    else:
        return 0.0001


def pips_to_price(instrument: str, pips: float) -> float:
    """Convert pip amount to price distance for an instrument."""
    return pips * get_pip_value(instrument)


def price_to_pips(instrument: str, price_distance: float) -> float:
    """Convert price distance to pip amount for an instrument."""
    return price_distance / get_pip_value(instrument)


def calculate_pip_difference(instrument: str, price1: float, price2: float) -> float:
    """Calculate the pip difference between two prices."""
    return abs(price1 - price2) / get_pip_value(instrument)


def format_pips(instrument: str, price_distance: float) -> str:
    """Format price distance as pip string with 1 decimal."""
    pips = price_to_pips(instrument, price_distance)
    return f"{pips:.1f}"


def get_contract_size(instrument: str) -> float:
    """Return the contract size for an instrument."""
    spec = INSTRUMENTS.get(instrument)
    if spec:
        return spec.contract_size
    return 100000  # Default standard lot


def get_digits(instrument: str) -> int:
    """Return the decimal digits for an instrument's price."""
    spec = INSTRUMENTS.get(instrument)
    if spec:
        return spec.digits
    return 5