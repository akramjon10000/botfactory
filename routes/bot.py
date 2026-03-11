"""Bot CRUD routes"""
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from bot_manager import bot_manager
from models import Bot

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
    
    return render_template('bot_create.html')


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
        
        db.session.commit()
        flash('Bot ma\'lumotlari yangilandi!', 'success')
        return redirect(url_for('main.dashboard'))
    
    return render_template('bot_edit.html', bot=bot)


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
