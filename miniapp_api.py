"""
Mini App API Blueprint
Provides API endpoints for Telegram Mini Web App
"""

from flask import Blueprint, jsonify, request
from flask_login import current_user
import logging
import json
from datetime import datetime

miniapp_bp = Blueprint('miniapp', __name__)
logger = logging.getLogger(__name__)


@miniapp_bp.route('/')
def miniapp_index():
    """Serve the MiniApp index.html file directly to bypass static routing issues"""
    from flask import send_from_directory, current_app, make_response
    import os
    miniapp_dir = os.path.join(current_app.root_path, 'static', 'miniapp')
    response = make_response(send_from_directory(miniapp_dir, 'index.html'))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response


@miniapp_bp.route('/business/<int:bot_id>')
def get_business_info(bot_id):
    """Get business information for a bot"""
    try:
        from models import Bot
        bot = Bot.query.get(bot_id)
        
        if not bot:
            return jsonify({'error': 'Bot topilmadi'}), 404
            
        owner_sub = (bot.owner.subscription_type or 'free').lower().strip()
        if owner_sub not in ['premium', 'admin']:
            return jsonify({'error': 'Ushbu xususiyat faqat Premium ta\'rifida mavjud'}), 403
        
        return jsonify({
            'id': bot.id,
            'name': bot.name,
            'description': bot.business_description or bot.description or '',
            'logo': bot.business_logo or '/static/images/default-logo.png',
            'business_type': bot.business_type or 'product',
            'owner_name': bot.owner.username if bot.owner else '',
            'theme': {
                'accent': getattr(bot, 'miniapp_theme_color', '#00d4aa') or '#00d4aa',
                'bg': getattr(bot, 'miniapp_bg_color', '#0f0f0f') or '#0f0f0f',
                'card': getattr(bot, 'miniapp_card_color', '#252525') or '#252525'
            },
            'welcome_text': getattr(bot, 'miniapp_welcome_text', '') or '',
            'currency': getattr(bot, 'miniapp_currency', "so'm") or "so'm"
        })
        
    except Exception as e:
        logger.error(f"Error getting business info: {e}")
        return jsonify({'error': 'Server xatosi'}), 500


@miniapp_bp.route('/catalog/<int:bot_id>')
def get_catalog(bot_id):
    """Get products/services catalog for a bot"""
    try:
        from models import KnowledgeBase, Bot
        
        bot = Bot.query.get(bot_id)
        if not bot:
            return jsonify([])
            
        owner_sub = (bot.owner.subscription_type or 'free').lower().strip()
        if owner_sub not in ['premium', 'admin']:
            return jsonify({'error': 'Premium yoziluvi talab qilinadi'}), 403
        
        # Get all product entries from knowledge base
        products = KnowledgeBase.query.filter_by(
            bot_id=bot_id,
            content_type='product'
        ).all()
        
        catalog = []
        for product in products:
            # Parse product content
            item = parse_product_content(product.content, product.id, product.source_name)
            if item:
                catalog.append(item)
        
        return jsonify(catalog)
        
    except Exception as e:
        logger.error(f"Error getting catalog: {e}")
        return jsonify([])


@miniapp_bp.route('/contact/<int:bot_id>')
def get_contact_info(bot_id):
    """Get contact information for a bot"""
    try:
        from models import Bot, KnowledgeBase
        import os
        import re
        
        bot = Bot.query.get(bot_id)
        
        if not bot:
            return jsonify({'error': 'Bot topilmadi'}), 404
        
        # Default fallback variables
        phone = ''
        telegram = ''
        address = "Ko'rsatilmagan"
        working_hours = '09:00 - 18:00'
        
        # 1. First priority: Check custom Contact Info from KnowledgeBase ("Aloqa" tab)
        kb_contact = KnowledgeBase.query.filter_by(
            bot_id=bot_id, 
            content_type='contact'
        ).order_by(KnowledgeBase.created_at.desc()).first()
        
        if kb_contact and kb_contact.content:
            content = kb_contact.content
            # Extract Phone
            phone_match = re.search(r'Telefon:\s*(.+)', content)
            if phone_match:
                phone = phone_match.group(1).strip()
            
            # Extract Address
            addr_match = re.search(r'Manzil/Lokatsiya:\s*(.+)', content)
            if addr_match:
                address = addr_match.group(1).strip()
                
            # Extract working hours
            hours_match = re.search(r'Ish vaqti:\s*(.+)', content)
            if hours_match:
                working_hours = hours_match.group(1).strip()
                
            # Extract Socials (we'll map to Telegram string)
            social_match = re.search(r'Ijtimoiy tarmoqlar:\s*(.+)', content)
            if social_match:
                telegram = social_match.group(1).strip()
        
        # 2. Second priority: Fallback to bot owner settings
        if not phone and bot.owner:
            phone = bot.owner.phone_number or ''
            
        if not telegram and bot.owner:
            telegram = bot.owner.telegram_id or ''
            
        if hasattr(bot, 'working_hours') and bot.working_hours and working_hours == '09:00 - 18:00':
            working_hours = bot.working_hours
        
        # 3. No system defaults - each bot owner should set their own contact info
        # phone and telegram remain empty if not configured by bot owner
        
        return jsonify({
            'phone': phone,
            'address': address,
            'working_hours': working_hours,
            'telegram': telegram
        })
        
    except Exception as e:
        logger.error(f"Error getting contact info: {e}")
        return jsonify({
            'phone': '',
            'address': 'Ko\'rsatilmagan',
            'working_hours': '09:00 - 18:00'
        })


