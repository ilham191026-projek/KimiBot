"""
Signal Formatter — Formats trading signals as Telegram HTML messages.
Uses emojis and clean formatting for professional presentation.
"""

from typing import Dict, Optional, List
from datetime import datetime

from utils.logger import get_logger
from utils.pip_calculator import get_pip_value

logger = get_logger(__name__)


def format_signal_html(signal: Dict) -> str:
    """
    Format a complete signal as a Telegram HTML message.
    
    Args:
        signal: Complete signal dict from SignalBuilder
        
    Returns:
        Formatted HTML string for Telegram
    """
    pair = signal.get("pair", "Unknown")
    direction = signal.get("direction", "Unknown")
    session = signal.get("session", "Unknown")
    timestamp = signal.get("timestamp", "")
    confluence_score = signal.get("confluence_score", 0)
    
    # Direction emoji
    dir_emoji = "🟢" if direction == "bullish" else "🔴"
    dir_text = "LONG" if direction == "bullish" else "SHORT"
    
    # Entry and prices
    entry = signal.get("entry_price", "N/A")
    
    # SL/TP
    sl_tp = signal.get("sl_tp", {})
    sl = sl_tp.get("sl", "N/A")
    tp1 = sl_tp.get("tp1", "N/A")
    tp2 = sl_tp.get("tp2", "N/A")
    rr1 = sl_tp.get("rr1", "N/A")
    rr2 = sl_tp.get("rr2", "N/A")
    sl_pip = sl_tp.get("sl_pip", "N/A")
    
    # Risk
    risk = signal.get("risk", {})
    lot_size = risk.get("lot_size", "N/A")
    dollar_risk = risk.get("dollar_risk", "N/A")
    pip_risk = risk.get("pip_risk", "N/A")
    
    # Capital
    capital = signal.get("capital", 0)
    risk_pct = signal.get("risk_pct", 0)
    
    # Layer results
    layer_results = signal.get("layer_results", [])
    layer_lines = []
    for lr in layer_results:
        valid = lr.get("valid", False)
        icon = "✅" if valid else "❌"
        stale_icon = "⚠️" if (not valid and "stale" in str(lr).lower()) else ""
        name = lr.get("name", "Unknown")
        layer_lines.append(f"{icon} {name} {stale_icon}".strip())
    
    # Narrative
    narrative = signal.get("narrative", "")
    
    # News
    news = signal.get("news", [])
    news_text = format_news(news)
    
    # Build message
    lines = [
        f"<b>{dir_emoji} {pair} {dir_text}</b>",
        f"",
        f"<b>📊 Confluence Score:</b> {confluence_score}/6",
        f"<b>🌍 Session:</b> {session}",
        f"<b>🕐 Time:</b> {timestamp}",
        f"",
        f"<b>💰 Entry:</b> <code>{entry}</code>",
        f"",
        f"<b>🛡️ Stop Loss:</b> <code>{sl}</code> ({sl_pip} pips)",
        f"<b>🎯 TP1:</b> <code>{tp1}</code> (RR {rr1}:1)",
        f"<b>🏆 TP2:</b> <code>{tp2}</code> (RR {rr2}:1)",
        f"",
        f"<b>📈 Risk Parameters</b>",
        f"  Lot Size: <code>{lot_size}</code>",
        f"  Dollar Risk: <code>${dollar_risk}</code>",
        f"  Pip SL: <code>{pip_risk}</code>",
        f"  Capital: <code>${capital:.0f}</code> @ <code>{risk_pct:.1f}%</code>",
        f"",
        f"<b>🔍 Layer Validation</b>",
    ]
    
    lines.extend([f"  {line}" for line in layer_lines])
    
    # Narrative section
    if narrative:
        lines.extend([
            f"",
            f"<b>🤖 AI Trade Rationale</b>",
            f"<i>{narrative}</i>",
        ])
    
    # News section
    if news_text:
        lines.extend([
            f"",
            f"{news_text}",
        ])
    
    lines.extend([
        f"",
        f"<i>SMC/ICT/CRT/MSNR Bot v3.0</i>",
    ])
    
    return "\n".join(lines)


def format_news(news_events: List) -> str:
    """Format news events for signal display."""
    if not news_events:
        return ""
    
    # Handle both list of EconomicEvent objects and list of dicts
    lines = ["⚠️ <b>Upcoming High-Impact Events:</b>"]
    
    for i, event in enumerate(news_events[:5]):  # Max 5 events
        if hasattr(event, 'time'):
            # EconomicEvent dataclass
            time_str = event.time.strftime("%H:%M GMT") if hasattr(event.time, 'strftime') else str(event.time)
            currency = event.currency
            title = event.title
        elif isinstance(event, dict):
            time_str = event.get("time", "")
            if hasattr(time_str, 'strftime'):
                time_str = time_str.strftime("%H:%M GMT")
            currency = event.get("currency", "")
            title = event.get("title", "")
        else:
            continue
        
        lines.append(f"  • {time_str} — {currency}: {title}")
    
    return "\n".join(lines)


