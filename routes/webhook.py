"""Webhook and messaging routes"""
import os
import json
import logging
from datetime import datetime
from flask import Blueprint, request, redirect, url_for, flash, jsonify, render_template
from flask_login import login_required, current_user
from app import db
from models import Bot, BotCustomer, BotMessage
from rate_limiter import rate_limiter, get_client_ip
import requests

webhook_bp = Blueprint('webhook', __name__)


@webhook_bp.route('/webhook/telegram/<int:bot_id>', methods=['POST'])
def telegram_webhook(bot_id):
    """Telegram webhook endpoint for production"""
    try:
        webhook_secret = (os.environ.get('TELEGRAM_WEBHOOK_SECRET') or '').strip()
        if webhook_secret:
            provided_secret = (request.headers.get('X-Telegram-Bot-Api-Secret-Token') or '').strip()
            if provided_secret != webhook_secret:
                return jsonify({'error': 'Invalid webhook secret'}), 403

        client_ip = get_client_ip(request)
        allowed, retry_after = rate_limiter.is_allowed(
            key=f"telegram_webhook:{bot_id}:{client_ip}",
            limit=240,
            window_seconds=60
        )
        if not allowed:
            return jsonify({'error': 'Rate limited', 'retry_after': retry_after}), 429

        # Bot mavjudligini tekshirish
        bot = Bot.query.get_or_404(bot_id)
        
        # Webhook ma'lumotlarini olish
        update_data = request.get_json()
        
        if not update_data:
            return jsonify({'error': 'No data received'}), 400
            
        # Telegram bot instance yaratish va update ni qayta ishlash
        from telegram_bot import process_webhook_update
        result = process_webhook_update(bot_id, bot.telegram_token, update_data)
        
        if result:
            return jsonify({'status': 'ok'}), 200
        else:
            return jsonify({'error': 'Processing failed'}), 500
            
    except Exception as e:
        logging.error(f"Webhook error for bot {bot_id}: {str(e)}")
        return jsonify({'error': 'Internal error'}), 500


@webhook_bp.route('/bot/<int:bot_id>/setup_webhook', methods=['POST'])
@login_required
def setup_webhook(bot_id):
    """Webhook ni o'rnatish"""
    try:
        bot = Bot.query.get_or_404(bot_id)
        
        # Foydalanuvchi huquqini tekshirish
        if bot.user_id != current_user.id and not current_user.is_admin:
            flash('Sizda bu botga ruxsat yo\'q!', 'error')
            return redirect(url_for('main.dashboard'))
            
        if not bot.telegram_token:
            flash('Avval Telegram token ni kiriting!', 'error')
            return redirect(url_for('bot.edit_bot', bot_id=bot_id))
            
        # Domain ni aniqlash
        webhook_url = get_webhook_url(bot_id)
        
        # Telegram API orqali webhook o'rnatish
        success = set_telegram_webhook(bot.telegram_token, webhook_url)
        
        if success:
            flash('✅ Webhook muvaffaqiyatli o\'rnatildi!', 'success')
            bot.is_active = True
            db.session.commit()
        else:
            flash('❌ Webhook o\'rnatishda xatolik yuz berdi!', 'error')
            
    except Exception as e:
        flash(f'Xatolik: {str(e)}', 'error')
        
    return redirect(url_for('bot.edit_bot', bot_id=bot_id))


def get_webhook_url(bot_id):
    """Webhook URL ni aniqlash"""
    if os.environ.get('RENDER') or 'render' in request.headers.get('Host', '').lower():
        return f"https://botfactory-am64.onrender.com/webhook/telegram/{bot_id}"
    elif request.headers.get('Host'):
        host = request.headers.get('Host')
        scheme = 'https' if request.headers.get('X-Forwarded-Proto') == 'https' else 'http'
        return f"{scheme}://{host}/webhook/telegram/{bot_id}"
    else:
        return f"https://botfactory-am64.onrender.com/webhook/telegram/{bot_id}"


def set_telegram_webhook(bot_token, webhook_url):
    """Telegram API orqali webhook o'rnatish"""
    try:
        api_url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
        payload = {
            'url': webhook_url,
            'max_connections': 40,
            'allowed_updates': ['message', 'callback_query']
        }
        
        response = requests.post(api_url, json=payload)
        result = response.json()
        
        if result.get('ok'):
            logging.info(f"Webhook set successfully: {webhook_url}")
            return True
        else:
            logging.error(f"Webhook setup failed: {result.get('description', 'Unknown error')}")
            return False
            
    except Exception as e:
        logging.error(f"Webhook setup error: {str(e)}")
        return False


# === Bot Messaging Routes ===

@webhook_bp.route('/bot/<int:bot_id>/messaging')
@login_required
def bot_messaging(bot_id):
    """Bot mijozlari va xabar yuborish interfeysi"""
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu botning xabarlariga kirish huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    # Bot mijozlarini olish
    customers = BotCustomer.query.filter_by(bot_id=bot_id, is_active=True).order_by(BotCustomer.last_interaction.desc()).all()
    
    # Xabar tarixi
    recent_messages = BotMessage.query.filter_by(bot_id=bot_id).order_by(BotMessage.created_at.desc()).limit(10).all()
    
    return render_template('bot_messaging.html', bot=bot, customers=customers, recent_messages=recent_messages)


