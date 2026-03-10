import os
import json
import logging
import requests
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from flask import Blueprint, request, jsonify, url_for
from flask_login import login_required, current_user
from app import db, app, csrf
from models import User, Bot, ChatHistory, BotCustomer
from ai import get_ai_response, process_knowledge_base
from audio_processor import download_and_process_audio
from rate_limiter import rate_limiter, get_client_ip

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

instagram_bp = Blueprint('instagram', __name__)

class InstagramBot:
    """Instagram bot integratsiyasi"""
    
    def __init__(self, access_token: str, bot_id: int):
        self.access_token = access_token
        self.bot_id = bot_id
        self.base_url = "https://graph.facebook.com/v18.0"
        self.verify_token = os.environ.get('INSTAGRAM_VERIFY_TOKEN', '')
    
    def send_message(self, recipient_id: str, message_text: str) -> bool:
        """Instagram Direct Message yuborish"""
        try:
            url = f"{self.base_url}/me/messages"
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'recipient': {'id': recipient_id},
                'message': {'text': message_text}
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                logger.info(f"Instagram message sent to {recipient_id}")
                return True
            else:
                logger.error(f"Instagram send error: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Instagram send message error: {str(e)}")
            return False

    def send_media_message(self, recipient_id: str, media_url: str, media_type: str = "image", caption: str = "") -> bool:
        """Instagram media xabar yuborish (rasm, video)"""
        try:
            url = f"{self.base_url}/me/messages"
            
            payload = {
                'recipient': {'id': recipient_id},
                'message': {
                    'attachment': {
                        'type': media_type,
                        'payload': {'url': media_url}
                    }
                },

            }
            
            if caption:
                payload['message']['text'] = caption
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                logger.info(f"Instagram media sent to {recipient_id}")
                return True
            else:
                logger.error(f"Instagram media error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Instagram media send error: {str(e)}")
            return False
    
    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Foydalanuvchi profilini olish"""
        try:
            url = f"{self.base_url}/{user_id}"
            params = {
                'fields': 'name,profile_pic',
                'access_token': self.access_token
            }
            
            response = requests.get(url, params=params, timeout=30)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Instagram profile error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"Instagram profile fetch error: {str(e)}")
            return None
    
    def send_quick_reply(self, recipient_id: str, message_text: str, quick_replies: List[Dict[str, str]]) -> bool:
        """Tez javob tugmalari bilan xabar yuborish"""
        try:
            url = f"{self.base_url}/me/messages"
            
            quick_replies_data = []
            for reply in quick_replies:
                quick_replies_data.append({
                    'content_type': 'text',
                    'title': reply['title'],
                    'payload': reply['payload']
                })
            
            payload = {
                'recipient': {'id': recipient_id},
                'message': {
                    'text': message_text,
                    'quick_replies': quick_replies_data
                },

            }
            
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }
            
            response = requests.post(url, headers=headers, json=payload, timeout=30)
            
            if response.status_code == 200:
                logger.info(f"Instagram quick reply sent to {recipient_id}")
                return True
            else:
                logger.error(f"Instagram quick reply error: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Instagram quick reply error: {str(e)}")
            return False
    
    def handle_message(self, sender_id: str, message_text: str) -> bool:
        """Instagram xabarini qayta ishlash"""
        try:
            with app.app_context():
                # Foydalanuvchini topish yoki yaratish
                user = User.query.filter_by(instagram_id=sender_id).first()
                if not user:
                    # Yangi Instagram foydalanuvchisi
                    user = User()
                    user.username = f"ig_{sender_id}"
                    user.email = f"ig_{sender_id}@instagram.bot"
                    user.password_hash = "instagram_user"
                    user.instagram_id = sender_id
                    user.language = 'uz'
                    user.subscription_type = 'free'
                    db.session.add(user)
                    db.session.commit()
                
                # Bot ma'lumotlarini olish
                bot = Bot.query.get(self.bot_id)
                if not bot:
                    return False
                
                # Obunani tekshirish
                if not user.subscription_active():
                    welcome_message = """🔒 Obunangiz tugagan!
                    
