"""
Economic news calendar scraper/API for high-impact events.
Fetches from Forex Factory or Investing.com.
"""

import re
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup

from utils.logger import get_logger
from utils.time_utils import now_gmt

logger = get_logger(__name__)


@dataclass
class EconomicEvent:
    """Represents a single economic event."""
    time: datetime
    currency: str
    impact: str  # "high", "medium", "low"
    title: str
    actual: Optional[str] = None
    forecast: Optional[str] = None
    previous: Optional[str] = None


def fetch_high_impact_events(hours_ahead: int = 4) -> List[EconomicEvent]:
    """
    Fetch high-impact economic events from Forex Factory.
    
    Args:
        hours_ahead: How many hours ahead to check for events
        
    Returns:
        List of high-impact EconomicEvents in the next N hours
    """
    try:
        return _fetch_forex_factory(hours_ahead)
    except Exception as e:
        logger.error("Failed to fetch calendar: %s", e)
        return []


def _fetch_forex_factory(hours_ahead: int) -> List[EconomicEvent]:
    """Scrape Forex Factory calendar."""
    url = "https://www.forexfactory.com/calendar"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    
    response = requests.get(url, headers=headers, timeout=15)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, "html.parser")
    events = []
    now = now_gmt()
    cutoff = now + timedelta(hours=hours_ahead)
    
    # Find calendar table rows
    for row in soup.find_all("tr", class_="calendar_row"):
        try:
            # Extract time
            time_cell = row.find("td", class_="calendar__time")
            if not time_cell:
                continue
            
            event_time = _parse_event_time(time_cell.text.strip(), now)
            if event_time is None or event_time > cutoff:
                continue
            
            # Extract impact
            impact_cell = row.find("td", class_="calendar__impact")
            impact = "low"
            if impact_cell:
                if impact_cell.find("span", class_="high"):
                    impact = "high"
                elif impact_cell.find("span", class_="medium"):
                    impact = "medium"
            
            # Only include high impact events
            if impact != "high":
                continue
            
            # Extract currency
            currency_cell = row.find("td", class_="calendar__currency")
            currency = currency_cell.text.strip() if currency_cell else ""
            
            # Extract event title
            title_cell = row.find("span", class_="calendar__event-title")
            title = title_cell.text.strip() if title_cell else ""
            
            # Extract actual/forecast/previous
            actual_cell = row.find("td", class_="calendar__actual")
            forecast_cell = row.find("td", class_="calendar__forecast")
            previous_cell = row.find("td", class_="calendar__previous")
            
            event = EconomicEvent(
                time=event_time,
                currency=currency,
                impact=impact,
                title=title,
                actual=actual_cell.text.strip() if actual_cell else None,
                forecast=forecast_cell.text.strip() if forecast_cell else None,
                previous=previous_cell.text.strip() if previous_cell else None,
            )
            events.append(event)
            
        except Exception as e:
            logger.debug("Error parsing calendar row: %s", e)
            continue
    
    logger.info("Found %d high-impact events in next %d hours", len(events), hours_ahead)
    return events


def _parse_event_time(time_str: str, reference: datetime) -> Optional[datetime]:
    """Parse event time string to datetime."""
    try:
        # Parse time like "8:30am" or "12:00pm"
        time_str = time_str.lower().strip()
        
        # Match time pattern
        match = re.match(r'(\d{1,2}):(\d{2})([ap]m)', time_str)
        if not match:
            return None
        
        hour = int(match.group(1))
        minute = int(match.group(2))
        ampm = match.group(3)
        
        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0
        
        # Use reference date (assume EST for Forex Factory, convert to UTC)
        event_time = reference.replace(hour=hour, minute=minute, second=0, microsecond=0)
        # Forex Factory shows times in ET (EST/EDT), roughly UTC-5 or UTC-4
        # This is a simplification - in production, handle DST properly
        event_time = event_time + timedelta(hours=5)  # Convert ET to UTC
        
        return event_time
    except Exception as e:
        logger.debug("Error parsing time '%s': %s", time_str, e)
        return None


def format_events_for_signal(events: List[EconomicEvent]) -> str:
    """Format events list as text for signal display."""
    if not events:
        return "No high-impact events in the next 4 hours."
    
    lines = ["⚠️ *Upcoming High-Impact Events:*"]
    for ev in events[:5]:  # Show max 5
        time_str = ev.time.strftime("%H:%M GMT")
        lines.append(f"  • {time_str} - {ev.currency}: {ev.title}")
    
    return "\n".join(lines)


def has_high_impact_for_pair(events: List[EconomicEvent], pair: str) -> bool:
    """Check if any high-impact event affects a given pair."""
    currencies = [pair[:3], pair[3:]] if len(pair) == 6 else ["USD"]
    for event in events:
        if event.currency in currencies:
            return True
    return False