@miniapp_bp.route('/order', methods=['POST'])
def create_order():
    """Create a new order from Mini App"""
    try:
        from models import MiniAppOrder
        from app import db
        
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Ma\'lumotlar topilmadi'}), 400
        
        # Validate required fields
        required = ['bot_id', 'customer_name', 'customer_phone', 'items']
        for field in required:
            if not data.get(field):
                return jsonify({'error': f'{field} majburiy'}), 400
        
        # Create order
        order = MiniAppOrder()
        order.bot_id = data['bot_id']
        order.customer_name = data['customer_name']
        order.customer_phone = data['customer_phone']
        order.customer_address = data.get('customer_address', '')
        
        note_text = data.get('note', '')
        booking_datetime = data.get('booking_datetime')
        if booking_datetime:
            try:
                dt_obj = datetime.strptime(booking_datetime, '%Y-%m-%dT%H:%M')
                formatted_dt = dt_obj.strftime('%d.%m.%Y %H:%M')
                order.note = f"Sana va vaqt: {formatted_dt}\n{note_text}".strip()
            except Exception:
                order.note = f"Sana va vaqt: {booking_datetime}\n{note_text}".strip()
        else:
            order.note = note_text
            
        order.items = json.dumps(data['items'], ensure_ascii=False)
        order.total_amount = data.get('total', 0)
        order.telegram_user_id = data.get('telegram_user_id')
        order.status = 'pending'
        order.created_at = datetime.utcnow()
        
        db.session.add(order)
        db.session.commit()
        
        # Send notification to bot owner
        try:
            notify_order_to_owner(order)
        except Exception as notify_error:
            logger.error(f"Failed to notify owner: {notify_error}")
        
        logger.info(f"New order created: #{order.id} for bot {order.bot_id}")
        
        return jsonify({
            'success': True,
            'order_id': order.id,
            'message': 'Buyurtma qabul qilindi'
        })
        
    except Exception as e:
        logger.error(f"Error creating order: {e}")
        return jsonify({'error': 'Buyurtma yaratishda xatolik'}), 500


def parse_product_content(content, product_id, source_name):
    """Parse product content from knowledge base format"""
    try:
        lines = content.split('\n')
        
        name = source_name or 'Mahsulot'
        price = 0
        description = ''
        image = ''
        
        for line in lines:
            line = line.strip()
            if line.startswith('Mahsulot:'):
                name = line.replace('Mahsulot:', '').strip()
            elif line.startswith('Narx:'):
                price_str = line.replace('Narx:', '').strip()
                # Extract number from price string
                price_num = ''.join(c for c in price_str if c.isdigit())
                if price_num:
                    price = int(price_num)
            elif line.startswith('Tavsif:'):
                description = line.replace('Tavsif:', '').strip()
            elif line.startswith('Rasm:'):
                image = line.replace('Rasm:', '').strip()
        
        return {
            'id': product_id,
            'name': name,
            'price': price,
            'description': description,
            'image': image or '/static/images/placeholder.png'
        }
        
    except Exception as e:
        logger.error(f"Error parsing product: {e}")
        return None


