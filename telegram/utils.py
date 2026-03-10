"""
Telegram utility functions — token validation, webhook, broadcast, admin messaging.
"""
import logging
import requests
from datetime import datetime, timedelta

from telegram.sdk import TELEGRAM_AVAILABLE, TelegramHTTPBot
from telegram.handlers import get_dependencies

logger = logging.getLogger(__name__)


def validate_telegram_token(token):
    """Telegram bot tokenini tekshirish"""
    try:
        if not token or len(token) < 20:
            return False

        response = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
        if response.status_code == 200:
            data = response.json()
            return data.get('ok', False)
        return False
    except Exception as e:
        logger.warning(f"Token validation error: {e}")
        return False


def send_message_to_bot_customer(bot_id: int, platform: str, platform_user_id: str, message_text: str) -> bool:
    """Send a broadcast message to a BotCustomer via the correct bot token.
    Currently supports Telegram customers. Returns True if sent successfully.
    """
    try:
        if platform.lower() != 'telegram':
            return False

        get_ai_response, process_knowledge_base, User, Bot, ChatHistory, db, app = get_dependencies()
        with app.app_context():
            bot = Bot.query.get(bot_id)
            if not bot or not bot.telegram_token:
                return False
            http_bot = TelegramHTTPBot(bot.telegram_token)
            resp = http_bot.send_message(platform_user_id, message_text)
            return bool(resp and resp.get('ok'))
    except Exception as e:
        try:
            logger.error(f"Error sending message to bot customer: {str(e)[:100]}")
        except Exception:
            pass
        return False


def start_bot_automatically(bot_id, bot_token):
    """Botni avtomatik ishga tushirish"""
    try:
        if not TELEGRAM_AVAILABLE:
            logger.warning(f"Cannot start bot {bot_id}: telegram library not available")
            return False

        if not validate_telegram_token(bot_token):
            logger.error(f"Invalid token for bot {bot_id}")
            return False

        # Late import to avoid circular imports
        from telegram.manager import bot_manager
        success = bot_manager.start_bot(bot_id, bot_token)
        if success:
            logger.info(f"Bot {bot_id} started automatically")
            return True
        else:
            logger.error(f"Failed to start bot {bot_id}")
            return False

    except Exception as e:
        logger.error(f"Auto start error for bot {bot_id}: {str(e)}")
        return False


def send_webhook_message(bot_token, chat_id, text):
    """Webhook orqali xabar yuborish"""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }

        response = requests.post(url, json=payload)
        return response.json().get('ok', False)

    except Exception as e:
        logger.error(f"Send webhook message error: {str(e)}")
        return False