@webhook_bp.route('/bot/<int:bot_id>/send_message', methods=['POST'])
@login_required
def send_bot_message(bot_id):
    """Bot orqali mijozlarga xabar yuborish"""
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu bot orqali xabar yuborish huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    message_text = request.form.get('message_text', '').strip()
    message_type = request.form.get('message_type', 'individual')
    selected_customers = request.form.getlist('selected_customers')
    
    if not message_text:
        flash('Xabar matni kiritilishi shart!', 'error')
        return redirect(url_for('webhook.bot_messaging', bot_id=bot_id))
    
    # Xabar ob'ektini yaratish
    bot_message = BotMessage()
    bot_message.bot_id = bot_id
    bot_message.sender_id = current_user.id
    bot_message.message_text = message_text
    bot_message.message_type = message_type
    
    if message_type == 'broadcast':
        target_customers = BotCustomer.query.filter_by(bot_id=bot_id, is_active=True).all()
    else:
        if not selected_customers:
            flash('Kamida bitta mijoz tanlanishi kerak!', 'error')
            return redirect(url_for('webhook.bot_messaging', bot_id=bot_id))
        target_customers = BotCustomer.query.filter(
            BotCustomer.id.in_(selected_customers),
            BotCustomer.bot_id == bot_id
        ).all()
    
    bot_message.target_customers = json.dumps([str(c.id) for c in target_customers])
    bot_message.status = 'sending'
    
    db.session.add(bot_message)
    db.session.commit()
    
    # Xabarlarni yuborish
    try:
        success_count = 0
        for customer in target_customers:
            try:
                platform = (customer.platform or '').lower()
                target_id = str(customer.platform_user_id or '').strip()
                if not target_id:
                    continue
                if platform == 'telegram' and bot.telegram_token:
                    result = send_telegram_message_sync(bot.telegram_token, target_id, message_text)
                    if result:
                        success_count += 1
                elif platform == 'whatsapp' and bot.whatsapp_token and bot.whatsapp_phone_id:
                    try:
                        from whatsapp_bot import WhatsAppBot
                        wa = WhatsAppBot(bot.whatsapp_token, bot.whatsapp_phone_id, bot.id)
                        if wa.send_message(target_id, message_text):
                            success_count += 1
                    except Exception as e:
                        logging.error(f"WhatsApp send error for customer {customer.id}: {e}")
                elif platform == 'instagram' and bot.instagram_token:
                    try:
                        from instagram_bot import InstagramBot
                        ig = InstagramBot(bot.instagram_token, bot.id)
                        if ig.send_message(target_id, message_text):
                            success_count += 1
                    except Exception as e:
                        logging.error(f"Instagram send error for customer {customer.id}: {e}")
                else:
                    logging.warning(f"Unsupported or misconfigured platform for customer {customer.id}: {platform}")
            except Exception as e:
                logging.error(f"Error sending message to customer {customer.id}: {str(e)}")
        
        # Natijalarni yangilash
        bot_message.sent_count = success_count
        bot_message.status = 'completed' if success_count > 0 else 'failed'
        bot_message.sent_at = datetime.utcnow()
        db.session.commit()
        
        if success_count > 0:
            flash(f'Xabar {success_count} ta mijozga muvaffaqiyatli yuborildi!', 'success')
        else:
            flash('Xabar yuborishda muammo yuz berdi!', 'error')
            
    except Exception as e:
        logging.error(f"Message sending error: {str(e)}")
        bot_message.status = 'failed'
        db.session.commit()
        flash('Xabar yuborishda xatolik yuz berdi!', 'error')
    
    return redirect(url_for('webhook.bot_messaging', bot_id=bot_id))


@webhook_bp.route('/bot/<int:bot_id>/customers')
@login_required
def bot_customers(bot_id):
    """Bot mijozlar ro'yxati (JSON format)"""
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    
    customers = BotCustomer.query.filter_by(bot_id=bot_id, is_active=True).all()
    
    customer_data = []
    for customer in customers:
        customer_data.append({
            'id': customer.id,
            'display_name': customer.display_name,
            'platform': customer.platform,
            'language': customer.language,
            'last_interaction': customer.last_interaction.strftime('%Y-%m-%d %H:%M'),
            'message_count': customer.message_count
        })
    
    return jsonify({'customers': customer_data})


def send_telegram_message_sync(bot_token, chat_id, message_text):
    """Telegram xabarini sinxron yuborish"""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        data = {
            'chat_id': chat_id,
            'text': message_text,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, json=data, timeout=30)
        result = response.json()
        
        return result.get('ok', False)
    except Exception as e:
        logging.error(f"Error sending telegram message: {str(e)}")
        return False