🌐 BotFactory.uz saytiga kirib, obunangizni yangilang.
💰 Tariflar: Basic (290,000 so'm) yoki Premium (590,000 so'm)"""
                    
                    self.send_message(sender_id, welcome_message)
                    return True
                
                # Track customer in BotCustomer for broadcasts
                try:
                    customer = BotCustomer.query.filter_by(
                        bot_id=self.bot_id,
                        platform='instagram',
                        platform_user_id=str(sender_id)
                    ).first()
                    if not customer:
                        customer = BotCustomer(
                            bot_id=self.bot_id,
                            platform='instagram',
                            platform_user_id=str(sender_id),
                            first_name='',
                            last_name='',
                            username=f"ig_{sender_id}",
                            language=user.language,
                            is_active=True,
                            message_count=1
                        )
                        db.session.add(customer)
                    else:
                        customer.last_interaction = datetime.utcnow()
                        customer.is_active = True
                        customer.message_count = (customer.message_count or 0) + 1
                    db.session.commit()
                except Exception as _:
                    try:
                        db.session.rollback()
                    except:
                        pass

                # AI javobini olish
                knowledge_base = process_knowledge_base(self.bot_id)
                
                owner_contact_info = ""
                if bot.owner:
                    owner_contact_info = f"Telefon raqam: {bot.owner.phone_number or 'Mavjud emas'}, Telegram: {bot.owner.telegram_id or 'Mavjud emas'}"

                ai_response = get_ai_response(
                    message=message_text,
                    bot_name=bot.name,
                    user_language=user.language,
                    knowledge_base=knowledge_base,
                    owner_contact_info=owner_contact_info
                )
                
                # Chat tarixini saqlash
                chat_history = ChatHistory()
                chat_history.bot_id = self.bot_id
                chat_history.user_instagram_id = sender_id
                chat_history.message = message_text
                chat_history.response = ai_response
                chat_history.language = user.language
                chat_history.created_at = datetime.utcnow()
                db.session.add(chat_history)
                db.session.commit()
                
                # Javobni yuborish
                if ai_response:
                    self.send_message(sender_id, ai_response)
                    
                    # Agar bepul foydalanuvchi bo'lsa, marketing xabar
                    if user.subscription_type == 'free':
                        marketing_message = """✨ Premium imkoniyatlar:
                        
