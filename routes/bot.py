"""Bot CRUD routes"""
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app import db
from bot_manager import bot_manager
from models import Bot, KnowledgeBase
import cloudinary.uploader
from routes.templates_data import TEMPLATES

bot_bp = Blueprint('bot', __name__)


@bot_bp.route('/bot/create', methods=['GET', 'POST'])
@login_required
def create_bot():
    if not current_user.can_create_bot():
        flash('Siz maksimal bot soni yaratdingiz!', 'error')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        platform = request.form.get('platform', 'Telegram')
        telegram_token = request.form.get('telegram_token')
        instagram_token = request.form.get('instagram_token')
        whatsapp_token = request.form.get('whatsapp_token')
        whatsapp_phone_id = request.form.get('whatsapp_phone_id')
        
        if not name:
            flash('Bot nomi kiritilishi shart!', 'error')
            return render_template('bot_create.html')
        
        bot = Bot()
        bot.user_id = current_user.id
        bot.name = name
        bot.platform = platform
        bot.telegram_token = telegram_token
        bot.instagram_token = instagram_token
        bot.whatsapp_token = whatsapp_token
        bot.whatsapp_phone_id = whatsapp_phone_id
        
        template_id = request.form.get('template_id', 'none')
        
        # Suhbat kuzatuvi sozlamalarini saqlash
        admin_chat_id = request.form.get('admin_chat_id')
        notification_channel = request.form.get('notification_channel')
        notifications_enabled = bool(request.form.get('notifications_enabled'))
        
        if admin_chat_id:
            current_user.admin_chat_id = admin_chat_id.strip()
        if notification_channel:
            current_user.notification_channel = notification_channel.strip()
        current_user.notifications_enabled = notifications_enabled
        
        db.session.add(bot)
        db.session.flush() # Boting ID sini olish uchun flush qilamiz
        
        # Add template data if selected
        if template_id and template_id in TEMPLATES and template_id != 'none':
            for entry in TEMPLATES[template_id]['entries']:
                kb = KnowledgeBase(
                    bot_id=bot.id,
                    content_type=entry['type'],
                    source_name=entry['source'],
                    content=entry['content']
                )
                db.session.add(kb)
        
        db.session.commit()
        
        # Yangi bot haqida adminga xabar berish
        try:
            from telegram_bot import send_admin_message_to_user
            from models import User
            admin_users = User.query.filter_by(is_admin=True, is_active=True).all()
            for admin in admin_users:
                if admin.telegram_id:
                    text = f"🤖 <b>Yangi bot yaratildi!</b>\n\n"
                    text += f"👤 <b>Egasi:</b> @{current_user.username}\n"
                    text += f"🤖 <b>Bot nomi:</b> {name}\n"
                    text += f"📱 <b>Platforma:</b> {platform}"
                    send_admin_message_to_user(admin.telegram_id, text)
        except Exception as notify_error:
            logging.error(f"Failed to send admin notification for new bot: {notify_error}")
        
        # Platform uchun avtomatik ishga tushirish (central manager)
        if platform == 'Telegram' and telegram_token:
            try:
                bot_manager.start_bot_polling(bot)
                bot.is_active = True
                db.session.commit()
                flash('Telegram bot muvaffaqiyatli yaratildi va ishga tushirildi!', 'success')
            except Exception as e:
                logging.error(f"Telegram botni ishga tushirishda xato: {e}")
                flash('Bot yaratildi, lekin token noto\'g\'ri yoki ishga tushirishda muammo!', 'warning')
        elif platform == 'Instagram' and instagram_token:
            try:
                from instagram_bot import start_instagram_bot_automatically
                success = start_instagram_bot_automatically(bot.id, instagram_token)
                if success:
                    bot.is_active = True
                    db.session.commit()
                    flash('Instagram bot muvaffaqiyatli yaratildi va ishga tushirildi!', 'success')
                else:
                    flash('Bot yaratildi, lekin token noto\'g\'ri yoki ishga tushirishda muammo!', 'warning')
            except Exception as e:
                flash(f'Bot yaratildi, lekin aktivlashtirish xatoligi: {str(e)}', 'warning')
        elif platform == 'WhatsApp' and whatsapp_token and whatsapp_phone_id:
            try:
                from whatsapp_bot import start_whatsapp_bot_automatically
                success = start_whatsapp_bot_automatically(bot.id, whatsapp_token, whatsapp_phone_id)
                if success:
                    bot.is_active = True
                    db.session.commit()
                    flash('WhatsApp bot muvaffaqiyatli yaratildi va ishga tushirildi!', 'success')
                else:
                    flash('Bot yaratildi, lekin token noto\'g\'ri yoki ishga tushirishda muammo!', 'warning')
            except Exception as e:
                flash(f'Bot yaratildi, lekin aktivlashtirish xatoligi: {str(e)}', 'warning')
        else:
            flash('Bot muvaffaqiyatli yaratildi!', 'success')
        
        return redirect(url_for('main.dashboard'))
    
    return render_template('bot_create.html', templates=TEMPLATES)


