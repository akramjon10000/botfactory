"""
Telegram package — re-exports all public APIs for backward compatibility.

Usage:
    from telegram_bot import bot_manager, start_telegram_bot, ...
    (unchanged — telegram_bot.py re-exports from this package)
"""

# SDK layer
from telegram.sdk import (
    TELEGRAM_AVAILABLE,
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ContextTypes,
    TelegramHTTPBot,
    TelegramApplication,
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    VoiceHandler,
    FilterType,
    filters,
    _mark_processed,
)

# Bot handlers
from telegram.handlers import (
    TelegramBot,
    start_telegram_bot,
    get_dependencies,
)

# Bot manager
from telegram.manager import (
    BotManager,
    bot_manager,
)

# Utility functions
from telegram.utils import (
    validate_telegram_token,
    send_message_to_bot_customer,
    start_bot_automatically,
    process_webhook_update,
    send_webhook_message,
    send_admin_message_to_user,
)