🌍 3 tilda AI (O'zbek/Rus/Ingliz)
🤖 5 ta bot yaratish
📱 Barcha platformalar (Telegram/Instagram/WhatsApp)
                        
💎 Faqat 590,000 so'm/oy - BotFactory.uz"""
                        
                        self.send_quick_reply(
                            sender_id,
                            marketing_message,
                            [
                                {'title': '💎 Premium', 'payload': 'premium'},
                                {'title': '📞 Aloqa', 'payload': 'contact'}
                            ]
                        )
                else:
                    fallback_message = "Kechirasiz, hozir javob bera olmayapman. Keyinroq urinib ko'ring. 🤖"
                    self.send_message(sender_id, fallback_message)
                
                return True
                
        except Exception as e:
            logger.error(f"Instagram message handling error: {str(e)}")
            return False
    
    def handle_audio_message(self, sender_id: str, audio_attachment: Dict[str, Any]) -> bool:
        """Handle audio messages - convert to text and get AI response"""
        try:
            audio_url = audio_attachment.get('payload', {}).get('url')
            if not audio_url:
                logger.error("Audio URL not found in attachment")
                self.send_message(sender_id, "❌ Audio fayl URL topilmadi!")
                return False
            
            # Send processing message
            self.send_message(sender_id, "🎤 Ovozli xabaringizni qayta ishlamoqdaman...")
            
            with app.app_context():
                # Get user info
                db_user = User.query.filter_by(instagram_id=sender_id).first()
                if not db_user:
                    self.send_message(sender_id, "❌ Foydalanuvchi topilmadi! Bot bilan birinchi marta gaplashing.")
                    return False
                
                # Get bot info
                bot = Bot.query.get(self.bot_id)
                if not bot:
                    self.send_message(sender_id, "❌ Bot topilmadi!")
                    return False
                
                # Check subscription
                if not db_user.subscription_active():
                    self.send_message(sender_id, "❌ Obunangiz tugagan! Iltimos, obunani yangilang.")
                    return False
                
                # Process audio
                ai_response = download_and_process_audio(
                    audio_url=audio_url,
                    user_id=sender_id,
                    language=db_user.language,
                    file_extension='.m4a'  # Instagram audio format
                )
                
                # Extract the text part and AI response
                if "🎤 Sizning xabaringiz:" in ai_response:
                    parts = ai_response.split("\n\n", 1)
                    if len(parts) == 2:
                        user_text = parts[0].replace("🎤 Sizning xabaringiz: \"", "").replace("\"", "")
                        ai_text = parts[1]
                    else:
                        user_text = "Audio xabar"
                        ai_text = ai_response
                else:
                    user_text = "Audio xabar"
                    ai_text = ai_response
                
                # Save chat history
                chat_history = ChatHistory()
                chat_history.bot_id = self.bot_id
                chat_history.user_instagram_id = sender_id
                chat_history.message = f"[AUDIO] {user_text}"
                chat_history.response = ai_text
                chat_history.language = db_user.language
                chat_history.created_at = datetime.utcnow()
                db.session.add(chat_history)
                db.session.commit()
                
                # Send response
                self.send_message(sender_id, ai_response)
                
                logger.info(f"Instagram audio message processed for user {sender_id}")
                return True
                
        except Exception as e:
            logger.error(f"Instagram audio handling error: {str(e)}")
            self.send_message(sender_id, "❌ Ovozli xabarni qayta ishlashda xatolik yuz berdi!")
            return False
    
    def handle_postback(self, sender_id: str, payload: str) -> bool:
        """Instagram postback (tugma bosilgan) ni qayta ishlash"""
        try:
            if payload == 'GET_STARTED':
                welcome_message = f"""🎉 Instagram botiga xush kelibsiz!
                
🤖 Men sizga yordam berish uchun tayyor AI yordamchiman.
💬 Menga savolingizni yozing, men javob beraman!

🌐 Tilni o'zgartirish: /language
❓ Yordam: /help"""
                
                self.send_message(sender_id, welcome_message)
                
            elif payload == 'premium':
                premium_message = """💎 Premium tarif:
                
✅ 5 ta bot yaratish
✅ Barcha platformalar
✅ 3 til qo'llab-quvvatlash
✅ Prioritet yordam
                
💰 Narx: 590,000 so'm/oy
🌐 Obuna bo'lish: BotFactory.uz"""
                
                self.send_message(sender_id, premium_message)
                
            elif payload == 'contact':
                contact_message = """📞 Biz bilan bog'lanish:
                
🌐 Sayt: BotFactory.uz
📧 Email: support@botfactory.uz
📱 Telegram: @BotFactorySupport
🕒 Ish vaqti: 9:00-18:00"""
                
                self.send_message(sender_id, contact_message)
            
            return True
            
        except Exception as e:
            logger.error(f"Instagram postback error: {str(e)}")
            return False

# Instagram Bot Manager
class InstagramBotManager:
    """Instagram botlarni boshqarish"""
    
    def __init__(self):
        self.running_bots = {}
    
    def start_bot(self, bot_id: int, access_token: str) -> bool:
        """Instagram botni ishga tushirish"""
        try:
            if bot_id not in self.running_bots:
                bot = InstagramBot(access_token, bot_id)
                self.running_bots[bot_id] = bot
                logger.info(f"Instagram bot {bot_id} started")
                return True
            return True
        except Exception as e:
            logger.error(f"Instagram bot start error: {str(e)}")
            return False
    
    def stop_bot(self, bot_id: int) -> bool:
        """Instagram botni to'xtatish"""
        try:
            if bot_id in self.running_bots:
                del self.running_bots[bot_id]
                logger.info(f"Instagram bot {bot_id} stopped")
            return True
        except Exception as e:
            logger.error(f"Instagram bot stop error: {str(e)}")
            return False
    
    def get_bot(self, bot_id: int) -> Optional['InstagramBot']:
        """Instagram botni olish"""
        return self.running_bots.get(bot_id)

# Global Instagram bot manager
instagram_manager = InstagramBotManager()

# Flask routes
@instagram_bp.route('/webhook/<int:bot_id>', methods=['GET', 'POST'])
@csrf.exempt
def instagram_webhook(bot_id):
    """Instagram webhook endpoint"""
    try:
        if request.method == 'GET':
            # Webhook verification
            verify_token = request.args.get('hub.verify_token')
            challenge = request.args.get('hub.challenge')
            
            bot = instagram_manager.get_bot(bot_id)
            if bot and verify_token == bot.verify_token:
                return str(challenge)
            else:
                return 'Verification failed', 403
        
        elif request.method == 'POST':
            client_ip = get_client_ip(request)
            allowed, retry_after = rate_limiter.is_allowed(
                key=f"instagram_webhook:{bot_id}:{client_ip}",
                limit=180,
                window_seconds=60
            )
            if not allowed:
                return jsonify({'error': 'Rate limited', 'retry_after': retry_after}), 429

            # Message processing
            data = request.get_json()
            
            if data and 'entry' in data:
                for entry in data['entry']:
                    if 'messaging' in entry:
                        for messaging_event in entry['messaging']:
                            sender_id = messaging_event['sender']['id']
                            
                            bot = instagram_manager.get_bot(bot_id)
                            if not bot:
                                continue
                            
                            if 'message' in messaging_event:
                                message_text = messaging_event['message'].get('text', '')
                                if message_text:
                                    bot.handle_message(sender_id, message_text)
                            
                            elif 'postback' in messaging_event:
                                payload = messaging_event['postback'].get('payload', '')
                                bot.handle_postback(sender_id, payload)
            
            return 'OK', 200
    
    except Exception as e:
        logger.error(f"Instagram webhook error: {str(e)}")
        return 'Internal Server Error', 500

@instagram_bp.route('/start/<int:bot_id>', methods=['POST'])
@csrf.exempt
@login_required
def start_instagram_bot(bot_id):
    """Instagram botni ishga tushirish"""
    try:
        bot = Bot.query.get_or_404(bot_id)

        if bot.user_id != current_user.id and not current_user.is_admin:
            return jsonify({'success': False, 'error': "Ruxsat yo'q"}), 403

        if not bot.instagram_token:
            return jsonify({'success': False, 'error': 'Instagram token topilmadi'})

        success = instagram_manager.start_bot(bot_id, bot.instagram_token)

        if success:
            bot.is_active = True
            db.session.commit()
            return jsonify({'success': True, 'message': 'Instagram bot ishga tushdi'})
        else:
            return jsonify({'success': False, 'error': 'Botni ishga tushirishda xato'})
    
    except Exception as e:
        logger.error(f"Start Instagram bot error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@instagram_bp.route('/stop/<int:bot_id>', methods=['POST'])
@csrf.exempt
@login_required
def stop_instagram_bot(bot_id):
    """Instagram botni to'xtatish"""
    try:
        bot = Bot.query.get_or_404(bot_id)

        if bot.user_id != current_user.id and not current_user.is_admin:
            return jsonify({'success': False, 'error': "Ruxsat yo'q"}), 403

        success = instagram_manager.stop_bot(bot_id)

        if success:
            bot.is_active = False
            db.session.commit()
            return jsonify({'success': True, 'message': 'Instagram bot to\'xtatildi'})
        else:
            return jsonify({'success': False, 'error': 'Botni to\'xtatishda xato'})
    
    except Exception as e:
        logger.error(f"Stop Instagram bot error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@instagram_bp.route('/status/<int:bot_id>')
@login_required
def instagram_bot_status(bot_id):
    """Instagram bot holatini tekshirish"""
    try:
        is_running = bot_id in instagram_manager.running_bots

        bot = Bot.query.get_or_404(bot_id)
        if bot.user_id != current_user.id and not current_user.is_admin:
            return jsonify({'error': "Ruxsat yo'q"}), 403

        return jsonify({
            'bot_id': bot_id,
            'is_running': is_running,
            'is_active': bot.is_active if bot else False,
            'platform': 'Instagram'
        })
    
    except Exception as e:
        logger.error(f"Instagram status error: {str(e)}")
        return jsonify({'error': str(e)}), 500

def start_instagram_bot_automatically(bot_id: int, access_token: str) -> bool:
    """Instagram botni avtomatik ishga tushirish funksiyasi"""
    try:
        with app.app_context():
            bot = Bot.query.get(bot_id)
            if not bot:
                logger.error(f"Bot {bot_id} topilmadi")
                return False
            
            # Instagram bot tokenini saqlash
            bot.instagram_token = access_token
            db.session.commit()
            
            # Instagram botni ishga tushirish
            success = instagram_manager.start_bot(bot_id, access_token)
            
            if success:
                bot.is_active = True
                db.session.commit()
                logger.info(f"Instagram bot {bot_id} avtomatik ishga tushdi")
                return True
            else:
                logger.error(f"Instagram bot {bot_id} ishga tushirishda xato")
                return False
                
    except Exception as e:
        logger.error(f"Instagram bot avtomatik ishga tushirishda xato: {str(e)}")
        return False