@bot_bp.route('/bot/<int:bot_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_bot(bot_id):
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu botni tahrirlash huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        bot.name = request.form.get('name', bot.name)
        bot.platform = request.form.get('platform', bot.platform)
        bot.telegram_token = request.form.get('telegram_token', bot.telegram_token)
        bot.instagram_token = request.form.get('instagram_token', bot.instagram_token)
        bot.whatsapp_token = request.form.get('whatsapp_token', bot.whatsapp_token)
        bot.whatsapp_phone_id = request.form.get('whatsapp_phone_id', bot.whatsapp_phone_id)
        
        # Suhbat kuzatuvi sozlamalarini yangilash
        admin_chat_id = request.form.get('admin_chat_id')
        notification_channel = request.form.get('notification_channel')
        notifications_enabled = bool(request.form.get('notifications_enabled'))
        
        if admin_chat_id is not None:
            current_user.admin_chat_id = admin_chat_id.strip() if admin_chat_id.strip() else None
        if notification_channel is not None:
            current_user.notification_channel = notification_channel.strip() if notification_channel.strip() else None
        current_user.notifications_enabled = notifications_enabled
        
        # Custom welcome message
        custom_welcome = request.form.get('custom_welcome_message')
        if custom_welcome is not None:
            bot.custom_welcome_message = custom_welcome.strip()
        
        # Agar Telegram bot token o'zgargan bo'lsa, qayta ishga tushirish (central manager)
        if bot.platform == 'Telegram' and bot.telegram_token:
            try:
                bot_manager.start_bot_polling(bot)
                bot.is_active = True
            except Exception as e:
                logging.error(f"Telegram botni ishga tushirishda xato: {e}")
                flash('Bot ma\'lumotlari yangilandi, lekin token noto\'g\'ri!', 'warning')
        elif bot.platform == 'Instagram' and bot.instagram_token:
            try:
                from instagram_bot import start_instagram_bot_automatically
                success = start_instagram_bot_automatically(bot.id, bot.instagram_token)
                if success:
                    bot.is_active = True
                else:
                    flash('Bot ma\'lumotlari yangilandi, lekin Instagram token ishlamadi!', 'warning')
            except Exception as e:
                logging.error(f"Instagram botni ishga tushirishda xato: {e}")
                flash('Instagram botni yangilashda xato yuz berdi.', 'warning')
        elif bot.platform == 'WhatsApp' and bot.whatsapp_token and bot.whatsapp_phone_id:
            try:
                from whatsapp_bot import start_whatsapp_bot_automatically
                success = start_whatsapp_bot_automatically(bot.id, bot.whatsapp_token, bot.whatsapp_phone_id)
                if success:
                    bot.is_active = True
                else:
                    flash('Bot ma\'lumotlari yangilandi, lekin WhatsApp token ishlamadi!', 'warning')
            except Exception as e:
                logging.error(f"WhatsApp botni ishga tushirishda xato: {e}")
                flash('WhatsApp botni yangilashda xato yuz berdi.', 'warning')
        
        # MiniApp Customization (Premium/Admin only)
        owner_sub = (current_user.subscription_type or '').strip().lower()
        if owner_sub in ['premium', 'admin']:
            business_type = request.form.get('business_type')
            if business_type in ['product', 'service']:
                bot.business_type = business_type
                
            miniapp_theme = request.form.get('miniapp_theme_color')
            miniapp_bg = request.form.get('miniapp_bg_color')
            miniapp_card = request.form.get('miniapp_card_color')
            miniapp_welcome = request.form.get('miniapp_welcome_text')
            miniapp_currency = request.form.get('miniapp_currency')
            
            if miniapp_theme:
                bot.miniapp_theme_color = miniapp_theme.strip()
            if miniapp_bg:
                bot.miniapp_bg_color = miniapp_bg.strip()
            if miniapp_card:
                bot.miniapp_card_color = miniapp_card.strip()
            if miniapp_welcome is not None:
                bot.miniapp_welcome_text = miniapp_welcome.strip()[:300]
            if miniapp_currency:
                bot.miniapp_currency = miniapp_currency.strip()[:20]
                
            # Handle Logo Upload
            if 'business_logo' in request.files:
                logo_file = request.files['business_logo']
                if logo_file and logo_file.filename != '':
                    try:
                        upload_result = cloudinary.uploader.upload(
                            logo_file,
                            folder="botfactory/logos"
                        )
                        bot.business_logo = upload_result.get('secure_url')
                    except Exception as e:
                        logging.error(f"Failed to upload MiniApp logo to Cloudinary: {e}")
                        flash("Logoni yuklashda xatolik yuz berdi. Iltimos, keyinroq qayta urinib ko'ring.", "warning")
        
        db.session.commit()
        flash('Bot ma\'lumotlari yangilandi!', 'success')
        return redirect(url_for('main.dashboard'))
    
    owner_sub = (current_user.subscription_type or '').strip().lower()
    return render_template('bot_edit.html', bot=bot, owner_sub=owner_sub)


@bot_bp.route('/bot/<int:bot_id>/start', methods=['POST'])
@login_required
def start_bot(bot_id):
    """Botni qo'lbola ishga tushirish"""
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu botni ishga tushirish huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    if bot.platform == 'Telegram' and bot.telegram_token:
        try:
            bot_manager.start_bot_polling(bot)
            bot.is_active = True
            db.session.commit()
            flash('Bot muvaffaqiyatli ishga tushirildi!', 'success')
        except Exception as e:
            flash(f'Xatolik: {str(e)}', 'error')
    else:
        flash('Bot tokenini tekshiring!', 'error')
    
    return redirect(url_for('main.dashboard'))


@bot_bp.route('/bot/<int:bot_id>/stop', methods=['POST'])
@login_required
def stop_bot(bot_id):
    """Botni to'xtatish"""
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu botni to\'xtatish huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        bot_manager.stop_bot_polling(bot.id, 'telegram')
        bot.is_active = False
        db.session.commit()
        flash('Bot to\'xtatildi!', 'success')
    except Exception as e:
        flash(f'Xatolik: {str(e)}', 'error')
    
    return redirect(url_for('main.dashboard'))


@bot_bp.route('/bot/<int:bot_id>/ai-insights', methods=['GET'])
@login_required
def bot_ai_insights(bot_id):
    """AI Chat Analytics - insights from recent chats"""
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        return jsonify({'success': False, 'message': 'Huquqingiz yo\'q'}), 403
        
    owner_sub = (bot.owner.subscription_type or '').lower().strip()
    if owner_sub not in ['premium', 'admin']:
        return jsonify({
            'success': False, 
            'message': '<div class="alert alert-warning mb-0"><i class="fas fa-crown text-warning me-2"></i><b>Premium Xususiyat:</b> Sun\'iy intellekt orqali mijozlar talabini tahlil qilish uchun Premium obunaga o\'ting.</div>'
        }), 403
        
    try:
        from models import ChatHistory
        import google.generativeai as genai
        import os
        
        # Get last 50 chats
        chats = ChatHistory.query.filter_by(bot_id=bot_id).order_by(ChatHistory.created_at.desc()).limit(50).all()
        
        if len(chats) < 5:
            return jsonify({
                'success': False, 
                'message': '<div class="alert alert-warning">Tahlil qilish uchun yetarli suhbat tarixi yo\'q. Kamida 5 ta suhbat bo\'lishi kerak.</div>'
            })
            
        chat_text = "\n".join([f"Mijoz: {c.message}\nBot: {c.response}" for c in reversed(chats)])
        
        prompt = f"""Quyida Telegram bot va mijozlar o'rtasidagi so'nggi suhbatlar tarixi keltirilgan.
Suhbatlarni tahlil qilib, quyidagi ma'lumotlarni aniq va qisqa (o'zbek tilida) chiqarib ber:
1. 🎯 Mijozlar asosan qaysi mahsulot/xizmatlarga qiziqmoqda?
2. ❓ Eng ko'p tushadigan savol yoki e'tiroz nima?
3. 💡 Savdoni oshirish uchun sening maslahating.

Javobingni HTML formatda qaytar (hech qanday ```html teglari va markdown formatsiz, to'g'ridan to'g'ri HTML qaytar). Fikrlar chiroyli va tushunarli bo'lsin.

SUHBATLAR:
{chat_text}"""

        api_key = os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_API_KEY3") or os.environ.get("GOOGLE_API_KEY2")
        genai.configure(api_key=api_key)
        
        # Using a fast and capable model
        model = genai.GenerativeModel('gemini-2.5-flash')
        response = model.generate_content(prompt)
        
        # Clean markdown if AI accidentally adds it
        cleaned_html = response.text.replace('```html', '').replace('```', '').strip()
        
        return jsonify({
            'success': True,
            'insights': cleaned_html
        })
    except Exception as e:
        return jsonify({'success': False, 'message': f'<div class="alert alert-danger">Tahlil qilishda xatolik: {str(e)}</div>'})


@bot_bp.route('/bot/<int:bot_id>/delete', methods=['POST'])
@login_required
def delete_bot(bot_id):
    bot = Bot.query.get_or_404(bot_id)
    
    if bot.user_id != current_user.id and not current_user.is_admin:
        flash('Sizda bu botni o\'chirish huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    db.session.delete(bot)
    db.session.commit()
    
    flash('Bot muvaffaqiyatli o\'chirildi!', 'success')
    return redirect(url_for('main.dashboard'))
