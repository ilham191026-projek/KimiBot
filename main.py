"""
SMC/ICT/CRT/MSNR Bot v3.0
Main Entry Point — Telegram Bot Handler
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
from telegram import Update, Bot
from dotenv import load_dotenv

# Load env vars
load_dotenv()

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    DEFAULT_PAIRS,
    DEFAULT_CAPITAL,
    DEFAULT_RISK_PCT,
    SCAN_INTERVAL_SECONDS,
)
from utils.logger import get_logger
from utils.time_utils import is_active_session, get_current_session, format_gmt, now_gmt
from data.fetcher import DataFetcher, DataUnavailableError
from data.calendar import fetch_high_impact_events
from data.cache import clear as clear_cache
from analysis.confluence import run_full_analysis
from risk.sl_tp_calculator import calculate_sl_tp
from risk.lot_sizer import calculate_lot_size
from ai.signal_narrator import generate_narrative
from signals.signal_builder import SignalBuilder
from signals.signal_formatter import format_signal_html
from filters.volatility_gate import check_volatility_gate
from filters.cooldown import CooldownManager
from filters.spread_check import check_spread
from bot import (
    cmd_start,
    cmd_status,
    cmd_signal,
    cmd_risk,
    cmd_pairs,
    cmd_news,
    cmd_setpairs,
    error_handler,
    load_settings,
    save_settings,
    user_settings,
    active_pairs,
    last_scan_time,
)

logger = get_logger(__name__)

# ── Global State ──────────────────────────────────────────────────────────────
data_fetcher = DataFetcher()
signal_builder = SignalBuilder()
cooldown_manager = CooldownManager()
scan_counter = 0
running = True


async def run_scan_for_pair(
    pair: str, user_capital: float, user_risk_pct: float, bot: Bot
) -> Optional[dict]:
    """
    Scan a single pair across all timeframes and generate signal if valid.
    """
    try:
        logger.info(f"Scanning {pair}...")
        
        # Fetch data
        h4_df = await data_fetcher.fetch_async(pair, "H4")
        h1_df = await data_fetcher.fetch_async(pair, "H1")
        m30_df = await data_fetcher.fetch_async(pair, "M30")
        m15_df = await data_fetcher.fetch_async(pair, "M15")
        m5_df = await data_fetcher.fetch_async(pair, "M5")
        m1_df = await data_fetcher.fetch_async(pair, "M1")
        
        if any(df is None or len(df) < 5 for df in [h4_df, h1_df, m30_df, m15_df, m5_df, m1_df]):
            logger.warning(f"{pair}: Insufficient data")
            return None
        
        # Run confluence analysis
        confluence = run_full_analysis(
            pair, h4_df, h1_df, m30_df, m15_df, m5_df, m1_df
        )
        
        if not confluence.get("signal_valid"):
            logger.info(f"{pair}: No valid confluence")
            return None
        
        # Check volatility
        if not check_volatility_gate(pair, h1_df):
            logger.info(f"{pair}: Volatility gate failed")
            return None
        
        # Check spread
        if not check_spread(pair):
            logger.info(f"{pair}: Spread too wide")
            return None
        
        # Check cooldown
        if cooldown_manager.is_in_cooldown(pair):
            logger.info(f"{pair}: In cooldown")
            return None
        
        # Build signal
        signal_data = signal_builder.build(
            pair=pair,
            confluence=confluence,
            m15_df=m15_df,
            m5_df=m5_df,
            m1_df=m1_df,
            capital=user_capital,
            risk_pct=user_risk_pct,
        )
        
        if not signal_data or not signal_data.get("valid"):
            logger.warning(f"{pair}: Signal validation failed")
            return None
        
        # Generate narrative
        narrative = await generate_narrative(signal_data, confluence)
        signal_data["narrative"] = narrative
        
        # Mark cooldown
        cooldown_manager.mark_signal(pair)
        
        logger.info(f"✅ {pair} {signal_data['direction']} signal generated")
        
        return signal_data
        
    except Exception as e:
        logger.error(f"Error scanning {pair}: {e}", exc_info=True)
        return None


async def scan_job(pairs: List[str], user_capital: float, user_risk_pct: float, bot: Bot):
    """
    Main scan job — scan all pairs concurrently.
    """
    global scan_counter
    scan_counter += 1
    
    now = now_gmt()
    session = get_current_session()
    is_active = is_active_session()
    
    logger.info(f"\n{'='*70}")
    logger.info(f"[SCAN #{scan_counter}] {now} GMT | Session: {session} | Active: {is_active}")
    logger.info(f"Pairs: {', '.join(pairs)}")
    logger.info(f"Capital: ${user_capital:.2f}, Risk: {user_risk_pct}%")
    logger.info(f"{'='*70}\n")
    
    # Run scans concurrently
    tasks = [
        run_scan_for_pair(pair, user_capital, user_risk_pct, bot)
        for pair in pairs
    ]
    signals = await asyncio.gather(*tasks)
    
    # Send signals to Telegram
    for signal in signals:
        if signal:
            try:
                html = format_signal_html(signal)
                if len(html) > 4000:
                    html = html[:4000] + "\n\n<i>(truncated)</i>"
                
                await bot.send_message(
                    chat_id=TELEGRAM_CHAT_ID,
                    text=html,
                    parse_mode="HTML",
                )
                logger.info(f"Signal sent to chat {TELEGRAM_CHAT_ID}")
            except Exception as e:
                logger.error(f"Error sending signal: {e}")
    
    # Clear cache
    clear_cache()


async def scheduled_scan(bot: Bot, pairs: List[str], capital: float, risk_pct: float):
    """
    Wrapper for scheduled scans.
    """
    try:
        await scan_job(pairs, capital, risk_pct, bot)
    except Exception as e:
        logger.error(f"Scan job error: {e}", exc_info=True)


async def scheduler_loop(app: Application):
    """
    Simple async scheduler loop.
    """
    global running
    
    # Load user settings
    load_settings()
    
    # Get initial settings
    capital = float(os.getenv("DEFAULT_CAPITAL", DEFAULT_CAPITAL))
    risk_pct = float(os.getenv("DEFAULT_RISK_PCT", DEFAULT_RISK_PCT))
    pairs = list(DEFAULT_PAIRS)
    scan_interval = SCAN_INTERVAL_SECONDS
    
    bot = app.bot
    last_scan = datetime.now()
    
    logger.info("Scheduler started")
    
    while running:
        try:
            now = datetime.now()
            
            # Check if it's time to scan
            if (now - last_scan).total_seconds() >= scan_interval:
                # Get latest settings
                if TELEGRAM_CHAT_ID in user_settings:
                    settings = user_settings[TELEGRAM_CHAT_ID]
                    capital = float(settings.get("capital", capital))
                    risk_pct = float(settings.get("risk_pct", risk_pct))
                    pairs = settings.get("pairs", pairs)
                
                # Run scan
                await scheduled_scan(bot, pairs, capital, risk_pct)
                last_scan = now
            
            # Sleep briefly to avoid busy-waiting
            await asyncio.sleep(1)
            
        except Exception as e:
            logger.error(f"Scheduler error: {e}", exc_info=True)
            await asyncio.sleep(5)


async def main_async(app: Application):
    """
    Main async entry point.
    """
    # Start the bot
    async with app:
        # Run scheduler in background
        scheduler_task = asyncio.create_task(scheduler_loop(app))
        
        # Start polling
        await app.start()
        await app.updater.start_polling()
        
        try:
            # Keep running
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Shutdown requested")
        finally:
            await app.stop()
            scheduler_task.cancel()


def create_app() -> Optional[Application]:
    """
    Create and configure the bot application.
    """
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not configured")
        return None
    
    from telegram.ext import (
        Application,
        CommandHandler,
        MessageHandler,
        filters,
    )
    
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Add handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("signal", cmd_signal))
    app.add_handler(CommandHandler("risk", cmd_risk))
    app.add_handler(CommandHandler("pairs", cmd_pairs))
    app.add_handler(CommandHandler("news", cmd_news))
    app.add_handler(CommandHandler("setpairs", cmd_setpairs))
    app.add_error_handler(error_handler)
    
    return app


def main():
    """
    Entry point.
    """
    logger.info("="*70)
    logger.info("SMC/ICT/CRT/MSNR Bot v3.0 Starting")
    logger.info("="*70)
    
    # Create app
    app = create_app()
    if not app:
        logger.error("Failed to create application")
        sys.exit(1)
    
    # Run
    try:
        asyncio.run(main_async(app))
    except KeyboardInterrupt:
        logger.info("Shutdown")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
