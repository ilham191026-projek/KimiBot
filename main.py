"""
SMC/ICT/CRT/MSNR Bot v3.0
Main Entry Point — Starts the Telegram Bot Application
"""

import asyncio
import logging
import sys
import os
from dotenv import load_dotenv

# Load environment
load_dotenv()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

from utils.logger import get_logger

logger = get_logger(__name__)

# Import bot creation from bot.py
from bot import create_application

async def main():
    """
    Main async entry point.
    Starts the Telegram bot application with handlers.
    """
    logger.info("="*70)
    logger.info("SMC/ICT/CRT/MSNR Bot v3.0 Starting...")
    logger.info("="*70)
    
    # Create the application
    application = create_application()
    if not application:
        logger.error("Failed to create bot application. Check TELEGRAM_BOT_TOKEN.")
        sys.exit(1)
    
    # Start the application
    async with application:
        # Start the bot
        await application.start()
        
        # Start polling for updates
        await application.updater.start_polling(allowed_updates=["message", "callback_query"])
        
        logger.info("Bot is running. Press Ctrl+C to stop.")
        
        try:
            # Keep the bot running
            await asyncio.Event().wait()
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down...")
        finally:
            # Graceful shutdown
            await application.updater.stop()
            await application.stop()
            logger.info("Bot stopped.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
