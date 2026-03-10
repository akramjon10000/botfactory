import os
import logging
import asyncio
import requests
import tempfile
from typing import Optional
from datetime import datetime, timedelta
from audio_processor import transcribe_audio_from_url

# Set telegram as available and use real bot implementation
TELEGRAM_AVAILABLE = True

# Local lightweight classes to replace private telegram imports
class Update:
    """Lightweight Update class to avoid private imports"""
    def __init__(self, data=None):
        self.data = data
        self.message = None
        self.callback_query = None
        self.effective_user = None
        self.effective_chat = None

class InlineKeyboardButton:
    """Lightweight InlineKeyboardButton replacement"""
    def __init__(self, text, callback_data=None, url=None, web_app=None):
        self.text = text
        self.callback_data = callback_data
        self.url = url
        self.web_app = web_app  # WebApp support for Mini Apps
    
    def to_dict(self):
        result = {"text": self.text}
        if self.callback_data:
            result["callback_data"] = self.callback_data
        if self.url:
            result["url"] = self.url
        if self.web_app:
            result["web_app"] = self.web_app
        return result

class InlineKeyboardMarkup:
    """Lightweight InlineKeyboardMarkup replacement"""
    def __init__(self, keyboard):
        self.keyboard = keyboard
    
    def to_dict(self):
        return {
            "inline_keyboard": [
                [button.to_dict() for button in row] 
                for row in self.keyboard
            ]
        }

# Real Telegram Bot implementation using HTTP API
class ContextTypes:
    DEFAULT_TYPE = "DefaultContext"

class TelegramHTTPBot:
    def __init__(self, token):
        self.token = token
        self.handlers = {}
        self.running = False
        self.base_url = f"https://api.telegram.org/bot{token}"
        
    def add_handler(self, handler):
        if isinstance(handler, tuple):
            cmd_type, func = handler
            if cmd_type not in self.handlers:
                self.handlers[cmd_type] = []
            self.handlers[cmd_type].append(func)
        
    def send_message(self, chat_id, text, reply_markup=None):
        url = f"{self.base_url}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': text
        }
        if reply_markup:
            import json
            # Convert reply_markup to JSON if it's an object
            if hasattr(reply_markup, 'to_dict'):
                data['reply_markup'] = json.dumps(reply_markup.to_dict())
            elif isinstance(reply_markup, dict):
                data['reply_markup'] = json.dumps(reply_markup)
            else:
                data['reply_markup'] = reply_markup
        
        try:
            response = requests.post(url, json=data)
            return response.json()
        except Exception as e:
            # Ultra-safe logging
            try:
                logger.error("Error sending message occurred")
            except Exception:
                pass
            return None
    
    def delete_webhook(self, drop_pending_updates: bool = False):
        """Delete webhook to enable long polling. Safe to call multiple times."""
        try:
            url = f"{self.base_url}/deleteWebhook"
            payload = {"drop_pending_updates": drop_pending_updates}
            resp = requests.post(url, json=payload, timeout=10)
            data = resp.json()
            return data.get('ok', False)
        except Exception:
            return False
    
    async def send_chat_action(self, chat_id, action):
        """Send typing or other chat actions to user"""
        url = f"{self.base_url}/sendChatAction"
        data = {
            'chat_id': chat_id,
            'action': action
        }
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, lambda: requests.post(url, json=data))
            return response.json()
        except Exception as e:
            try:
                logger.error("Error sending chat action occurred")
            except Exception:
                pass
            return None
    
    def get_updates(self, offset=None):
        url = f"{self.base_url}/getUpdates"
        params = {'timeout': 10}
        if offset:
            params['offset'] = offset
            
        try:
            response = requests.get(url, params=params)
            return response.json()
        except Exception as e:
            # Ultra-safe logging
            try:
                logger.error("Error getting updates occurred")
            except Exception:
                pass
            return {'ok': False, 'result': []}
            
    async def process_update(self, update_data):
        # Create simplified Update object
        class SimpleUpdate:
            def __init__(self, data):
                self.data = data
                self.message = None
                self.callback_query = None
                self.effective_user = None
                self.effective_chat = None
                
                if 'message' in data:
                    self.message = SimpleMessage(data['message'])
                    self.effective_user = SimpleUser(data['message']['from'])
                    self.effective_chat = SimpleChat(data['message']['chat'])
                elif 'callback_query' in data:
                    self.callback_query = SimpleCallbackQuery(data['callback_query'])
                    self.effective_user = SimpleUser(data['callback_query']['from'])
                    self.effective_chat = SimpleChat(data['callback_query']['message']['chat'])
        
        class SimpleMessage:
            def __init__(self, data):
                self.data = data
                self.text = data.get('text', '')
                self.voice = data.get('voice')
                self.audio = data.get('audio') 
                self.document = data.get('document')
                self.chat = SimpleChat(data['chat'])
                
            async def reply_text(self, text, reply_markup=None):
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(
                    None, lambda: bot_instance.send_message(self.chat.id, text, reply_markup)
                )
                return result
            
            async def reply_photo(self, photo, caption=None):
                """Reply with photo via sendPhoto API"""
                url = f"{bot_instance.base_url}/sendPhoto"
                try:
                    data = {
                        'chat_id': self.chat.id,
                        'photo': photo
                    }
                    if caption:
                        data['caption'] = caption
                    
                    response = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: requests.post(url, json=data)
                    )
                    return response.json()
                except Exception as e:
                    logger.error(f"Failed to send photo: {e}")
                    # Graceful fallback - send text message instead
                    fallback_text = f"🖼️ Rasm: {caption or 'Rasm yuborilmadi'}"
                    return await self.reply_text(fallback_text)
        
        class SimpleUser:
            def __init__(self, data):
                self.data = data
                self.id = data['id']
                self.username = data.get('username', '')
                self.first_name = data.get('first_name', '')
                self.last_name = data.get('last_name', '')
                
        class SimpleChat:
            def __init__(self, data):
                self.data = data
                self.id = data['id']
                
        class SimpleCallbackQuery:
            def __init__(self, data):
                self.data = data.get('data', '')  # Extract callback_data properly
                self.id = data.get('id', '')
                self.from_user = SimpleUser(data['from'])
                self.message = data.get('message', {})
                
            async def answer(self):
                """Answer callback query via answerCallbackQuery API"""
                url = f"{bot_instance.base_url}/answerCallbackQuery"
                try:
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None, lambda: requests.post(url, json={'callback_query_id': self.id})
                    )
                    return response.json()
                except Exception as e:
                    logger.error(f"Failed to answer callback query: {e}")
                    return {'ok': False, 'error': str(e)}
                
            async def edit_message_text(self, text):
                """Edit message text via editMessageText API"""
                url = f"{bot_instance.base_url}/editMessageText"
                try:
                    data = {
                        'chat_id': self.message.get('chat', {}).get('id'),
                        'message_id': self.message.get('message_id'),
                        'text': text
                    }
                    loop = asyncio.get_event_loop()
                    response = await loop.run_in_executor(
                        None, lambda: requests.post(url, json=data)
                    )
                    return response.json()
                except Exception as e:
                    logger.error(f"Failed to edit message text: {e}")
                    return {'ok': False, 'error': str(e)}
        
        # Process update
        update = SimpleUpdate(update_data)
        
        # Create context object
        class SimpleContext:
            def __init__(self, text=None, bot=None):
                self.args = []
                self.bot = bot  # Add bot reference
                if text and text.startswith('/'):
                    # Split command and arguments
                    parts = text.split()[1:]  # Remove command itself
                    self.args = parts
        
        # Handle voice messages first
        if update.message and (update.message.voice or update.message.audio):
            context = SimpleContext(None, self)
            if 'voice' in self.handlers:
                for handler in self.handlers['voice']:
                    await handler(update, context)
        # Handle text commands and messages
        elif update.message and update.message.text:
            text = update.message.text
            context = SimpleContext(text, self)
            
            if text.startswith('/'):
                cmd = text.split()[0][1:]  # Remove '/'
                if 'start' in self.handlers and cmd == 'start':
                    for handler in self.handlers['start']:
                        await handler(update, context)
                elif 'help' in self.handlers and cmd == 'help':
                    for handler in self.handlers['help']:
                        await handler(update, context)
                elif 'language' in self.handlers and cmd == 'language':
                    for handler in self.handlers['language']:
                        await handler(update, context)
            else:
                # Regular message
                if 'message' in self.handlers:
                    for handler in self.handlers['message']:
                        await handler(update, context)
        
        # Handle callback queries
        if update.callback_query and 'callback' in self.handlers:
            context = SimpleContext()  # Empty context for callbacks
            for handler in self.handlers['callback']:
                await handler(update, context)

