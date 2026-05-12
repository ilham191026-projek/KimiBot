"""
Session checks, GMT handling, and trading time utilities.
"""

from datetime import datetime, time
from typing import Optional
import pytz

from config import (
    SESSION_LONDON_START,
    SESSION_LONDON_END,
    SESSION_NY_START,
    SESSION_NY_END,
)


def now_gmt() -> datetime:
    """Return current time in GMT/UTC."""
    return datetime.now(pytz.UTC)


def _parse_time(t: str) -> time:
    """Parse 'HH:MM' string to time object."""
    h, m = map(int, t.split(":"))
    return time(h, m)


def is_london_session(dt: Optional[datetime] = None) -> bool:
    """Check if given time (default now) is within London session."""
    dt = dt or now_gmt()
    start = _parse_time(SESSION_LONDON_START)
    end = _parse_time(SESSION_LONDON_END)
    return start <= dt.time() <= end


def is_ny_session(dt: Optional[datetime] = None) -> bool:
    """Check if given time (default now) is within New York session."""
    dt = dt or now_gmt()
    start = _parse_time(SESSION_NY_START)
    end = _parse_time(SESSION_NY_END)
    return start <= dt.time() <= end


def is_active_session(dt: Optional[datetime] = None) -> bool:
    """Check if we are in either London or NY session."""
    return is_london_session(dt) or is_ny_session(dt)


def get_current_session(dt: Optional[datetime] = None) -> str:
    """Return the name of the current active session."""
    dt = dt or now_gmt()
    if is_london_session(dt):
        return "London"
    elif is_ny_session(dt):
        return "New York"
    else:
        return "Off-Hours"


def time_until_next_session(dt: Optional[datetime] = None) -> int:
    """Return minutes until the next trading session starts."""
    dt = dt or now_gmt()
    today = dt.date()

    london_start = datetime.combine(today, _parse_time(SESSION_LONDON_START), tzinfo=pytz.UTC)
    london_end = datetime.combine(today, _parse_time(SESSION_LONDON_END), tzinfo=pytz.UTC)
    ny_start = datetime.combine(today, _parse_time(SESSION_NY_START), tzinfo=pytz.UTC)

    if dt < london_start:
        return int((london_start - dt).total_seconds() // 60)
    elif london_end < dt < ny_start:
        return int((ny_start - dt).total_seconds() // 60)
    else:
        # After NY session, wait for next day's London
        tomorrow = london_start + __import__('datetime').timedelta(days=1)
        return int((tomorrow - dt).total_seconds() // 60)


def format_gmt(dt: datetime) -> str:
    """Format datetime as GMT string."""
    return dt.astimezone(pytz.UTC).strftime("%Y-%m-%d %H:%M GMT")


def candle_age_minutes(timestamp, reference: Optional[datetime] = None) -> float:
    """Calculate how many minutes ago a candle timestamp was."""
    reference = reference or now_gmt()
    if hasattr(timestamp, 'to_pydatetime'):
        timestamp = timestamp.to_pydatetime()
    if timestamp.tzinfo is None:
        timestamp = pytz.UTC.localize(timestamp)
    return (reference - timestamp).total_seconds() / 60.0