"""
Telegram Bot Handler — User interface for the SMC Bot.
Implements all commands using python-telegram-bot v20+.
"""

import asyncio
import json
import os
from typing import Dict, List, Optional

from telegram import Update, Bot
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    DEFAULT_PAIRS,
    DEFAULT_CAPITAL,
    DEFAULT_RISK_PCT,
    SCAN_INTERVAL_SECONDS,
)
from utils.logger import get_logger
from utils.time_utils import now_gmt, format_gmt, is_active_session, get_current_session
from data.calendar import fetch_high_impact_events
from signals.signal_builder import SignalBuilder
from signals.signal_formatter import (
    format_signal_html,
    format_status,
    format_pairs_list,
    format_welcome_message,
    format_risk_confirmation,
    format_scan_start,
    format_error_message,
    format_news,
)
from filters.cooldown import CooldownManager
from main import run_scan_for_pair, load_user_settings, save_user_settings

logger = get_logger(__name__)

# ── Conversation States ──────────────────────────────────────────────────────
RISK_CAPITAL, RISK_PCT = range(2)

# ── User Settings Storage ────────────────────────────────────────────────────
USER_SETTINGS_FILE = "user_settings.json"
user_settings: Dict[int, dict] = {}
signal_builder = SignalBuilder()
cooldown_manager = CooldownManager()
active_pairs: List[str] = list(DEFAULT_PAIRS)
last_scan_time: Optional[str] = None


def load_settings() -> None:
    """Load user settings from disk."""
    global user_settings
    if os.path.exists(USER_SETTINGS_FILE):
        try:
            with open(USER_SETTINGS_FILE, "r") as f:
                data = json.load(f)
                user_settings = {int(k): v for k, v in data.items()}
            logger.info("Loaded settings for %d users", len(user_settings))
        except Exception as e:
            logger.error("Error loading settings: %s", e)
            user_settings = {}


def save_settings() -> None:
    """Save user settings to disk."""
    try:
        with open(USER_SETTINGS_FILE, "w") as f:
            json.dump(user_settings, f, indent=2)
    except Exception as e:
        logger.error("Error saving settings: %s", e)


def _get_chat_id(update: Update) -> int:
    """Safely get chat ID from update."""
    if update.effective_chat:
        return update.effective_chat.id
    return 0


# ── Command Handlers ─────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command — welcome message."""
    chat_id = _get_chat_id(update)
    
    # Load user's risk settings if available
    if str(chat_id) in user_settings:
        settings = user_settings[str(chat_id)]
        signal_builder.set_user_risk(
            chat_id,
            settings.get("capital", DEFAULT_CAPITAL),
            settings.get("risk_pct", DEFAULT_RISK_PCT),
        )
    
    await update.message.reply_html(format_welcome_message())


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command — show bot status."""
    cooldown_status = cooldown_manager.get_status()
    
    message = format_status(
        active_pairs=active_pairs,
        last_scan_time=last_scan_time,
        cooldown_status=cooldown_status,
    )
    
    await update.message.reply_html(message)


async def cmd_signal(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /signal command — force immediate scan."""
    chat_id = _get_chat_id(update)
    
    # Check if we're in an active session
    if not is_active_session():
        session = get_current_session()
        await update.message.reply_html(
            f"<b>⏸️ Off-Hours</b>\n\n"
            f"Current session: {session}\n"
            f"Scanning is active during London (07:00-12:00 GMT) "
            f"and New York (13:00-17:00 GMT) sessions.\n\n"
            f"<i>Use /status to check when the next session starts.</i>"
        )
        return
    
    await update.message.reply_html(format_scan_start(active_pairs))
    
    signals_found = 0
    
    for pair in active_pairs:
        # Skip if on cooldown
        if cooldown_manager.is_on_cooldown(pair):
            remaining = cooldown_manager.time_remaining(pair)
            await update.message.reply_html(
                f"🔒 <b>{pair}</b> on cooldown ({remaining/60:.0f} min left)"
            )
            continue
        
        try:
            signal = await run_scan_for_pair(pair, chat_id)
            if signal:
                signals_found += 1
                formatted = format_signal_html(signal)
                
                # Telegram message limit is 4096 chars
                if len(formatted) > 4000:
                    formatted = formatted[:4000] + "\n\n<i>(message truncated)</i>"
                
                await update.message.reply_html(formatted)
                cooldown_manager.trigger(pair)
            else:
                pass  # Silently skip no-signal pairs to avoid spam
                
        except Exception as e:
            logger.error("Error scanning %s: %s", pair, e)
            await update.message.reply_html(
                f"❌ <b>{pair}</b>: Scan error"
            )
    
    if signals_found == 0:
        await update.message.reply_html(
            f"<b>🔍 Scan Complete</b>\n\n"
            f"No signals found across {len(active_pairs)} pairs.\n"
            f"All layers must align (≥5/6) for a signal to trigger.\n\n"
            f"<i>Next automatic scan in {SCAN_INTERVAL_SECONDS}s</i>"
        )