class TelegramApplication:
    def __init__(self, token):
        self.bot = TelegramHTTPBot(token)
        
    def add_handler(self, handler):
        self.bot.add_handler(handler)
        
    def run_polling(self):
        # Simple polling implementation
        offset = None
        global bot_instance
        bot_instance = self.bot
        # Ensure webhook is removed so getUpdates will work
        try:
            self.bot.delete_webhook(drop_pending_updates=False)
        except Exception:
            pass
        
        logger.info("Starting bot polling...")
        while True:
            try:
                updates = self.bot.get_updates(offset)
                if updates.get('ok') and updates.get('result'):
                    for update in updates['result']:
                        # Deduplicate by update_id across the process to avoid double replies
                        try:
                            uid = update.get('update_id')
                        except Exception:
                            uid = None
                        if uid is not None and not _mark_processed(uid):
                            continue
                        asyncio.run(self.bot.process_update(update))
                        offset = update['update_id'] + 1
                        
                # Small delay to prevent API spam
                import time
                time.sleep(1)
                
            except Exception as e:
                # Ultra-safe logging
                try:
                    error_safe = str(e).encode('ascii', errors='ignore').decode('ascii')
                    logger.error(f"Polling error: {error_safe}")
                except Exception:
                    logger.error("Polling error: encoding issue")
                import time
                time.sleep(5)

class Application:
    @staticmethod
    def builder():
        class Builder:
            def __init__(self):
                self._token = None
            def token(self, token):
                self._token = token
                return self
            def build(self):
                return TelegramApplication(self._token)
        return Builder()

# Handler creators
def CommandHandler(command, func):
    return (command, func)

def MessageHandler(filters_obj, func):  
    return ('message', func)

def CallbackQueryHandler(func):
    return ('callback', func)

def VoiceHandler(func):
    return ('voice', func)

class FilterType:
    def __init__(self, name):
        self.name = name
    
    def __and__(self, other):
        return FilterType(f"{self.name} & {other.name}")
    
    def __invert__(self):
        return FilterType(f"~{self.name}")

class filters:
    TEXT = FilterType('text')
    COMMAND = FilterType('command')
    VOICE = FilterType('voice')
    AUDIO = FilterType('audio')
# Circular import muammosini oldini olish uchun lazy import
def get_dependencies():
    from ai import get_ai_response, process_knowledge_base
    from models import User, Bot, ChatHistory
    from app import db, app
    return get_ai_response, process_knowledge_base, User, Bot, ChatHistory, db, app

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global deduplication for processed Telegram update IDs to avoid double handling
# even if multiple polling loops accidentally run in parallel. Keep it bounded.
PROCESSED_UPDATE_IDS = set()
from collections import deque
_processed_queue = deque(maxlen=500)

def _mark_processed(update_id):
    if update_id in PROCESSED_UPDATE_IDS:
        return False
    PROCESSED_UPDATE_IDS.add(update_id)
    _processed_queue.append(update_id)
    # When queue drops old IDs, also remove from the set
    if len(_processed_queue) == _processed_queue.maxlen:
        # Clean up extras beyond deque window
        while len(PROCESSED_UPDATE_IDS) > _processed_queue.maxlen:
            # This is a safety; usually set and deque stay in sync by size
            try:
                PROCESSED_UPDATE_IDS.pop()
            except KeyError:
                break
    return True