def format_status(
    active_pairs: List[str],
    last_scan_time: Optional[str],
    cooldown_status: Dict,
) -> str:
    """
    Format bot status message.
    
    Args:
        active_pairs: List of currently monitored pairs
        last_scan_time: Timestamp of last scan
        cooldown_status: Dict of pair -> cooldown info
        
    Returns:
        Formatted HTML string
    """
    lines = [
        f"<b>🤖 SMC/ICT/CRT/MSNR Bot v3.0 — Status</b>",
        f"",
        f"<b>📊 Active Pairs ({len(active_pairs)}):</b>",
    ]
    
    for pair in active_pairs:
        cd_info = cooldown_status.get(pair, {})
        if cd_info.get("on_cooldown", False):
            remaining = cd_info.get("remaining_minutes", 0)
            lines.append(f"  🔒 {pair} (cooldown: {remaining}m remaining)")
        else:
            lines.append(f"  ✅ {pair}")
    
    lines.extend([
        f"",
        f"<b>🕐 Last Scan:</b> {last_scan_time or 'Never'}",
        f"",
        f"<b>⏱️ Active Cooldowns:</b>",
    ])
    
    active_cds = {
        k: v for k, v in cooldown_status.items()
        if v.get("on_cooldown", False)
    }
    
    if active_cds:
        for pair, info in active_cds.items():
            remaining = info.get("remaining_minutes", 0)
            lines.append(f"  • {pair}: {remaining} min")
    else:
        lines.append("  None")
    
    lines.append(f"")
    lines.append(f"<i>Use /signal to force an immediate scan</i>")
    
    return "\n".join(lines)


def format_pairs_list(pairs: List[str]) -> str:
    """Format the list of monitored pairs."""
    lines = [
        f"<b>📋 Monitored Pairs ({len(pairs)}):</b>",
        f"",
    ]
    
    for i, pair in enumerate(pairs, 1):
        lines.append(f"  {i}. {pair}")
    
    lines.extend([
        f"",
        f"<i>Use /setpairs to customize (e.g., /setpairs EURUSD,GBPUSD)</i>",
    ])
    
    return "\n".join(lines)


def format_welcome_message() -> str:
    """Format the welcome message for new users."""
    return """<b>🤖 Welcome to SMC/ICT/CRT/MSNR Bot v3.0!</b>

This bot performs automated multi-timeframe technical analysis using a 6-layer Smart Money strategy:

<b>📊 Available Commands:</b>
• /start — Show this welcome message
• /status — Check bot status and cooldowns
• /signal — Force an immediate scan
• /risk &lt;capital&gt; &lt;risk%&gt; — Set your risk parameters
• /pairs — List monitored pairs
• /news — Show upcoming economic events
• /setpairs &lt;pair1,pair2,...&gt; — Customize pairs

<b>🔍 Analysis Layers:</b>
1. H4 — Market Structure (HH/HL/LH/LL)
2. H1 — Order Blocks + Fair Value Gaps
3. M30 — MSNR Wick Detection
4. M15 — CRT 3-Step Pattern (Liquidity Sweep)
5. M5 — Market Structure Shift + FVG
6. M1 — Precision Entry Confirmation

<b>⚠️ Requirements for a signal:</b>
• Score ≥ 5/6 layers
• ADX > 25, ATR 8-35 pips
• Spread ≤ 2 pips
• 30-min cooldown per pair

<b>Get started:</b> Use /risk to set your capital and risk %
"""


def format_risk_confirmation(capital: float, risk_pct: float) -> str:
    """Format risk setting confirmation."""
    dollar_risk = capital * (risk_pct / 100)
    return (
        f"<b>✅ Risk Parameters Updated</b>\n\n"
        f"Capital: <code>${capital:.0f}</code>\n"
        f"Risk per trade: <code>{risk_pct:.1f}%</code>\n"
        f"Dollar risk per trade: <code>${dollar_risk:.2f}</code>\n\n"
        f"<i>These settings will be used for all future signals.</i>"
    )


def format_scan_start(pairs: List[str]) -> str:
    """Format scan start message."""
    return (
        f"<b>🔍 Starting manual scan...</b>\n"
        f"Scanning {len(pairs)} pairs across 6 timeframes.\n"
        f"This may take a few moments."
    )


def format_no_signal(pair: str, confluence_score: int) -> str:
    """Format message when no signal is found."""
    return f"❌ <b>{pair}</b>: No signal ({confluence_score}/6 layers)"


def format_error_message(error: str) -> str:
    """Format a user-friendly error message."""
    return f"<b>⚠️ Error</b>\n\nSomething went wrong. Please try again later.\n\n<i>{error}</i>"