async def cmd_risk(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /risk command — set capital and risk percentage."""
    chat_id = _get_chat_id(update)
    args = context.args
    
    if len(args) >= 2:
        # Direct input: /risk 1000 1
        try:
            capital = float(args[0])
            risk_pct = float(args[1])
            
            if capital <= 0 or risk_pct <= 0 or risk_pct > 100:
                await update.message.reply_html(
                    "<b>⚠️ Invalid Input</b>\n\n"
                    "Capital must be > 0 and risk % must be 0-100.\n"
                    "Usage: <code>/risk 1000 1</code>"
                )
                return
            
            _set_user_risk(chat_id, capital, risk_pct)
            await update.message.reply_html(format_risk_confirmation(capital, risk_pct))
            
        except ValueError:
            await update.message.reply_html(
                "<b>⚠️ Invalid Format</b>\n\n"
                "Usage: <code>/risk &lt;capital&gt; &lt;risk%&gt;</code>\n"
                "Example: <code>/risk 1000 1</code>"
            )
    else:
        # Show current settings
        capital, risk_pct = signal_builder.get_user_risk(chat_id)
        await update.message.reply_html(
            f"<b>📊 Current Risk Settings</b>\n\n"
            f"Capital: <code>${capital:.0f}</code>\n"
            f"Risk per trade: <code>{risk_pct:.1f}%</code>\n\n"
            f"<i>To change: /risk &lt;capital&gt; &lt;risk%&gt;</i>\n"
            f"<i>Example: /risk 5000 2</i>"
        )


def _set_user_risk(chat_id: int, capital: float, risk_pct: float) -> None:
    """Set and persist user risk settings."""
    signal_builder.set_user_risk(chat_id, capital, risk_pct)
    user_settings[chat_id] = {
        "capital": capital,
        "risk_pct": risk_pct,
    }
    save_settings()


async def cmd_pairs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /pairs command — list monitored pairs."""
    await update.message.reply_html(format_pairs_list(active_pairs))


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /news command — show economic events."""
    await update.message.reply_html("<b>📰 Fetching economic calendar...</b>")
    
    try:
        events = fetch_high_impact_events(hours_ahead=24)
        
        if not events:
            await update.message.reply_html(
                "<b>📰 Economic Calendar</b>\n\n"
                "No high-impact events in the next 24 hours."
            )
            return
        
        lines = ["<b>📰 High-Impact Events (Next 24h)</b>", ""]
        
        for ev in events[:10]:  # Show max 10
            time_str = ""
            if hasattr(ev.time, 'strftime'):
                time_str = ev.time.strftime("%H:%M GMT")
            else:
                time_str = str(ev.time)
            
            impact_emoji = "🔴" if ev.impact == "high" else "🟡" if ev.impact == "medium" else "🟢"
            lines.append(f"{impact_emoji} {time_str} — <b>{ev.currency}</b>: {ev.title}")
            
            if ev.forecast or ev.previous:
                details = []
                if ev.forecast:
                    details.append(f"Forecast: {ev.forecast}")
                if ev.previous:
                    details.append(f"Previous: {ev.previous}")
                lines.append(f"   <i>{' | '.join(details)}</i>")
        
        await update.message.reply_html("\n".join(lines))
        
    except Exception as e:
        logger.error("Error fetching news: %s", e)
        await update.message.reply_html(
            "<b>⚠️ Error</b>\n\nCould not fetch economic calendar.\nPlease try again later."
        )


async def cmd_setpairs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setpairs command — customize monitored pairs."""
    global active_pairs
    args = context.args
    
    if not args:
        await update.message.reply_html(
            f"<b>📋 Current Pairs:</b> {', '.join(active_pairs)}\n\n"
            f"<i>To change: /setpairs EURUSD,GBPUSD,XAUUSD</i>"
        )
        return
    
    # Parse pairs from comma-separated list
    pairs_str = " ".join(args)
    new_pairs = [p.strip().upper() for p in pairs_str.replace(" ", "").split(",") if p.strip()]
    
    if not new_pairs:
        await update.message.reply_html(
            "<b>⚠️ Invalid Format</b>\n\n"
            "Usage: <code>/setpairs EURUSD,GBPUSD,XAUUSD</code>\n"
            "Comma-separated, no spaces."
        )
        return
    
    # Validate pairs (basic check)
    valid_pairs = []
    for p in new_pairs:
        if len(p) >= 6:  # Minimum forex pair length
            valid_pairs.append(p)
    
    if not valid_pairs:
        await update.message.reply_html(
            "<b>⚠️ No valid pairs found</b>\n\n"
            "Examples: EURUSD, GBPUSD, XAUUSD, USDJPY"
        )
        return
    
    active_pairs = valid_pairs
    
    # Save to settings
    chat_id = _get_chat_id(update)
    if chat_id not in user_settings:
        user_settings[chat_id] = {}
    user_settings[chat_id]["active_pairs"] = active_pairs
    save_settings()
    
    await update.message.reply_html(
        f"<b>✅ Pairs Updated</b>\n\n"
        f"Now monitoring: <code>{', '.join(active_pairs)}</code>\n"
        f"Total: {len(active_pairs)} pairs"
    )


# ── Error Handler ────────────────────────────────────────────────────────────

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle bot errors gracefully."""
    logger.error("Update %s caused error: %s", update, context.error)
    
    if update and update.effective_message:
        await update.effective_message.reply_html(
            "<b>⚠️ Something went wrong</b>\n\n"
            "Please try again. If the issue persists, check bot logs."
        )


# ── Application Setup ────────────────────────────────────────────────────────

def create_application() -> Optional[Application]:
    """Create and configure the Telegram bot application."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("No TELEGRAM_BOT_TOKEN configured")
        return None
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("signal", cmd_signal))
    application.add_handler(CommandHandler("risk", cmd_risk))
    application.add_handler(CommandHandler("pairs", cmd_pairs))
    application.add_handler(CommandHandler("news", cmd_news))
    application.add_handler(CommandHandler("setpairs", cmd_setpairs))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    return application


async def send_signal_to_chat(bot: Bot, chat_id: int, signal: dict) -> None:
    """Send a formatted signal to a specific chat."""
    try:
        formatted = format_signal_html(signal)
        
        if len(formatted) > 4000:
            formatted = formatted[:4000] + "\n\n<i>(message truncated)</i>"
        
        await bot.send_message(
            chat_id=chat_id,
            text=formatted,
            parse_mode="HTML",
        )
        logger.info("Signal sent to chat %d", chat_id)
        
    except Exception as e:
        logger.error("Error sending signal to %d: %s", chat_id, e)