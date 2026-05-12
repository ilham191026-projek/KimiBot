"""
Entry point and scheduler for the SMC Bot.
Runs the 60-second scan loop during London and NY sessions.
"""

import asyncio
import json
import os
import signal
import sys
import time
from datetime import datetime
from typing import Dict, List, Optional

from telegram.ext import Application

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    SCAN_INTERVAL_SECONDS,
    DEFAULT_PAIRS,
    DEFAULT_CAPITAL,
    DEFAULT_RISK_PCT,
)
from utils.logger import get_logger
from utils.time_utils import is_active_session, get_current_session, format_gmt, now_gmt
from data.fetcher import DataFetcher, DataUnavailableError
from data.calendar import fetch_high_impact_events
from data.cache import clear as clear_cache
from analysis.confluence import run_full_analysis
from analysis.layer4_m15_crt import find_m15_swing, find_m30_swing
from risk.sl_tp_calculator import calculate_sl_tp
from risk.lot_sizer import calculate_lot_size
from ai.signal_narrator import generate_narrative
from signals.signal_builder import SignalBuilder
from signals.signal_formatter import format_signal_html
from filters.volatility_gate import check_volatility_gate
from filters.cooldown import CooldownManager
from filters.spread_check import check_spread
from bot import create_application, send_signal_to_chat, active_pairs, last_scan_time

logger = get_logger(__name__)

# ── Global State ─────────────────────────────────────────────────────────────
data_fetcher = DataFetcher()
signal_builder = SignalBuilder()
cooldown_manager = CooldownManager()
active_pairs = list(DEFAULT_PAIRS)
last_scan_time: Optional[str] = None
running = True

USER_SETTINGS_FILE = "user_settings.json"


def load_user_settings() -> None:
    """Load user settings from disk."""
    global active_pairs
    
    if os.path.exists(USER_SETTINGS_FILE):
        try:
            with open(USER_SETTINGS_FILE, "r") as f:
                data = json.load(f)
                
                # Load active pairs from default chat
                default_settings = data.get("0", {})
                saved_pairs = default_settings.get("active_pairs")
                if saved_pairs:
                    active_pairs = saved_pairs
                    
                logger.info("Loaded settings: %d entries", len(data))
        except Exception as e:
            logger.error("Error loading user settings: %s", e)


def save_user_settings() -> None:
    """Save user settings to disk."""
    try:
        existing = {}
        if os.path.exists(USER_SETTINGS_FILE):
            with open(USER_SETTINGS_FILE, "r") as f:
                existing = json.load(f)
        
        existing["0"] = {"active_pairs": active_pairs}
        
        with open(USER_SETTINGS_FILE, "w") as f:
            json.dump(existing, f, indent=2)
    except Exception as e:
        logger.error("Error saving settings: %s", e)


async def run_scan_for_pair(pair: str, chat_id: int = 0) -> Optional[Dict]:
    """
    Run full 6-layer analysis on a single pair.
    
    Args:
        pair: Instrument symbol
        chat_id: Telegram chat ID for user-specific settings
        
    Returns:
        Signal dict or None if no signal
    """
    logger.info("Scanning %s...", pair)
    
    try:
        # Step 1: Fetch H1 data for volatility gate
        h1_df = data_fetcher.get_ohlcv(pair, "H1", limit=50)
        
        # Step 2: Check volatility gate
        vol_check = check_volatility_gate(pair, h1_df)
        if not vol_check["passed"]:
            logger.info("Volatility gate failed for %s", pair)
            return None
        
        # Step 3: Fetch all timeframe data
        dataframes = {}
        
        for tf in ["H4", "H1", "M30", "M15", "M5", "M1"]:
            try:
                df = data_fetcher.get_ohlcv(pair, tf, limit=100)
                dataframes[tf] = df
            except DataUnavailableError:
                logger.warning("No %s data for %s", tf, pair)
                dataframes[tf] = None
        
        # Step 4: Check spread at M5/M1
        m5_df = dataframes.get("M5")
        if m5_df is not None:
            spread_check = check_spread(pair, m5_df)
            if not spread_check["passed"]:
                logger.info("Spread too high for %s", pair)
                return None
        
        # Step 5: Run 6-layer confluence analysis
        confluence = run_full_analysis(pair, dataframes)
        
        if not confluence.get("confluence_passed"):
            logger.info("Confluence failed for %s: %d/6",
                       pair, confluence.get("confluence_score", 0))
            return None
        
        # Step 6: Fetch news events
        news_events = fetch_high_impact_events(hours_ahead=4)
        
        # Step 7: Build signal with narrative
        signal = await signal_builder.build_with_narrative(
            pair=pair,
            confluence_results=confluence,
            dataframes=dataframes,
            news_events=news_events,
            chat_id=chat_id,
        )
        
        if signal:
            logger.info("Signal generated for %s!", pair)
        
        return signal
        
    except DataUnavailableError as e:
        logger.warning("Data unavailable for %s: %s", pair, e)
        return None
    except Exception as e:
        logger.error("Error scanning %s: %s", pair, e)
        return None