def notify_order_to_owner(order):
    """Send Telegram notification to bot owner about new order"""
    try:
        from models import Bot
        import requests
        import os
        
        bot = Bot.query.get(order.bot_id)
        if not bot or not bot.telegram_token:
            return
        
        # Get admin chat ID
        admin_chat_id = None
        if bot.owner and hasattr(bot.owner, 'telegram_id') and bot.owner.telegram_id:
            admin_chat_id = bot.owner.telegram_id
        
        if not admin_chat_id:
            admin_chat_id = os.environ.get('ADMIN_TELEGRAM_ID')
        
        if not admin_chat_id:
            return
        
        # Parse items
        items = json.loads(order.items)
        items_lines = []
        for item in items:
            items_lines.append(f"• {item['name']} x{item['quantity']} - {item['price']:,} so'm")
        items_text = '\n'.join(items_lines)
        
        # Build message parts
        address_text = order.customer_address if order.customer_address else "Ko'rsatilmagan"
        note_text = order.note if order.note else "-"
        
        message = f"""🛒 Yangi buyurtma #{order.id}

👤 Mijoz: {order.customer_name}
📞 Telefon: {order.customer_phone}
📍 Manzil: {address_text}

📦 Buyurtma:
{items_text}

💰 Jami: {order.total_amount:,} so'm

📝 Izoh: {note_text}
"""
        
        # Send via Telegram API
        url = f"https://api.telegram.org/bot{bot.telegram_token}/sendMessage"
        requests.post(url, json={
            'chat_id': admin_chat_id,
            'text': message
        })
        
    except Exception as e:
        logger.error(f"Error notifying owner: {e}")


def _forward_chat_to_admin(bot, user_msg, ai_reply, msg_type="text"):
    """Forward MiniApp chat messages to bot owner via Telegram for monitoring"""
    try:
        import requests as req
        import os

        if not bot or not bot.telegram_token:
            return

        admin_chat_id = None
        if bot.owner and hasattr(bot.owner, 'telegram_id') and bot.owner.telegram_id:
            admin_chat_id = bot.owner.telegram_id
        if not admin_chat_id:
            admin_chat_id = os.environ.get('ADMIN_TELEGRAM_ID')
        if not admin_chat_id:
            return

        icon = "🎤" if msg_type == "voice" else "💬"
        message = f"""{icon} MiniApp Chat | {bot.name}

👤 Mijoz: {user_msg[:200]}
🤖 AI: {ai_reply[:300]}"""

        url = f"https://api.telegram.org/bot{bot.telegram_token}/sendMessage"
        req.post(url, json={'chat_id': admin_chat_id, 'text': message}, timeout=5)
    except Exception as e:
        logger.error(f"Error forwarding chat to admin: {e}")


@miniapp_bp.route('/chat', methods=['POST'])
def miniapp_chat():
    """MiniApp text chat endpoint — uses appropriate AI model based on subscription"""
    try:
        from models import Bot
        from ai import get_ai_response, process_knowledge_base

        data = request.get_json(silent=True) or {}
        bot_id = data.get('bot_id') or request.args.get('bot_id')
        message = (data.get('message') or '').strip()

        if not bot_id or not message:
            return jsonify({'error': 'bot_id va message kerak'}), 400

        bot = Bot.query.get(int(bot_id))
        if not bot:
            return jsonify({'error': 'Bot topilmadi'}), 404

        # Get owner subscription tier
        owner_sub = 'free'
        if bot.owner:
            owner_sub = (bot.owner.subscription_type or 'free').strip().lower()

        # Build knowledge base context
        kb_text = ''
        try:
            kb_text = process_knowledge_base(bot.id) or ''
        except Exception:
            pass

        # Get AI response with subscription-aware model
        reply = get_ai_response(
            message=message,
            bot_name=bot.name or 'AI Assistant',
            user_language='uz',
            knowledge_base=kb_text,
            chat_history='',
            owner_contact_info='',
            subscription_tier=owner_sub
        )
        reply = reply or 'Kechirasiz, hozir javob bera olmayapman.'

        # Forward to admin for monitoring
        try:
            _forward_chat_to_admin(bot, message, reply, "text")
        except Exception:
            pass

        return jsonify({
            'success': True,
            'reply': reply,
            'is_premium': owner_sub in ('premium', 'admin')
        })

    except Exception as e:
        logger.error(f"MiniApp chat error: {e}")
        return jsonify({'error': 'Chat xatolik yuz berdi'}), 500


