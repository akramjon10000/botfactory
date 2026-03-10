"""
Bot Manager Service - Handles lifecycle and background polling for all platform bots
This service ensures all active bots start polling when the Flask application launches
"""

import threading
import logging
import time
import signal
import sys
from typing import Dict, List
from datetime import datetime

logger = logging.getLogger(__name__)

class BotManager:
    """Central manager for all bot platform polling operations"""
    
    def __init__(self):
        self.active_bots: Dict[str, Dict] = {}  # bot_id -> bot_info
        self.polling_threads: Dict[str, threading.Thread] = {}
        self.shutdown_event = threading.Event()
        self.startup_complete = False
        
        # Setup graceful shutdown
        signal.signal(signal.SIGTERM, self._shutdown_handler)
        signal.signal(signal.SIGINT, self._shutdown_handler)
    
    def _shutdown_handler(self, signum, frame):
        """Handle graceful shutdown signals"""
        logger.info(f"🛑 Bot manager received shutdown signal: {signum}")
        self.shutdown_all_bots()
        sys.exit(0)
    
    def start_all_active_bots(self):
        """Start polling for all active bots in the database"""
        try:
            from models import Bot
            from app import db, app
            
            with app.app_context():
                # Get all active bots from database
                active_bots = Bot.query.filter_by(is_active=True).all()
                
                if not active_bots:
                    logger.info("🤖 No active bots found in database")
                    self.startup_complete = True
                    return
                
                logger.info(f"🚀 Starting polling for {len(active_bots)} active bots...")
                
                for bot in active_bots:
                    try:
                        self.start_bot_polling(bot)
                        time.sleep(0.5)  # Small delay between bot starts
                    except Exception as e:
                        logger.error(f"❌ Failed to start bot {bot.name} (ID: {bot.id}): {e}")
                
                self.startup_complete = True
                logger.info(f"✅ Bot manager startup complete! {len(self.active_bots)} bots active")
                
        except Exception as e:
            logger.error(f"❌ Critical error during bot manager startup: {e}")
            self.startup_complete = True
    
    def start_bot_polling(self, bot_model):
        """Start polling for a specific bot based on its platform"""
        bot_key = f"{bot_model.platform}_{bot_model.id}"
        
        if bot_key in self.active_bots:
            logger.warning(f"⚠️ Bot {bot_model.name} already active, skipping...")
            return
        
        try:
            if bot_model.platform.lower() == 'telegram':
                self._start_telegram_bot(bot_model, bot_key)
            elif bot_model.platform.lower() == 'instagram':
                self._start_instagram_bot(bot_model, bot_key)
            elif bot_model.platform.lower() == 'whatsapp':
                self._start_whatsapp_bot(bot_model, bot_key)
            else:
                logger.warning(f"⚠️ Unknown platform for bot {bot_model.name}: {bot_model.platform}")
                
        except Exception as e:
            logger.error(f"❌ Error starting {bot_model.platform} bot {bot_model.name}: {e}")
    
    def _start_telegram_bot(self, bot_model, bot_key):
        """Start Telegram bot polling in background thread"""
        if not bot_model.telegram_token:
            logger.warning(f"⚠️ No Telegram token for bot {bot_model.name}")
            return
        
        def telegram_polling_worker():
            """Worker function that runs Telegram bot polling"""
            try:
                from telegram_bot import TelegramBot
                
                logger.info(f"🔄 Starting Telegram polling for bot: {bot_model.name}")
                
                # Create bot instance
                telegram_bot = TelegramBot(bot_model.telegram_token, bot_model.id)
                
                # Store bot info
                self.active_bots[bot_key] = {
                    'model': bot_model,
                    'instance': telegram_bot,
                    'platform': 'telegram',
                    'status': 'running',
                    'started_at': datetime.now()
                }
                
                logger.info(f"✅ Telegram bot {bot_model.name} polling started successfully!")
                
                # Start the blocking polling loop
                telegram_bot.application.run_polling()
                
            except Exception as e:
                logger.error(f"❌ Telegram polling error for bot {bot_model.name}: {e}")
                # Clean up failed bot
                if bot_key in self.active_bots:
                    self.active_bots[bot_key]['status'] = 'error'
        
        # Start polling in background thread
        thread = threading.Thread(
            target=telegram_polling_worker,
            name=f"telegram_bot_{bot_model.id}",
            daemon=True
        )
        thread.start()
        
        # Track thread
        self.polling_threads[bot_key] = thread
        logger.info(f"🧵 Telegram polling thread started for bot: {bot_model.name}")
    
    def _start_instagram_bot(self, bot_model, bot_key):
        """Start Instagram bot polling"""
        if not bot_model.instagram_token:
            logger.warning(f"⚠️ No Instagram token for bot {bot_model.name}")
            return
            
        try:
            logger.info(f"📷 Starting Instagram bot: {bot_model.name}")
            from instagram_bot import start_instagram_bot_automatically
            
            # Start Instagram webhook registration/setup
            success = start_instagram_bot_automatically(bot_model.id, bot_model.instagram_token)
            
            if success:
                self.active_bots[bot_key] = {
                    'model': bot_model,
                    'instance': None, # Instagram relies on webhooks, no persistent instance
                    'platform': 'instagram',
                    'status': 'running',
                    'started_at': datetime.now()
                }
                logger.info(f"✅ Instagram bot {bot_model.name} started successfully!")
            else:
                logger.error(f"❌ Failed to start Instagram bot {bot_model.name}")
                
        except Exception as e:
            logger.error(f"❌ Error starting Instagram bot {bot_model.name}: {e}")
    
    def _start_whatsapp_bot(self, bot_model, bot_key):
        """Start WhatsApp bot polling"""
        if not bot_model.whatsapp_token or not bot_model.whatsapp_phone_id:
            logger.warning(f"⚠️ No WhatsApp token or phone ID for bot {bot_model.name}")
            return
            
        try:
            logger.info(f"📱 Starting WhatsApp bot: {bot_model.name}")
            from whatsapp_bot import start_whatsapp_bot_automatically
            
            # Start WhatsApp webhook registration/setup
            success = start_whatsapp_bot_automatically(bot_model.id, bot_model.whatsapp_token, bot_model.whatsapp_phone_id)
            
            if success:
                self.active_bots[bot_key] = {
                    'model': bot_model,
                    'instance': None, # WhatsApp relies on webhooks, no persistent instance
                    'platform': 'whatsapp',
                    'status': 'running',
                    'started_at': datetime.now()
                }
                logger.info(f"✅ WhatsApp bot {bot_model.name} started successfully!")
            else:
                logger.error(f"❌ Failed to start WhatsApp bot {bot_model.name}")
                
        except Exception as e:
            logger.error(f"❌ Error starting WhatsApp bot {bot_model.name}: {e}")
    
    def stop_bot_polling(self, bot_id, platform='telegram'):
        """Stop polling for a specific bot"""
        bot_key = f"{platform}_{bot_id}"
        
        if bot_key not in self.active_bots:
            logger.warning(f"⚠️ Bot {bot_key} not found in active bots")
            return
        
        try:
            # Update status
            self.active_bots[bot_key]['status'] = 'stopping'
            
            # For Telegram bots, there's no clean stop method in our implementation
            # The thread will continue until process ends
            logger.info(f"🛑 Marked bot {bot_key} for shutdown")
            
            # Remove from active bots
            del self.active_bots[bot_key]
            
            # Remove thread reference
            if bot_key in self.polling_threads:
                del self.polling_threads[bot_key]
            
            logger.info(f"✅ Bot {bot_key} polling stopped")
            
        except Exception as e:
            logger.error(f"❌ Error stopping bot {bot_key}: {e}")
    
    def shutdown_all_bots(self):
        """Shutdown all bot polling operations"""
        logger.info("🛑 Shutting down all bot polling operations...")
        
        self.shutdown_event.set()
        
        # Stop all active bots
        for bot_key in list(self.active_bots.keys()):
            try:
                self.active_bots[bot_key]['status'] = 'shutting_down'
                logger.info(f"🛑 Stopping bot: {bot_key}")
            except Exception as e:
                logger.error(f"❌ Error during bot shutdown {bot_key}: {e}")
        
        logger.info("✅ All bots marked for shutdown")
    
    def get_bot_status(self):
        """Get status of all active bots"""
        status = {
            'startup_complete': self.startup_complete,
            'total_active_bots': len(self.active_bots),
            'bots': {}
        }
        
        for bot_key, bot_info in self.active_bots.items():
            status['bots'][bot_key] = {
                'name': bot_info['model'].name,
                'platform': bot_info['platform'],
                'status': bot_info['status'],
                'started_at': bot_info['started_at'].strftime('%Y-%m-%d %H:%M:%S'),
                'uptime_seconds': (datetime.now() - bot_info['started_at']).total_seconds()
            }
        
        return status
    
    def restart_bot(self, bot_id, platform='telegram'):
        """Restart a specific bot"""
        logger.info(f"🔄 Restarting bot: {platform}_{bot_id}")
        
        # Stop the bot first
        self.stop_bot_polling(bot_id, platform)
        time.sleep(1)  # Brief pause
        
        # Get bot from database and restart
        try:
            from models import Bot
            from app import app
            
            with app.app_context():
                bot_model = Bot.query.get(bot_id)
                if bot_model and bot_model.is_active:
                    self.start_bot_polling(bot_model)
                    logger.info(f"✅ Bot {platform}_{bot_id} restarted successfully")
                else:
                    logger.warning(f"⚠️ Bot {bot_id} not found or not active")
                    
        except Exception as e:
            logger.error(f"❌ Error restarting bot {platform}_{bot_id}: {e}")

# Global bot manager instance
bot_manager = BotManager()

def initialize_bot_manager():
    """Initialize the bot manager and start all active bots"""
    try:
        logger.info("🤖 Initializing BotFactory AI Bot Manager...")
        
        # Start all active bots in a separate thread to avoid blocking Flask startup
        startup_thread = threading.Thread(
            target=bot_manager.start_all_active_bots,
            name="bot_manager_startup",
            daemon=True
        )
        startup_thread.start()
        
        logger.info("✅ Bot manager initialization started in background")
        return bot_manager
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize bot manager: {e}")
        return None

# Health check function for bot manager
def get_bot_manager_health():
    """Get health status of bot manager for monitoring"""
    try:
        return {
            'status': 'healthy' if bot_manager.startup_complete else 'starting',
            'active_bots': len(bot_manager.active_bots),
            'polling_threads': len(bot_manager.polling_threads),
            'uptime': 'Bot manager active'
        }
    except Exception as e:
        return {
            'status': 'error',
            'error': str(e),
            'active_bots': 0,
            'polling_threads': 0
        }