def process_webhook_update(bot_id, bot_token, update_data):
    """Webhook orqali kelgan update ni qayta ishlash"""
    try:
        get_ai_response, process_knowledge_base, User, Bot, ChatHistory, db, app = get_dependencies()

        logger.info(f"DEBUG: Processing webhook update for bot {bot_id}")

        if 'message' in update_data:
            message = update_data['message']
            chat_id = message.get('chat', {}).get('id')
            user_id = message.get('from', {}).get('id')
            text = message.get('text', '')

            if not chat_id or not user_id:
                return False

            with app.app_context():
                telegram_user = User.query.filter_by(telegram_id=str(user_id)).first()
                if not telegram_user:
                    telegram_user = User()
                    telegram_user.username = f"tg_{user_id}"
                    telegram_user.email = f"telegram_{user_id}@botfactory.ai"
                    telegram_user.telegram_id = str(user_id)
                    telegram_user.language = 'uz'
                    telegram_user.subscription_type = 'free'
                    telegram_user.subscription_start_date = datetime.now()
                    telegram_user.subscription_end_date = datetime.now() + timedelta(days=14)
                    db.session.add(telegram_user)
                    db.session.commit()

                bot = Bot.query.get(bot_id)
                if not bot or not bot.telegram_token:
                    return False

                # Obunani tekshirish
                trial_active = False
                try:
                    from models import BotCustomer
                    cust = BotCustomer.query.filter_by(
                        bot_id=bot_id, platform='telegram', platform_user_id=str(user_id)
                    ).first()
                    trial_start = cust.first_interaction if cust and getattr(cust, 'first_interaction', None) else None
                    if not trial_start:
                        trial_start = telegram_user.subscription_start_date or telegram_user.created_at
                    if trial_start:
                        trial_active = (datetime.utcnow() - trial_start) <= timedelta(days=14)
                except Exception:
                    trial_active = False

                if not (telegram_user.subscription_active() or trial_active):
                    send_webhook_message(bot_token, chat_id, "Sizning obunangiz tugagan yoki 14 kunlik sinov muddati yakunlangan. Iltimos, yangilang!")
                    return True

                # Komandalarni qayta ishlash
                if text.startswith('/start'):
                    welcome_msg = f"Assalomu alaykum! 👋\n\nMen {bot.name} botiman. Menga savollaringizni bering, men sizga yordam beraman! 🤖"
                    send_webhook_message(bot_token, chat_id, welcome_msg)
                    return True
                elif text.startswith('/help'):
                    help_msg = "Yordam 📋\n\nMenga har qanday savol bering, men sizga AI yordamida javob beraman.\n\nTil sozlamalari uchun /language buyrug'ini ishlating."
                    send_webhook_message(bot_token, chat_id, help_msg)
                    return True
                elif text.startswith('/language'):
                    lang_msg = "Tilni tanlang / Выберите язык / Choose language:"
                    send_webhook_message(bot_token, chat_id, lang_msg)
                    return True

                # AI javob olish
                try:
                    knowledge_base = ""
                    if hasattr(bot, 'knowledge_base') and bot.knowledge_base:
                        for kb in bot.knowledge_base:
                            if kb.content:
                                knowledge_base += f"{kb.content}\n\n"

                    chat_history = ""
                    recent_chats = ChatHistory.query.filter_by(
                        bot_id=bot_id,
                        user_telegram_id=str(chat_id)
                    ).order_by(ChatHistory.created_at.desc()).limit(10).all()

                    for chat in reversed(recent_chats):
                        chat_history += f"Foydalanuvchi: {chat.message}\nBot: {chat.response}\n\n"

                    owner_contact_info = ""
                    if bot.owner:
                        owner_contact_info = f"Telefon raqam: {bot.owner.phone_number or 'Mavjud emas'}, Telegram: {bot.owner.telegram_id or 'Mavjud emas'}"
                    ai_response = get_ai_response(
                        message=text,
                        bot_name=bot.name,
                        user_language=telegram_user.language,
                        knowledge_base=knowledge_base,
                        chat_history=chat_history,
                        owner_contact_info=owner_contact_info
                    )

                    if not ai_response:
                        ai_response = "Kechirasiz, hozir javob bera olmayapman. Keyinroq qayta urinib ko'ring."

                    chat_record = ChatHistory()
                    chat_record.bot_id = bot_id
                    chat_record.user_telegram_id = str(chat_id)
                    chat_record.message = text[:1000]
                    chat_record.response = ai_response[:2000]
                    chat_record.created_at = datetime.now()
                    db.session.add(chat_record)
                    db.session.commit()

                    send_webhook_message(bot_token, chat_id, ai_response)
                    return True

                except Exception as e:
                    logger.error(f"AI processing error: {str(e)}")
                    error_msg = "Kechirasiz, xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
                    send_webhook_message(bot_token, chat_id, error_msg)
                    return True

        elif 'callback_query' in update_data:
            callback = update_data['callback_query']
            chat_id = callback.get('message', {}).get('chat', {}).get('id')
            callback_data = callback.get('data', '')

            if chat_id and callback_data:
                response = f"Siz {callback_data} ni tanladingiz."
                send_webhook_message(bot_token, chat_id, response)
                return True

        return True

    except Exception as e:
        logger.error(f"Webhook processing error for bot {bot_id}: {str(e)}")
        return False


def send_admin_message_to_user(telegram_id, message_text):
    """Send a message from admin to a specific user"""
    try:
        get_ai_response, process_knowledge_base, User, Bot, ChatHistory, db, app = get_dependencies()

        with app.app_context():
            bot = Bot.query.first()
            if not bot or not bot.telegram_token:
                return False

            http_bot = TelegramHTTPBot(bot.telegram_token)
            response = http_bot.send_message(telegram_id, f"📢 Admin xabari:\n\n{message_text}")

            if response and response.get('ok'):
                return True
            return False

    except Exception as e:
        logger.error(f"Error sending admin message: {e}")
        return False