class TelegramBot:
    def __init__(self, bot_token, bot_id):
        if not TELEGRAM_AVAILABLE:
            raise ImportError("python-telegram-bot library not available")
            
        self.bot_token = bot_token
        self.bot_id = bot_id
        self.application = Application.builder().token(bot_token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup bot command and message handlers"""
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("language", self.language_command))
        self.application.add_handler(CommandHandler("ping", self.ping_command))
        self.application.add_handler(CallbackQueryHandler(self.language_callback))
        self.application.add_handler(CallbackQueryHandler(self.contact_callback))
        self.application.add_handler(VoiceHandler(self.handle_voice_message))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    async def start_command(self, update: Update, context) -> None:
        """Handle /start command"""
        if not update or not update.effective_user or not update.message:
            return
        
        # Deduplication: Skip if this update was already processed
        try:
            update_id = update.data.get('update_id') if hasattr(update, 'data') else None
            if update_id and not _mark_processed(update_id * 1000 + 1):  # Use different ID space for start_command
                logger.info(f"Skipping duplicate start_command for update_id: {update_id}")
                return
        except Exception:
            pass
        
        user = update.effective_user
        
        get_ai_response, process_knowledge_base, User, Bot, ChatHistory, db, app = get_dependencies()
        with app.app_context():
            # Get or create user
            db_user = User.query.filter_by(telegram_id=str(user.id)).first()
            if not db_user:
                # Register new telegram user
                db_user = User()
                db_user.username = f"tg_{user.id}"
                db_user.email = f"tg_{user.id}@telegram.bot"
                db_user.password_hash = "telegram_user"
                db_user.telegram_id = str(user.id)
                db_user.language = 'uz'
                db_user.subscription_type = 'free'
                db.session.add(db_user)
                db.session.commit()
            
            # Get bot info
            bot = Bot.query.get(self.bot_id)
            bot_name = bot.name if bot else "BotFactory AI"
            
            # Track customer interaction
            try:
                from models import BotCustomer
                customer = BotCustomer.query.filter_by(
                    bot_id=self.bot_id,
                    platform='telegram',
                    platform_user_id=str(user.id)
                ).first()
                
                if not customer:
                    # Create new customer record
                    customer = BotCustomer()
                    customer.bot_id = self.bot_id
                    customer.platform = 'telegram'
                    customer.platform_user_id = str(user.id)
                    customer.first_name = user.first_name or ''
                    customer.last_name = user.last_name or ''
                    customer.username = user.username or ''
                    customer.language = db_user.language
                    customer.is_active = True
                    customer.message_count = 1
                    db.session.add(customer)
                else:
                    # Update existing customer
                    customer.first_name = user.first_name or customer.first_name
                    customer.last_name = user.last_name or customer.last_name
                    customer.username = user.username or customer.username
                    customer.last_interaction = datetime.utcnow()
                    customer.message_count += 1
                    customer.is_active = True
                
                db.session.commit()
                logging.info(f"Customer tracked: {customer.display_name} for bot {self.bot_id}")
                
            except Exception as customer_error:
                logging.error(f"Failed to track customer: {str(customer_error)}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
            
            welcome_message = f"🤖 Salom! Men {bot_name} chatbot!\n\n"
            welcome_message += "📝 Menga savolingizni yozing va men sizga yordam beraman.\n"
            welcome_message += "❓ Yordam uchun /help buyrug'ini ishlating."
            
            if update.message:
                await update.message.reply_text(welcome_message)
                
            # Til tanlash uchun inline klaviaturani ko'rsatish
            try:
                owner_subscription = bot.owner.subscription_type if (bot and bot.owner) else 'free'
                owner_subscription_norm = (owner_subscription or '').strip().lower()
                owner_allows_extra = owner_subscription_norm in ['starter', 'basic', 'premium', 'admin']
                
                lang_keyboard = []
                lang_keyboard.append([InlineKeyboardButton("🇺🇿 O'zbek", callback_data="lang_uz")])
                if owner_allows_extra:
                    lang_keyboard.append([InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")])
                    lang_keyboard.append([InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")])
                else:
                    lang_keyboard.append([InlineKeyboardButton("🔒 Русский (Starter/Basic/Premium)", callback_data="lang_locked")])
                    lang_keyboard.append([InlineKeyboardButton("🔒 English (Starter/Basic/Premium)", callback_data="lang_locked")])
                
                lang_markup = InlineKeyboardMarkup(lang_keyboard)
                lang_msg = "🌐 Tilni tanlang / Выберите язык / Choose language:"
                if update.message:
                    await update.message.reply_text(lang_msg, reply_markup=lang_markup)
            except Exception as lang_err:
                logger.error(f"Failed to send language keyboard: {lang_err}")

            # Send Mini App button if enabled
            try:
                if bot.miniapp_enabled:
                    import os
                    base_url = os.environ.get('BASE_URL', 'http://127.0.0.1:5000')
                    miniapp_url = f"{base_url}/static/miniapp/index.html?bot_id={self.bot_id}"
                    
                    miniapp_keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(
                            text="📱 Mahsulotlar / Xizmatlar",
                            web_app={"url": miniapp_url}
                        )],
                        [InlineKeyboardButton(
                            text="📞 Bog'lanish",
                            callback_data="contact_info"
                        )]
                    ])
                    await update.message.reply_text(
                        "🛒 Katalogni ko'rish uchun quyidagi tugmani bosing:",
                        reply_markup=miniapp_keyboard
                    )
            except Exception as miniapp_error:
                logger.error(f"Failed to send Mini App button: {str(miniapp_error)[:100]}")

            # Send contact options inline keyboard
            try:
                contact_markup = self._build_contact_keyboard(bot)
                if update.message and contact_markup:
                    await update.message.reply_text("📞 Biz bilan bog'lanish usullari:", reply_markup=contact_markup)
            except Exception as e:
                logger.error(f"Failed to send contact keyboard: {str(e)[:100]}")
    
    async def help_command(self, update: Update, context) -> None:
        """Handle /help command"""
        help_text = """
🤖 BotFactory AI Yordam

📋 Mavjud buyruqlar:
/start - Botni qayta ishga tushirish
/help - Yordam ma'lumotlari
/language - Tilni tanlash

💬 Oddiy xabar yuborib, men bilan suhbatlashishingiz mumkin!

🌐 Qo'llab-quvvatlanadigan tillar:
• O'zbek tili (bepul)
• Rus tili (Starter/Basic/Premium)
• Ingliz tili (Starter/Basic/Premium)
        """
        if update and update.message:
            await update.message.reply_text(help_text)
    
    async def language_command(self, update: Update, context) -> None:
        """Handle /language command"""
        if not update or not update.effective_user or not update.message:
            return
        
        user_id = str(update.effective_user.id)
        
        get_ai_response, process_knowledge_base, User, Bot, ChatHistory, db, app = get_dependencies()
        with app.app_context():
            db_user = User.query.filter_by(telegram_id=user_id).first()
            if not db_user:
                if update.message:
                    await update.message.reply_text("❌ Foydalanuvchi topilmadi!")
                return
            
            # Determine availability by BOT OWNER's subscription, not end-user
            bot = Bot.query.get(self.bot_id)
            owner_subscription = bot.owner.subscription_type if (bot and bot.owner) else 'free'
            owner_subscription_norm = (owner_subscription or '').strip().lower()
            owner_allows_extra = owner_subscription_norm in ['starter', 'basic', 'premium', 'admin']
            
            # Create language selection keyboard
            keyboard = []
            keyboard.append([InlineKeyboardButton("🇺🇿 O'zbek", callback_data="lang_uz")])
            if owner_allows_extra:
                keyboard.append([InlineKeyboardButton("🇷🇺 Русский", callback_data="lang_ru")])
                keyboard.append([InlineKeyboardButton("🇺🇸 English", callback_data="lang_en")])
            else:
                keyboard.append([InlineKeyboardButton("🔒 Русский (Starter/Basic/Premium)", callback_data="lang_locked")])
                keyboard.append([InlineKeyboardButton("🔒 English (Starter/Basic/Premium)", callback_data="lang_locked")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            current_lang = db_user.language
            lang_names = {'uz': "O'zbek", 'ru': "Русский", 'en': "English"}
            # Use a variable for default to avoid nested quotes in f-string
            default_lang = "O'zbek"
            message = f"🌐 Joriy til: {lang_names.get(current_lang, default_lang)}\n"
            message += "Tilni tanlang:"
            
            if update.message:
                await update.message.reply_text(message, reply_markup=reply_markup)
    
    async def language_callback(self, update: Update, context) -> None:
        """Handle language selection callback"""
        if not update or not update.callback_query:
            return
        
        query = update.callback_query
        await query.answer()
        
        if not query.from_user or not query.data:
            return
        
        # Only process language callbacks to avoid collisions with other callbacks
        if not (query.data.startswith('lang_') or query.data == 'lang_locked'):
            return

        user_id = str(query.from_user.id)
        language = query.data.split('_')[1] if '_' in query.data else None
        
        if query.data == "lang_locked":
            if query:
                await query.edit_message_text("🔒 Bu til faqat Starter, Basic yoki Premium obunachi uchun mavjud!")
            return
        
        if not language:
            return
        
        get_ai_response, process_knowledge_base, User, Bot, ChatHistory, db, app = get_dependencies()
        with app.app_context():
            db_user = User.query.filter_by(telegram_id=user_id).first()
            bot = Bot.query.get(self.bot_id)
            owner_subscription = bot.owner.subscription_type if (bot and bot.owner) else 'free'
            owner_allows_extra = owner_subscription in ['starter', 'basic', 'premium', 'admin']
            
            if not db_user:
                return
            
            # Allow Uzbek for all; RU/EN only if owner allows
            if language == 'uz' or owner_allows_extra:
                db_user.language = language
                db.session.commit()
                lang_names = {'uz': "O'zbek", 'ru': "Русский", 'en': "English"}
                success_messages = {
                    'uz': f"✅ Til {lang_names[language]} ga o'zgartirildi!",
                    'ru': f"✅ Язык изменен на {lang_names[language]}!",
                    'en': f"✅ Language changed to {lang_names[language]}!"
                }
                if query:
                    await query.edit_message_text(success_messages.get(language, success_messages['uz']))
            else:
                if query:
                    await query.edit_message_text("❌ Bu tilni tanlash uchun obunangizni yangilang!")

    async def ping_command(self, update: Update, context) -> None:
        """Soddalashtirilgan /ping testi"""
        if update and update.message:
            await update.message.reply_text("pong ✅")

    async def contact_callback(self, update: Update, context) -> None:
        """Handle contact-related callbacks (e.g., operator request)"""
        if not update or not update.callback_query:
            return
        query = update.callback_query
        data = query.data or ""
        if data != "contact_operator":
            return  # Ignore other callbacks
        await query.answer()

        # Notify user
        try:
            await query.edit_message_text("✅ Operatorga xabarnoma yuborildi. Tez orada bog'lanamiz.")
        except Exception:
            pass

        # Try to notify admin chat
        try:
            get_ai_response, process_knowledge_base, User, Bot, ChatHistory, db, app = get_dependencies()
            with app.app_context():
                bot = Bot.query.get(self.bot_id)
                admin_chat = None
                if bot and bot.owner and getattr(bot.owner, 'admin_chat_id', None):
                    admin_chat = str(bot.owner.admin_chat_id)
                if not admin_chat:
                    admin_chat = os.environ.get('ADMIN_TELEGRAM_ID')
                if admin_chat:
                    user = query.from_user
                    text = f"📩 Yangi operator so'rovi\nBot: {bot.name if bot else self.bot_id}\nFoydalanuvchi: @{user.username or 'nomalum'} (ID: {user.id})"
                    self.application.bot.send_message(admin_chat, text)
        except Exception as e:
            logger.error(f"Failed to notify admin: {str(e)[:100]}")

    def _build_contact_keyboard(self, bot_obj=None):
        """Create inline keyboard with Telegram DM, Phone call, and Operator callback."""
        try:
            tg_link = os.environ.get('SUPPORT_TELEGRAM') or "https://t.me/akramjon0011"
            phone_number = os.environ.get('SUPPORT_PHONE') or "+998900000000"
            # If bot owner has a notification channel or username, prefer that for Telegram link
            if bot_obj and bot_obj.owner and getattr(bot_obj.owner, 'notification_channel', None):
                # notification_channel may be like @channel; if it's a user, it still works
                ch = bot_obj.owner.notification_channel
                if ch.startswith('@'):
                    tg_link = f"https://t.me/{ch[1:]}"
            keyboard = [
                [InlineKeyboardButton("💬 Telegramda yozish", url=tg_link)],
                [InlineKeyboardButton("📞 Qo'ng'iroq qilish", url=f"tel:{phone_number}")],
                [InlineKeyboardButton("👨‍💼 Operator bilan bog'lanish", callback_data="contact_operator")]
            ]
            return InlineKeyboardMarkup(keyboard)
        except Exception as e:
            logger.error(f"Failed to build contact keyboard: {str(e)[:100]}")
            return None
    
    
    async def handle_voice_message(self, update: Update, context) -> None:
        """Handle voice and audio messages"""
        if not update or not update.effective_user or not update.message:
            return
        
        user_id = str(update.effective_user.id)
        
        # Check if it's a voice message or audio file
        voice_data = None
        if update.message.voice:
            voice_data = update.message.voice
        elif update.message.audio:
            voice_data = update.message.audio
        elif update.message.document and update.message.document.get('mime_type', '').startswith('audio/'):
            voice_data = update.message.document
        
        if not voice_data:
            return
        
        get_ai_response, process_knowledge_base, User, Bot, ChatHistory, db, app = get_dependencies()
        
        with app.app_context():
            # Get user info
            db_user = User.query.filter_by(telegram_id=user_id).first()
            if not db_user:
                if update.message:
                    await update.message.reply_text("❌ Foydalanuvchi topilmadi! /start buyrug'ini ishlating.")
                return
            
            # Get bot info
            bot = Bot.query.get(self.bot_id)
            if not bot:
                if update.message:
                    await update.message.reply_text("❌ Bot topilmadi!")
                return
            
            # Check subscription
            if not db_user.subscription_active():
                if update.message:
                    await update.message.reply_text("❌ Obunangiz tugagan! Iltimos, obunani yangilang.")
                return
            
            # Send typing indicator while processing
            try:
                if update.effective_chat:
                    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
            except Exception:
                pass
            
            try:
                # Get file info and download
                file_id = voice_data.get('file_id')
                if not file_id:
                    if update.message:
                        await update.message.reply_text("❌ Ovoz fayli topilmadi!")
                    return
                
                # Get file info from Telegram API
                file_info_url = f"{context.bot.base_url}/getFile"
                file_info_response = requests.get(file_info_url, params={'file_id': file_id})
                
                if not file_info_response.json().get('ok'):
                    if update.message:
                        await update.message.reply_text("❌ Ovoz faylini olishda xatolik yuz berdi!")
                    return
                
                file_path = file_info_response.json()['result']['file_path']
                file_url = f"https://api.telegram.org/file/bot{context.bot.token}/{file_path}"
                
                # Process the voice message using Gemini-based audio transcription
                try:
                    # Run the synchronous audio processing in executor to avoid blocking
                    loop = asyncio.get_event_loop()
                    transcribed_text = await loop.run_in_executor(
                        None, lambda: transcribe_audio_from_url(file_url, db_user.language)
                    )
                    
                    if not transcribed_text or transcribed_text.strip() == "":
                        if update.message:
                            await update.message.reply_text("🎤 Ovoz xabari eshitilmadi yoki bo'sh. Iltimos, qaytadan urinib ko'ring.")
                        return
                    
                    # Send transcription confirmation
                    if update.message:
                        await update.message.reply_text(f"🎤 Eshitildi: {transcribed_text}")
                    
                    # Process transcribed text as a regular message
                    # Get knowledge base
                    try:
                        knowledge_base = process_knowledge_base(self.bot_id)
                        
                        # Get recent chat history
                        recent_history = ""
                        history_entries = ChatHistory.query.filter_by(
                            bot_id=self.bot_id, 
                            user_telegram_id=user_id
                        ).order_by(ChatHistory.created_at.desc()).limit(10).all()
                        
                        if history_entries:
                            history_parts = []
                            for entry in reversed(history_entries):
                                history_parts.append(f"Foydalanuvchi: {entry.message}")
                                history_parts.append(f"Bot: {entry.response}")
                            recent_history = "\n".join(history_parts)
                        
                        # Generate AI response for transcribed text
                        owner_contact_info = ""
                        if bot.owner:
                            owner_contact_info = f"Telefon raqam: {bot.owner.phone_number or 'Mavjud emas'}, Telegram: {bot.owner.telegram_id or 'Mavjud emas'}"
                        ai_response = get_ai_response(
                            message=transcribed_text,
                            bot_name=bot.name,
                            user_language=db_user.language,
                            knowledge_base=knowledge_base,
                            chat_history=recent_history,
                            owner_contact_info=owner_contact_info
                        )
                        
                        if ai_response:
                            # Clean response
                            from ai import validate_ai_response
                            cleaned_response = validate_ai_response(ai_response)
                            if not cleaned_response:
                                cleaned_response = ai_response
                            
                            # Send AI response
                            if update.message:
                                await update.message.reply_text(cleaned_response)
                            
                            # Save chat history
                            try:
                                chat_history = ChatHistory()
                                chat_history.bot_id = self.bot_id
                                chat_history.user_telegram_id = str(user_id)
                                chat_history.message = transcribed_text[:1000]
                                chat_history.response = cleaned_response[:2000]
                                chat_history.language = db_user.language or 'uz'
                                
                                db.session.add(chat_history)
                                db.session.commit()
                                
                            except Exception as db_error:
                                logger.error(f"Failed to save voice chat history: {str(db_error)[:100]}")
                                try:
                                    db.session.rollback()
                                except Exception:
                                    pass
                    
                    except Exception as processing_error:
                        logger.error(f"Voice message processing error: {str(processing_error)[:100]}")
                        if update.message:
                            await update.message.reply_text("❌ Ovoz xabarini qayta ishlashda xatolik yuz berdi.")
                
                except Exception as audio_error:
                    logger.error(f"Audio processing error: {str(audio_error)[:100]}")
                    if update.message:
                        await update.message.reply_text("❌ Ovoz faylini qayta ishlashda xatolik yuz berdi. Iltimos, qaytadan urinib ko'ring.")
            
            except Exception as voice_error:
                logger.error(f"Voice handler error: {str(voice_error)[:100]}")
                if update.message:
                    await update.message.reply_text("❌ Ovoz xabarini qayta ishlashda xatolik yuz berdi.")
    
    async def handle_message(self, update: Update, context) -> None:
        """Handle regular text messages"""
        if not update or not update.effective_user or not update.message:
            return
        
        user_id = str(update.effective_user.id)
        message_text = update.message.text
        
        if not message_text:
            return
        
        # Send typing indicator immediately
        try:
            if update.effective_chat:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        except Exception as e:
            logger.error(f"Failed to send typing action: {e}")
        
        get_ai_response, process_knowledge_base, User, Bot, ChatHistory, db, app = get_dependencies()
        logger.info("DEBUG: Dependencies loaded")
        
        with app.app_context():
            # Get user info
            db_user = User.query.filter_by(telegram_id=user_id).first()
            if not db_user:
                logger.info("DEBUG: User not found")
                if update.message:
                    await update.message.reply_text("❌ Foydalanuvchi topilmadi! /start buyrug'ini ishlating.")
                return
            
            logger.info("DEBUG: User found")
            
            # Get bot info
            bot = Bot.query.get(self.bot_id)
            if not bot:
                logger.info("DEBUG: Bot not found")
                if update.message:
                    await update.message.reply_text("❌ Bot topilmadi!")
                return
            
            logger.info("DEBUG: Bot found")
            
            # Track customer interaction
            try:
                from models import BotCustomer
                customer = BotCustomer.query.filter_by(
                    bot_id=self.bot_id,
                    platform='telegram',
                    platform_user_id=user_id
                ).first()
                
                if not customer:
                    # Create new customer record
                    user = update.effective_user
                    customer = BotCustomer()
                    customer.bot_id = self.bot_id
                    customer.platform = 'telegram'
                    customer.platform_user_id = user_id
                    customer.first_name = user.first_name or ''
                    customer.last_name = user.last_name or ''
                    customer.username = user.username or ''
                    customer.language = db_user.language
                    customer.is_active = True
                    customer.message_count = 1
                    db.session.add(customer)
                    logger.info(f"New customer created: {customer.display_name} for bot {self.bot_id}")
                else:
                    # Update existing customer
                    customer.last_interaction = datetime.utcnow()
                    customer.message_count += 1
                    customer.is_active = True
                    logger.info(f"Customer interaction updated: {customer.display_name}")
                
                db.session.commit()
            except Exception as customer_error:
                logger.error(f"Failed to track customer interaction: {str(customer_error)}")
                try:
                    db.session.rollback()
                except Exception:
                    pass
            
            # Check subscription with 14-day free trial per bot for new users
            trial_active = False
            trial_start = None
            try:
                from datetime import timedelta
                # Prefer bot-specific first_interaction for trial window
                try:
                    # 'customer' variable may exist from the tracking block above
                    trial_start = customer.first_interaction if 'customer' in locals() and customer and getattr(customer, 'first_interaction', None) else None
                except Exception:
                    trial_start = None
                if not trial_start:
                    # Fallback to user's account creation/start date
                    trial_start = db_user.subscription_start_date or db_user.created_at
                if trial_start:
                    trial_active = (datetime.utcnow() - trial_start) <= timedelta(days=14)
            except Exception:
                trial_active = False

            subscription_ok = db_user.subscription_active() or trial_active
            if not subscription_ok:
                logger.info("DEBUG: Subscription not active and free trial expired")
                if update.message:
                    await update.message.reply_text("❌ Obunangiz tugagan yoki bepul 14 kunlik sinov muddati yakunlangan. Iltimos, obunani yangilang.")
                return

            logger.info("DEBUG: Subscription active or trial active")

            # Immediate feedback to user so bot feels responsive
            try:
                feedback = "🤖 Xabaringiz qabul qilindi, javob tayyorlanmoqda..."
                # If trial is active, show remaining days
                try:
                    if trial_active and trial_start:
                        from datetime import datetime, timedelta
                        days_left = 14 - (datetime.utcnow() - trial_start).days
                        if days_left < 0:
                            days_left = 0
                        feedback += f"\n🎁 Bepul sinov: yana {days_left} kun qoldi"
                except Exception:
                    pass
                await update.message.reply_text(feedback)
            except Exception:
                pass
            
            # Send typing indicator while processing
            try:
                if update.effective_chat:
                    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
            except Exception:
                pass
            
            # Get knowledge base and chat history in parallel for faster processing
            try:
                # Get recent chat history in parallel (increased limit for better context)
                recent_history = ""
                history_entries = ChatHistory.query.filter_by(
                    bot_id=self.bot_id, 
                    user_telegram_id=user_id
                ).order_by(ChatHistory.created_at.desc()).limit(10).all()
                
                if history_entries:
                    history_parts = []
                    for entry in reversed(history_entries):
                        history_parts.append(f"Foydalanuvchi: {entry.message}")
                        history_parts.append(f"Bot: {entry.response}")
                    recent_history = "\n".join(history_parts)
                
                # Get knowledge base (potentially slower operation)
                knowledge_base = process_knowledge_base(self.bot_id)
                logger.info("DEBUG: Knowledge base and history processed")
                
            except Exception as hist_error:
                logger.error(f"Chat history/knowledge retrieval error: {str(hist_error)[:100]}")
                recent_history = ""
                knowledge_base = ""

            # Send typing indicator again before AI call
            try:
                if update.effective_chat:
                    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
            except Exception:
                pass

            # Generate AI response
            try:
                logger.info("DEBUG: Starting AI response generation")
                
                owner_contact_info = ""
                if bot.owner:
                    owner_contact_info = f"Telefon raqam: {bot.owner.phone_number or 'Mavjud emas'}, Telegram: {bot.owner.telegram_id or 'Mavjud emas'}"

                ai_response = get_ai_response(
                    message=message_text,
                    bot_name=bot.name,
                    user_language=db_user.language,
                    knowledge_base=knowledge_base,
                    chat_history=recent_history,
                    owner_contact_info=owner_contact_info
                )
                
                logger.info("DEBUG: AI response received")
                
                # Clean and prepare response first
                if ai_response:
                    # Import validation function
                    from ai import validate_ai_response
                    
                    # First validate and remove markdown formatting
                    cleaned_response = validate_ai_response(ai_response)
                    if not cleaned_response:
                        cleaned_response = ai_response
                    
                    # Replace problematic unicode characters but keep emojis
                    unicode_replacements = {
                        '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"',
                        '\u2013': '-', '\u2014': '-', '\u2026': '...', '\u00a0': ' ',
                        '\u2010': '-', '\u2011': '-', '\u2012': '-', '\u2015': '-'
                    }
                    
                    for unicode_char, replacement in unicode_replacements.items():
                        cleaned_response = cleaned_response.replace(unicode_char, replacement)
                    
                    # Fallback if empty
                    if not cleaned_response.strip():
                        cleaned_response = "Javob tayyor! 🤖"
                    
                    # Save chat history with proper error handling
                    try:
                        # Clean text and remove problematic Unicode characters
                        import re
                        
                        def clean_text_for_db(text):
                            if not text:
                                return ""
                            try:
                                # Simple string processing - let Python handle Unicode natively
                                if isinstance(text, bytes):
                                    text = text.decode('utf-8', errors='replace')
                                
                                # Keep original text as much as possible, just remove control chars
                                import re
                                clean_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', str(text))
                                
                                # Return the clean text - Python 3 handles Unicode natively
                                return clean_text
                            except Exception:
                                # Ultimate fallback - return empty string
                                return ""
                        
                        safe_message = clean_text_for_db(message_text)
                        safe_response = clean_text_for_db(cleaned_response)
                        
                        # Create new session for chat history to avoid rollback issues
                        try:
                            chat_history = ChatHistory()
                            chat_history.bot_id = self.bot_id
                            chat_history.user_telegram_id = str(user_id)  # Ensure string
                            chat_history.message = safe_message[:1000]  # Limit length
                            chat_history.response = safe_response[:2000]  # Limit length
                            chat_history.language = db_user.language or 'uz'
                            
                            db.session.add(chat_history)
                            db.session.commit()
                            logger.info("DEBUG: Chat history saved successfully")
                            
                        except Exception as db_error:
                            # Rollback on any database error
                            try:
                                db.session.rollback()
                                logger.error(f"Chat history save failed, rolled back: {str(db_error)[:100]}")
                            except Exception:
                                logger.error("Chat history save failed and rollback failed")
                        
                        # Send notification to admin using bot's own token
                        try:
                            bot_owner = bot.owner
                            if (bot_owner and bot_owner.notifications_enabled and 
                                (bot_owner.admin_chat_id or bot_owner.notification_channel)):
                                
                                from notification_service import TelegramNotificationService
                                # Use current bot's token for notifications
                                bot_notification_service = TelegramNotificationService(bot.telegram_token)
                                
                                # Get username from update
                                username = ""
                                try:
                                    if update and update.effective_user and hasattr(update.effective_user, 'username'):
                                        username = update.effective_user.username or ""
                                except Exception:
                                    username = ""
                                
                                bot_notification_service.send_chat_notification(
                                    admin_chat_id=bot_owner.admin_chat_id,
                                    channel_id=bot_owner.notification_channel,
                                    bot_name=bot.name,
                                    user_id=user_id,
                                    user_message=safe_message,
                                    bot_response=safe_response,
                                    platform="Telegram",
                                    username=username
                                )
                                logger.info("DEBUG: Notification sent to admin")
                        except Exception as notif_error:
                            logger.error(f"Notification error: {str(notif_error)[:100]}")
                            
                    except Exception as db_error:
                        # Safe error logging
                        error_msg = str(db_error).encode('ascii', errors='ignore').decode('ascii')[:100]
                        logger.error(f"Failed to save chat history: {error_msg}")
                    
                    # Send the response
                    try:
                        if update.message:
                            await update.message.reply_text(cleaned_response)
                            logger.info("DEBUG: Response sent successfully")
                            
                            # Check for relevant product images to send
                            try:
                                from ai import find_relevant_product_images
                                relevant_images = find_relevant_product_images(self.bot_id, message_text)
                                
                                for image_info in relevant_images:
                                    try:
                                        await update.message.reply_photo(
                                            photo=image_info['url'],
                                            caption=image_info['caption']
                                        )
                                        logger.info(f"DEBUG: Product image sent for {image_info['product_name']}")
                                    except Exception as img_error:
                                        logger.error(f"Failed to send product image: {str(img_error)[:100]}")
                            except Exception as img_search_error:
                                logger.error(f"Failed to search product images: {str(img_search_error)[:100]}")
                    except Exception as send_error:
                        # Final fallback
                        logger.error(f"Failed to send response: {str(send_error)[:100]}")
                        try:
                            if update.message:
                                await update.message.reply_text("Javob tayyor! 🤖")
                        except Exception:
                            logger.error("Failed to send fallback message")
                else:
                    await update.message.reply_text("Javob berishda xatolik yuz berdi! Keyinroq urinib ko'ring. ⚠️")
                    
            except Exception as e:
                # Debug: log which step failed (with safe encoding)
                try:
                    error_str = str(e).encode('ascii', errors='ignore').decode('ascii')[:200]
                    logger.error(f"DEBUG: Message handling failed: {error_str}")
                except Exception:
                    logger.error("DEBUG: Message handling failed with encoding error")
                
                # Send simple error message
                try:
                    await update.message.reply_text("Xatolik yuz berdi!")
                except Exception:
                    print("[ERROR] Cannot send error message to user")
    
    
    async def _get_telegram_file_url(self, file_id):
        """Get file URL from Telegram API"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getFile"
            response = requests.get(url, params={'file_id': file_id})
            data = response.json()
            
            if data.get('ok') and 'result' in data:
                file_path = data['result']['file_path']
                return f"https://api.telegram.org/file/bot{self.bot_token}/{file_path}"
            else:
                logger.error(f"Telegram getFile API error: {data}")
                return None
                
        except Exception as e:
            logger.error(f"Error getting Telegram file URL: {str(e)}")
            return None
    
    def run(self):
        """Start the bot"""
        try:
            self.application.run_polling()
        except Exception as e:
            # Ultra-safe logging
            try:
                error_safe = str(e).encode('ascii', errors='ignore').decode('ascii')
                logger.error(f"Bot running error: {error_safe}")
            except Exception:
                logger.error("Bot running error: encoding issue")

def start_telegram_bot(bot_token, bot_id):
    """Start a telegram bot instance"""
    try:
        bot = TelegramBot(bot_token, bot_id)
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot {bot_id}: {str(e)}")

# Bot manager for multiple bots
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
                import threading
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

def validate_telegram_token(token):
    """Telegram bot tokenini tekshirish"""
    import requests
    try:
        # Basic token format check
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
            return False  # Extend later for Instagram/WhatsApp

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
            
        # Token validatsiyasi
        if not validate_telegram_token(bot_token):
            logger.error(f"Invalid token for bot {bot_id}")
            return False
            
        # Botni ishga tushirish
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

def process_webhook_update(bot_id, bot_token, update_data):
    """Webhook orqali kelgan update ni qayta ishlash"""
    try:
        # Dependencies ni olish
        get_ai_response, process_knowledge_base, User, Bot, ChatHistory, db, app = get_dependencies()
        
        logger.info(f"DEBUG: Processing webhook update for bot {bot_id}")
        
        # Update ma'lumotlarini tahlil qilish
        if 'message' in update_data:
            message = update_data['message']
            chat_id = message.get('chat', {}).get('id')
            user_id = message.get('from', {}).get('id')
            text = message.get('text', '')
            
            if not chat_id or not user_id:
                return False
                
            # Foydalanuvchini topish yoki yaratish
            with app.app_context():
                telegram_user = User.query.filter_by(telegram_id=str(user_id)).first()
                if not telegram_user:
                    # Yangi foydalanuvchi yaratish
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
                    
                # Botni topish
                bot = Bot.query.get(bot_id)
                if not bot or not bot.telegram_token:
                    return False
                    
                # Obunani tekshirish: 14 kunlik sinov oynasi (yangi foydalanuvchilar uchun)
                trial_active = False
                try:
                    from datetime import timedelta
                    # BotCustomer.first_interaction ga qarab
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
                    # Language buttons qo'shish mumkin
                    send_webhook_message(bot_token, chat_id, lang_msg)
                    return True
                    
                # AI javob olish
                try:
                    # Bilim bazasini olish
                    knowledge_base = ""
                    if hasattr(bot, 'knowledge_base') and bot.knowledge_base:
                        for kb in bot.knowledge_base:
                            if kb.content:
                                knowledge_base += f"{kb.content}\n\n"
                                
                    # Suhbat tarixini olish (xotirani yaxshilash maqsadida limit 10 qilingan)
                    chat_history = ""
                    recent_chats = ChatHistory.query.filter_by(
                        bot_id=bot_id, 
                        user_telegram_id=str(chat_id)
                    ).order_by(ChatHistory.created_at.desc()).limit(10).all()
                    
                    for chat in reversed(recent_chats):
                        chat_history += f"Foydalanuvchi: {chat.message}\nBot: {chat.response}\n\n"
                    
                    # AI javob olish
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
                        
                    # Suhbat tarixini saqlash
                    chat_record = ChatHistory()
                    chat_record.bot_id = bot_id
                    chat_record.user_telegram_id = str(chat_id)
                    chat_record.message = text[:1000]
                    chat_record.response = ai_response[:2000]
                    chat_record.created_at = datetime.now()
                    db.session.add(chat_record)
                    db.session.commit()
                    
                    # Javobni yuborish
                    send_webhook_message(bot_token, chat_id, ai_response)
                    return True
                    
                except Exception as e:
                    logger.error(f"AI processing error: {str(e)}")
                    error_msg = "Kechirasiz, xatolik yuz berdi. Iltimos, qayta urinib ko'ring."
                    send_webhook_message(bot_token, chat_id, error_msg)
                    return True
                    
        elif 'callback_query' in update_data:
            # Callback query ni qayta ishlash
            callback = update_data['callback_query']
            chat_id = callback.get('message', {}).get('chat', {}).get('id')
            callback_data = callback.get('data', '')
            
            if chat_id and callback_data:
                # Callback javobini qayta ishlash
                response = f"Siz {callback_data} ni tanladingiz."
                send_webhook_message(bot_token, chat_id, response)
                return True
                
        return True
        
    except Exception as e:
        logger.error(f"Webhook processing error for bot {bot_id}: {str(e)}")
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

def send_admin_message_to_user(telegram_id, message_text):
    """Send a message from admin to a specific user"""
    try:
        # Get any bot token to send message (we'll use the first available bot)
        get_ai_response, process_knowledge_base, User, Bot, ChatHistory, db, app = get_dependencies()
        
        with app.app_context():
            bot = Bot.query.first()
            if not bot or not bot.telegram_token:
                return False
            
            # Create HTTP bot instance
            http_bot = TelegramHTTPBot(bot.telegram_token)
            
            # Send message
            response = http_bot.send_message(telegram_id, f"📢 Admin xabari:\n\n{message_text}")
            
            if response and response.get('ok'):
                return True
            return False
            
    except Exception as e:
        logger.error(f"Error sending admin message: {e}")
        return False