@miniapp_bp.route('/voice-chat', methods=['POST'])
def miniapp_voice_chat():
    """MiniApp voice chat endpoint — Premium only, uses Gemini Native Audio via new google-genai SDK"""
    try:
        from models import Bot
        from ai import get_ai_response, process_knowledge_base
        import tempfile
        import os
        import base64
        from google import genai

        bot_id = request.args.get('bot_id') or request.form.get('bot_id')
        if not bot_id:
            return jsonify({'error': 'bot_id kerak'}), 400

        bot = Bot.query.get(int(bot_id))
        if not bot:
            return jsonify({'error': 'Bot topilmadi'}), 404

        # Check Premium subscription
        owner_sub = 'free'
        if bot.owner:
            owner_sub = (bot.owner.subscription_type or 'free').strip().lower()

        if owner_sub not in ('premium', 'admin'):
            return jsonify({
                'error': 'premium_required',
                'message': 'Ovozli chat faqat Premium obunachilarga mavjud!'
            }), 403

        # Get audio file
        audio_file = request.files.get('audio')
        if not audio_file:
            return jsonify({'error': 'Audio fayl kerak'}), 400

        # Save to temp file
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as tmp:
                audio_file.save(tmp)
                temp_path = tmp.name

            # Configure new google-genai client
            api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GOOGLE_API_KEY2')
            if not api_key:
                return jsonify({'error': 'API kalit topilmadi'}), 500

            client = genai.Client(api_key=api_key)

            # Upload audio file using new SDK
            uploaded_audio = client.files.upload(file=temp_path)

            # Transcribe using native audio model (with fallback)
            transcribe_prompt = """Bu audio xabardagi nutqni aniq matn shaklida yoz.
Faqat gapirilgan so'zlarni yoz, boshqa hech narsa qo'shma."""

            audio_models = [
                'gemini-2.5-flash-preview-native-audio',
                'gemini-3.1-flash-lite-preview',
            ]
            user_text = ''
            for audio_model in audio_models:
                try:
                    transcribe_response = client.models.generate_content(
                        model=audio_model,
                        contents=[transcribe_prompt, uploaded_audio]
                    )
                    if transcribe_response and transcribe_response.text:
                        user_text = transcribe_response.text.strip()
                        logger.info(f"Voice transcription success with model: {audio_model}")
                        break
                except Exception as model_err:
                    logger.warning(f"Voice model {audio_model} failed: {model_err}")
                    continue

            # Build knowledge and get AI text reply
            kb_text = ''
            try:
                kb_text = process_knowledge_base(bot.id) or ''
            except Exception:
                pass

            reply_text = get_ai_response(
                message=user_text or 'Ovozli xabar yuborildi',
                bot_name=bot.name or 'AI Assistant',
                user_language='uz',
                knowledge_base=kb_text,
                chat_history='',
                owner_contact_info='',
                subscription_tier=owner_sub
            )
            reply_text = reply_text or 'Kechirasiz, tushunmadim.'

            # Try to generate audio response using native audio model (TTS)
            audio_response_b64 = None
            try:
                tts_response = client.models.generate_content(
                    model='gemini-2.5-flash-preview-native-audio',
                    contents=f"Bu matnni ovozga o'gir (o'zbek tilida natural ovozda o'qi): {reply_text[:500]}"
                )
                # Check if response contains audio data
                if hasattr(tts_response, 'candidates') and tts_response.candidates:
                    for part in tts_response.candidates[0].content.parts:
                        if hasattr(part, 'inline_data') and part.inline_data:
                            audio_response_b64 = base64.b64encode(part.inline_data.data).decode('utf-8')
                            break
            except Exception as tts_err:
                logger.warning(f"TTS generation failed, returning text only: {tts_err}")

            # Cleanup uploaded file
            try:
                client.files.delete(name=uploaded_audio.name)
            except Exception:
                pass

            # Forward to admin
            try:
                _forward_chat_to_admin(bot, user_text or '[ovozli xabar]', reply_text, "voice")
            except Exception:
                pass

            return jsonify({
                'success': True,
                'user_text': user_text,
                'reply': reply_text,
                'audio_response': audio_response_b64,
                'is_premium': True
            })

        finally:
            if temp_path and os.path.exists(temp_path):
                os.unlink(temp_path)

    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        logger.error(f"MiniApp voice chat error: {e}\nTraceback: {error_details}")
        return jsonify({
            'error': 'Ovozli chat xatolik yuz berdi',
            'details': str(e)
        }), 500