async def run_scheduled_scan(bot) -> None:
    """Run the scheduled scan loop."""
    global last_scan_time
    
    logger.info("Starting scheduled scan loop")
    logger.info("Session check: %s", get_current_session())
    
    while running:
        try:
            # Check if we're in an active session
            if not is_active_session():
                session = get_current_session()
                next_session_min = 0
                
                # Calculate time until next session
                from utils.time_utils import time_until_next_session
                wait_min = time_until_next_session()
                wait_sec = min(wait_min * 60, 300)  # Check every 5 min max
                
                logger.info(
                    "Off-hours (%s). Waiting %d minutes until next session...",
                    session, wait_sec // 60
                )
                await asyncio.sleep(wait_sec)
                continue
            
            # We're in an active session — scan all pairs
            logger.info("=" * 50)
            logger.info("Starting scan cycle — Session: %s", get_current_session())
            logger.info("=" * 50)
            
            signals_found = 0
            
            for pair in active_pairs:
                if not running:
                    break
                
                # Skip pairs on cooldown
                if cooldown_manager.is_on_cooldown(pair):
                    remaining = cooldown_manager.time_remaining(pair)
                    logger.info("%s on cooldown (%.0f min remaining)", pair, remaining / 60)
                    continue
                
                try:
                    signal = await run_scan_for_pair(pair)
                    
                    if signal:
                        signals_found += 1
                        last_scan_time = format_gmt(now_gmt())
                        
                        # Send signal to Telegram
                        if TELEGRAM_CHAT_ID:
                            try:
                                chat_id = int(TELEGRAM_CHAT_ID)
                                await send_signal_to_chat(bot, chat_id, signal)
                                cooldown_manager.trigger(pair)
                            except Exception as e:
                                logger.error("Error sending signal: %s", e)
                        
                        # Small delay between signals
                        await asyncio.sleep(2)
                        
                except Exception as e:
                    logger.error("Error in scan cycle for %s: %s", pair, e)
                    continue
            
            last_scan_time = format_gmt(now_gmt())
            
            logger.info(
                "Scan cycle complete. Signals found: %d. Next scan in %ds",
                signals_found, SCAN_INTERVAL_SECONDS
            )
            
            # Wait for next scan interval
            await asyncio.sleep(SCAN_INTERVAL_SECONDS)
            
        except Exception as e:
            logger.error("Error in scheduled scan loop: %s", e)
            await asyncio.sleep(SCAN_INTERVAL_SECONDS)


async def main() -> None:
    """Main entry point — starts bot and scheduler."""
    logger.info("=" * 60)
    logger.info("SMC/ICT/CRT/MSNR Bot v3.0 Starting...")
    logger.info("=" * 60)
    
    # Load settings
    load_user_settings()
    
    # Create Telegram bot application
    application = create_application()
    
    if application is None:
        logger.error("Failed to create bot application. Exiting.")
        return
    
    # Initialize bot
    await application.initialize()
    await application.start()
    
    bot = application.bot
    
    # Send startup message
    if TELEGRAM_CHAT_ID:
        try:
            await bot.send_message(
                chat_id=int(TELEGRAM_CHAT_ID),
                text=(
                    "🤖 <b>SMC/ICT/CRT/MSNR Bot v3.0</b> is now running!\n\n"
                    f"Session: {get_current_session()}\n"
                    f"Pairs: {len(active_pairs)}\n"
                    f"Scan interval: {SCAN_INTERVAL_SECONDS}s\n\n"
                    "Use /status for details."
                ),
                parse_mode="HTML",
            )
        except Exception as e:
            logger.error("Failed to send startup message: %s", e)
    
    # Start polling for commands
    await application.updater.start_polling(drop_pending_updates=True)
    
    logger.info("Bot polling started")
    
    # Run scheduled scan loop in background
    scan_task = asyncio.create_task(run_scheduled_scan(bot))
    
    logger.info("Scheduler started. Bot is running.")
    
    try:
        # Keep running until interrupted
        while running:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        logger.info("Main task cancelled")
    finally:
        # Cleanup
        logger.info("Shutting down...")
        scan_task.cancel()
        try:
            await scan_task
        except asyncio.CancelledError:
            pass
        
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        
        logger.info("Bot stopped. Goodbye!")


def signal_handler(sig, frame) -> None:
    """Handle shutdown signals gracefully."""
    global running
    logger.info("Shutdown signal received (%s)", sig)
    running = False


if __name__ == "__main__":
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run main
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
        sys.exit(0)
    except Exception as e:
        logger.error("Fatal error: %s", e)
        sys.exit(1)