"""
Telegram Bot Handlers — TelegramBot class with all command and message handlers.
"""
import os
import re
import logging
import asyncio
import requests
from datetime import datetime, timedelta
from audio_processor import transcribe_audio_from_url

from telegram.sdk import (
    TELEGRAM_AVAILABLE, Update, InlineKeyboardButton, InlineKeyboardMarkup,
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    VoiceHandler, filters, _mark_processed
)

logger = logging.getLogger(__name__)


# Circular import muammosini oldini olish uchun lazy import
def get_dependencies():
    from ai import get_ai_response, process_knowledge_base
    from models import User, Bot, ChatHistory
    from app import db, app
    return get_ai_response, process_knowledge_base, User, Bot, ChatHistory, db, app


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

        # Deduplication
        try:
            update_id = update.data.get('update_id') if hasattr(update, 'data') else None
            if update_id and not _mark_processed(update_id * 1000 + 1):
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

            # Moved Mini App and contact keyboards to language_callback

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

            bot = Bot.query.get(self.bot_id)
            owner_subscription = bot.owner.subscription_type if (bot and bot.owner) else 'free'
            owner_subscription_norm = (owner_subscription or '').strip().lower()
            owner_allows_extra = owner_subscription_norm in ['starter', 'basic', 'premium', 'admin']

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

                # Send Mini App button if enabled and Premium/Admin
                try:
                    owner_sub = (bot.owner.subscription_type or 'free').lower().strip()
                    if bot.miniapp_enabled and owner_sub in ['premium', 'admin']:
                        import os
                        base_url = os.environ.get('BASE_URL', 'https://botfactory-am64.onrender.com')
                        miniapp_url = f"{base_url}/api/miniapp/?bot_id={self.bot_id}"

                        texts = {
                            'uz': {"btn1": "📱 Mahsulotlar / Xizmatlar", "btn2": "📞 Bog'lanish", "msg": "🛒 Katalogni ko'rish uchun quyidagi tugmani bosing:"},
                            'ru': {"btn1": "📱 Товары / Услуги", "btn2": "📞 Контакты", "msg": "🛒 Нажмите кнопку ниже, чтобы посмотреть каталог:"},
                            'en': {"btn1": "📱 Products / Services", "btn2": "📞 Contact", "msg": "🛒 Click the button below to view the catalog:"}
                        }
                        t = texts.get(language, texts['uz'])

                        miniapp_keyboard = InlineKeyboardMarkup([
                            [InlineKeyboardButton(text=t["btn1"], web_app={"url": miniapp_url})],
                            [InlineKeyboardButton(text=t["btn2"], callback_data="contact_info")]
                        ])
                        if update.effective_chat:
                            await context.bot.send_message(chat_id=update.effective_chat.id, text=t["msg"], reply_markup=miniapp_keyboard)
                except Exception as miniapp_error:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to send Mini App button: {str(miniapp_error)[:100]}")

                # Send contact options inline keyboard
                try:
                    contact_markup = self._build_contact_keyboard(bot)
                    if update.effective_chat and contact_markup:
                        contact_msgs = {'uz': "📞 Biz bilan bog'lanish usullari:", 'ru': "📞 Способы связи с нами:", 'en': "📞 Contact us:"}
                        await context.bot.send_message(chat_id=update.effective_chat.id, text=contact_msgs.get(language, contact_msgs['uz']), reply_markup=contact_markup)
                except Exception as e:
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.error(f"Failed to send contact keyboard: {str(e)[:100]}")
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
        if data == "contact_info":
            await query.answer()
            try:
                get_ai_response, process_knowledge_base, User, Bot, ChatHistory, db, app = get_dependencies()
                with app.app_context():
                    from models import BotCustomer
                    bot = Bot.query.get(self.bot_id)
                    customer = BotCustomer.query.filter_by(bot_id=bot.id, platform='telegram', platform_user_id=str(query.from_user.id)).first()
                    language = customer.language if customer else 'uz'
                    
                    contact_markup = self._build_contact_keyboard(bot)
                    if contact_markup and update.effective_chat:
                        contact_msgs = {'uz': "📞 Biz bilan bog'lanish usullari:", 'ru': "📞 Способы связи с нами:", 'en': "📞 Contact us:"}
                        await context.bot.send_message(chat_id=update.effective_chat.id, text=contact_msgs.get(language, contact_msgs['uz']), reply_markup=contact_markup)
            except Exception as e:
                logger.error(f"Failed to send contact info on button click: {str(e)}")
            return

        if data != "contact_operator":
            return
        await query.answer()

        try:
            await query.edit_message_text("✅ Operatorga xabarnoma yuborildi. Tez orada bog'lanamiz.")
        except Exception:
            pass

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
            if bot_obj and bot_obj.owner and getattr(bot_obj.owner, 'notification_channel', None):
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
            db_user = User.query.filter_by(telegram_id=user_id).first()
            if not db_user:
                if update.message:
                    await update.message.reply_text("❌ Foydalanuvchi topilmadi! /start buyrug'ini ishlating.")
                return

            bot = Bot.query.get(self.bot_id)
            if not bot:
                if update.message:
                    await update.message.reply_text("❌ Bot topilmadi!")
                return

            if not db_user.subscription_active():
                if update.message:
                    await update.message.reply_text("❌ Obunangiz tugagan! Iltimos, obunani yangilang.")
                return

            try:
                if update.effective_chat:
                    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
            except Exception:
                pass

            try:
                file_id = voice_data.get('file_id')
                if not file_id:
                    if update.message:
                        await update.message.reply_text("❌ Ovoz fayli topilmadi!")
                    return

                file_info_url = f"{context.bot.base_url}/getFile"
                file_info_response = requests.get(file_info_url, params={'file_id': file_id})

                if not file_info_response.json().get('ok'):
                    if update.message:
                        await update.message.reply_text("❌ Ovoz faylini olishda xatolik yuz berdi!")
                    return

                file_path = file_info_response.json()['result']['file_path']
                file_url = f"https://api.telegram.org/file/bot{context.bot.token}/{file_path}"

                try:
                    loop = asyncio.get_event_loop()
                    transcribed_text = await loop.run_in_executor(
                        None, lambda: transcribe_audio_from_url(file_url, db_user.language)
                    )

                    if not transcribed_text or transcribed_text.strip() == "":
                        if update.message:
                            await update.message.reply_text("🎤 Ovoz xabari eshitilmadi yoki bo'sh. Iltimos, qaytadan urinib ko'ring.")
                        return

                    if update.message:
                        await update.message.reply_text(f"🎤 Eshitildi: {transcribed_text}")

                    try:
                        knowledge_base = process_knowledge_base(self.bot_id, user_message=transcribed_text)

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
                            from ai import validate_ai_response
                            cleaned_response = validate_ai_response(ai_response)
                            if not cleaned_response:
                                cleaned_response = ai_response

                            if update.message:
                                await update.message.reply_text(cleaned_response)

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

        try:
            if update.effective_chat:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
        except Exception as e:
            logger.error(f"Failed to send typing action: {e}")

        get_ai_response, process_knowledge_base, User, Bot, ChatHistory, db, app = get_dependencies()
        logger.info("DEBUG: Dependencies loaded")

        with app.app_context():
            db_user = User.query.filter_by(telegram_id=user_id).first()
            if not db_user:
                logger.info("DEBUG: User not found")
                if update.message:
                    await update.message.reply_text("❌ Foydalanuvchi topilmadi! /start buyrug'ini ishlating.")
                return

            logger.info("DEBUG: User found")

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

            # Check subscription with 14-day free trial
            trial_active = False
            trial_start = None
            try:
                try:
                    trial_start = customer.first_interaction if 'customer' in locals() and customer and getattr(customer, 'first_interaction', None) else None
                except Exception:
                    trial_start = None
                if not trial_start:
                    trial_start = db_user.subscription_start_date or db_user.created_at
                if trial_start:
                    trial_active = (datetime.utcnow() - trial_start) <= timedelta(days=14)
            except Exception:
                trial_active = False

            subscription_ok = db_user.subscription_active() or trial_active
            if not subscription_ok:
                logger.info("DEBUG: Subscription not active and free trial expired")
                if update.message:
                    await update.message.reply_text("❌ Obunangiz tugagan yoki bepul 7 kunlik sinov muddati yakunlangan. Iltimos, obunani yangilang.")
                return

            logger.info("DEBUG: Subscription active or trial active")

            # Immediate feedback
            try:
                feedback = "🤖 Xabaringiz qabul qilindi, javob tayyorlanmoqda..."
                await update.message.reply_text(feedback)
            except Exception:
                pass

            try:
                if update.effective_chat:
                    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action='typing')
            except Exception:
                pass

            # Get knowledge base and chat history
            try:
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

                knowledge_base = process_knowledge_base(self.bot_id, user_message=message_text)
                logger.info("DEBUG: Knowledge base and history processed")

            except Exception as hist_error:
                logger.error(f"Chat history/knowledge retrieval error: {str(hist_error)[:100]}")
                recent_history = ""
                knowledge_base = ""

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

                if ai_response:
                    from ai import validate_ai_response

                    cleaned_response = validate_ai_response(ai_response)
                    if not cleaned_response:
                        cleaned_response = ai_response

                    unicode_replacements = {
                        '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"',
                        '\u2013': '-', '\u2014': '-', '\u2026': '...', '\u00a0': ' ',
                        '\u2010': '-', '\u2011': '-', '\u2012': '-', '\u2015': '-'
                    }

                    for unicode_char, replacement in unicode_replacements.items():
                        cleaned_response = cleaned_response.replace(unicode_char, replacement)

                    if not cleaned_response.strip():
                        cleaned_response = "Javob tayyor! 🤖"

                    # Save chat history
                    try:
                        def clean_text_for_db(text):
                            if not text:
                                return ""
                            try:
                                if isinstance(text, bytes):
                                    text = text.decode('utf-8', errors='replace')
                                clean_text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', str(text))
                                return clean_text
                            except Exception:
                                return ""

                        safe_message = clean_text_for_db(message_text)
                        safe_response = clean_text_for_db(cleaned_response)

                        try:
                            chat_history = ChatHistory()
                            chat_history.bot_id = self.bot_id
                            chat_history.user_telegram_id = str(user_id)
                            chat_history.message = safe_message[:1000]
                            chat_history.response = safe_response[:2000]
                            chat_history.language = db_user.language or 'uz'

                            db.session.add(chat_history)
                            db.session.commit()
                            logger.info("DEBUG: Chat history saved successfully")

                        except Exception as db_error:
                            try:
                                db.session.rollback()
                                logger.error(f"Chat history save failed, rolled back: {str(db_error)[:100]}")
                            except Exception:
                                logger.error("Chat history save failed and rollback failed")

                        # Send notification to admin
                        try:
                            bot_owner = bot.owner
                            if (bot_owner and bot_owner.notifications_enabled and
                                (bot_owner.admin_chat_id or bot_owner.notification_channel)):

                                from notification_service import TelegramNotificationService
                                bot_notification_service = TelegramNotificationService(bot.telegram_token)

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
                        error_msg = str(db_error).encode('ascii', errors='ignore').decode('ascii')[:100]
                        logger.error(f"Failed to save chat history: {error_msg}")

                    # Send the response
                    try:
                        if update.message:
                            await update.message.reply_text(cleaned_response)
                            logger.info("DEBUG: Response sent successfully")

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
                        logger.error(f"Failed to send response: {str(send_error)[:100]}")
                        try:
                            if update.message:
                                await update.message.reply_text("Javob tayyor! 🤖")
                        except Exception:
                            logger.error("Failed to send fallback message")
                else:
                    await update.message.reply_text("Javob berishda xatolik yuz berdi! Keyinroq urinib ko'ring. ⚠️")

            except Exception as e:
                try:
                    error_str = str(e).encode('ascii', errors='ignore').decode('ascii')[:200]
                    logger.error(f"DEBUG: Message handling failed: {error_str}")
                except Exception:
                    logger.error("DEBUG: Message handling failed with encoding error")

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
