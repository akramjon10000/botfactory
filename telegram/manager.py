"""
Bot Manager — manages multiple bot instances (start, stop, restart).
"""
import logging
import threading

from telegram.sdk import TELEGRAM_AVAILABLE, TelegramHTTPBot
from telegram.handlers import TelegramBot

logger = logging.getLogger(__name__)


class BotManager:
    def __init__(self):
        self.running_bots = {}

    def start_bot(self, bot_id, bot_token):
        """Start a bot"""
        if not TELEGRAM_AVAILABLE:
            logger.warning(f"Cannot start bot {bot_id}: telegram library not available")
            return False

        if bot_id not in self.running_bots:
            try:
                bot = TelegramBot(bot_token, bot_id)
                # Make sure webhook is disabled before polling
                try:
                    bot.application.bot.delete_webhook(drop_pending_updates=False)
                except Exception:
                    pass

                # Start bot in a separate thread
                bot_thread = threading.Thread(target=bot.run, daemon=True)
                bot_thread.start()

                self.running_bots[bot_id] = {'bot': bot, 'thread': bot_thread}
                logger.info(f"Bot {bot_id} started successfully")
                return True
            except Exception as e:
                logger.error(f"Failed to start bot {bot_id}: {str(e)}")
                return False
        return True

    def stop_bot(self, bot_id):
        """Stop a bot"""
        if bot_id in self.running_bots:
            try:
                bot_info = self.running_bots[bot_id]
                if isinstance(bot_info, dict):
                    bot_info['bot'].application.bot.running = False
                del self.running_bots[bot_id]
                logger.info(f"Bot {bot_id} stopped")
                return True
            except Exception as e:
                logger.error(f"Failed to stop bot {bot_id}: {str(e)}")
                return False
        return True

    def restart_bot(self, bot_id, bot_token):
        """Restart a bot"""
        self.stop_bot(bot_id)
        return self.start_bot(bot_id, bot_token)


# Global bot manager instance
bot_manager = BotManager()
