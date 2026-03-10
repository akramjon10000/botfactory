"""
Telegram HTTP SDK — lightweight classes for Telegram Bot API interaction.
Replaces python-telegram-bot private imports with custom HTTP-based implementation.
"""
import os
import json
import time
import logging
import asyncio
import requests
from collections import deque

logger = logging.getLogger(__name__)

# Flag to indicate telegram support is available
TELEGRAM_AVAILABLE = True

# Global deduplication for processed Telegram update IDs
PROCESSED_UPDATE_IDS = set()
_processed_queue = deque(maxlen=500)


def _mark_processed(update_id):
    if update_id in PROCESSED_UPDATE_IDS:
        return False
    PROCESSED_UPDATE_IDS.add(update_id)
    _processed_queue.append(update_id)
    if len(_processed_queue) == _processed_queue.maxlen:
        while len(PROCESSED_UPDATE_IDS) > _processed_queue.maxlen:
            try:
                PROCESSED_UPDATE_IDS.pop()
            except KeyError:
                break
    return True


# ---------------------------------------------------------------------------
# Lightweight data classes
# ---------------------------------------------------------------------------

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


class ContextTypes:
    DEFAULT_TYPE = "DefaultContext"


# ---------------------------------------------------------------------------
# HTTP Bot — low-level Telegram API wrapper
# ---------------------------------------------------------------------------

# Global reference so SimpleMessage.reply_text can reach the bot instance
bot_instance = None


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
            try:
                logger.error("Error getting updates occurred")
            except Exception:
                pass
            return {'ok': False, 'result': []}

    async def process_update(self, update_data):
        # ---- Inline helper classes that capture *self* (the bot) ---------
        _bot = self  # alias for closures

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
                    None, lambda: _bot.send_message(self.chat.id, text, reply_markup)
                )
                return result

            async def reply_photo(self, photo, caption=None):
                """Reply with photo via sendPhoto API"""
                url = f"{_bot.base_url}/sendPhoto"
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
                self.data = data.get('data', '')
                self.id = data.get('id', '')
                self.from_user = SimpleUser(data['from'])
                self.message = data.get('message', {})

            async def answer(self):
                """Answer callback query via answerCallbackQuery API"""
                url = f"{_bot.base_url}/answerCallbackQuery"
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
                url = f"{_bot.base_url}/editMessageText"
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

        # ---- Routing logic -----------------------------------------------
        update = SimpleUpdate(update_data)

        class SimpleContext:
            def __init__(self, text=None, bot=None):
                self.args = []
                self.bot = bot
                if text and text.startswith('/'):
                    parts = text.split()[1:]
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
                cmd = text.split()[0][1:]
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
                if 'message' in self.handlers:
                    for handler in self.handlers['message']:
                        await handler(update, context)

        # Handle callback queries
        if update.callback_query and 'callback' in self.handlers:
            context = SimpleContext()
            for handler in self.handlers['callback']:
                await handler(update, context)


# ---------------------------------------------------------------------------
# Application / polling wrapper
# ---------------------------------------------------------------------------

class TelegramApplication:
    def __init__(self, token):
        self.bot = TelegramHTTPBot(token)

    def add_handler(self, handler):
        self.bot.add_handler(handler)

    def run_polling(self):
        offset = None
        global bot_instance
        bot_instance = self.bot
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
                        try:
                            uid = update.get('update_id')
                        except Exception:
                            uid = None
                        if uid is not None and not _mark_processed(uid):
                            continue
                        asyncio.run(self.bot.process_update(update))
                        offset = update['update_id'] + 1

                time.sleep(1)

            except Exception as e:
                try:
                    error_safe = str(e).encode('ascii', errors='ignore').decode('ascii')
                    logger.error(f"Polling error: {error_safe}")
                except Exception:
                    logger.error("Polling error: encoding issue")
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


# ---------------------------------------------------------------------------
# Handler creator functions
# ---------------------------------------------------------------------------

def CommandHandler(command, func):
    return (command, func)

def MessageHandler(filters_obj, func):
    return ('message', func)

def CallbackQueryHandler(func):
    return ('callback', func)

def VoiceHandler(func):
    return ('voice', func)


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

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
