"""Admin routes"""
import logging
from datetime import datetime, timedelta
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from app import db
from bot_manager import bot_manager
from models import User, Bot, KnowledgeBase, Payment, ChatHistory, BroadcastMessage, BotCustomer, BotMessage
import pandas as pd
import requests

admin_routes_bp = Blueprint('admin_routes', __name__)


@admin_routes_bp.route('/admin')
@admin_routes_bp.route('/admin/')
@login_required
def admin():
    if not current_user.is_admin:
        flash('Sizda admin huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    # Build admin dashboard context
    users = User.query.all()
    payments = Payment.query.order_by(Payment.created_at.desc()).limit(50).all()
    bots = Bot.query.all()
    
    # Statistics
    stats = {
        'total_users': User.query.count(),
        'active_subscriptions': User.query.filter(User.subscription_type.in_(['starter', 'basic', 'premium'])).count(),
        'total_bots': Bot.query.count(),
        'total_payments': Payment.query.filter_by(status='completed').count(),
        'monthly_revenue': Payment.query.filter(
            Payment.status == 'completed',
            Payment.created_at >= datetime.utcnow() - timedelta(days=30)
        ).count()
    }
    
    # Get broadcast messages
    broadcasts = BroadcastMessage.query.order_by(BroadcastMessage.created_at.desc()).limit(10).all()
    
    # Get recent chat history
    chat_history = ChatHistory.query.order_by(ChatHistory.created_at.desc()).limit(50).all()
    
    return render_template('admin.html', users=users, payments=payments, 
                         bots=bots, stats=stats, broadcasts=broadcasts, chat_history=chat_history)


@admin_routes_bp.route('/admin/delete-bot/<int:bot_id>', methods=['POST'])
@login_required
def admin_delete_bot(bot_id):
    """Admin uchun: botni to'xtatib, barcha bog'liq ma'lumotlari bilan o'chirish
    Xavfsizlik: faqat admin. Foydalanuvchi o'z botini o'chirmaydi (admin paneldan).
    """
    if not current_user.is_admin:
        flash('Ruxsat yo\'q', 'error')
        return redirect(url_for('main.dashboard'))

    try:
        bot = Bot.query.get_or_404(bot_id)

        # Stop platform runner safely
        platform = (bot.platform or '').lower()
        try:
            if platform == 'telegram':
                bot_manager.stop_bot_polling(bot.id, 'telegram')
            elif platform == 'instagram':
                from instagram_bot import instagram_manager
                instagram_manager.stop_bot(bot.id)
            elif platform == 'whatsapp':
                from whatsapp_bot import whatsapp_manager
                whatsapp_manager.stop_bot(bot.id)
        except Exception as e:
            logging.warning(f"Bot stop during delete warning: {e}")

        # Delete related records
        try:
            ChatHistory.query.filter_by(bot_id=bot.id).delete(synchronize_session=False)
        except Exception:
            pass
        try:
            BotCustomer.query.filter_by(bot_id=bot.id).delete(synchronize_session=False)
        except Exception:
            pass
        try:
            BotMessage.query.filter_by(bot_id=bot.id).delete(synchronize_session=False)
        except Exception:
            pass
        try:
            BroadcastMessage.query.filter_by(bot_id=bot.id).delete(synchronize_session=False)
        except Exception:
            pass

        # Finally delete bot
        db.session.delete(bot)
        db.session.commit()
        flash('Bot va bog\'liq ma\'lumotlar o\'chirildi', 'success')
    except Exception as e:
        logging.error(f"Admin delete bot error: {e}")
        db.session.rollback()
        flash('O\'chirishda xatolik', 'error')

    return redirect(url_for('main.dashboard'))


@admin_routes_bp.route('/admin/delete-user/<int:user_id>', methods=['POST'])
@login_required
def admin_delete_user(user_id):
    """Admin uchun: foydalanuvchini va uning botlarini o'chirish.
    Admin rolli foydalanuvchilarni saqlab qolamiz.
    """
    if not current_user.is_admin:
        flash('Ruxsat yo\'q', 'error')
        return redirect(url_for('main.dashboard'))

    user = User.query.get_or_404(user_id)
    if getattr(user, 'is_admin', False):
        flash('Admin foydalanuvchini o\'chirib bo\'lmaydi', 'warning')
        return redirect(url_for('main.dashboard'))

    try:
        # Delete user's bots via admin_delete_bot logic (stop + cascade)
        bots = Bot.query.filter_by(user_id=user.id).all()
        for b in bots:
            try:
                # Reuse deletion steps inline to keep single transaction
                platform = (b.platform or '').lower()
                try:
                    if platform == 'telegram':
                        bot_manager.stop_bot_polling(b.id, 'telegram')
                    elif platform == 'instagram':
                        from instagram_bot import instagram_manager
                        instagram_manager.stop_bot(b.id)
                    elif platform == 'whatsapp':
                        from whatsapp_bot import whatsapp_manager
                        whatsapp_manager.stop_bot(b.id)
                except Exception:
                    pass
                ChatHistory.query.filter_by(bot_id=b.id).delete(synchronize_session=False)
                BotCustomer.query.filter_by(bot_id=b.id).delete(synchronize_session=False)
                try:
                    BotMessage.query.filter_by(bot_id=b.id).delete(synchronize_session=False)
                except Exception:
                    pass
                try:
                    BroadcastMessage.query.filter_by(bot_id=b.id).delete(synchronize_session=False)
                except Exception:
                    pass
                db.session.delete(b)
            except Exception as inner_e:
                logging.error(f"Delete user bot error: {inner_e}")

        # Finally delete user
        db.session.delete(user)
        db.session.commit()
        flash('Foydalanuvchi va uning botlari o\'chirildi', 'success')
    except Exception as e:
        logging.error(f"Admin delete user error: {e}")
        db.session.rollback()
        flash('O\'chirishda xatolik', 'error')

    return redirect(url_for('main.dashboard'))


@admin_routes_bp.route('/admin/test_message', methods=['POST'])
@login_required
def test_message():
    if not current_user.is_admin:
        flash('Sizda admin huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        from telegram_bot import send_admin_message_to_user
        
        test_message_text = "🧪 TEST XABARI\n\nSalom! Bu BotFactory AI dan test xabari.\n\n✅ Telegram bot to'g'ri ishlayapti!\n\n📅 Vaqt: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Admin foydalanuvchining telegram_id sini olish
        if current_user.telegram_id:
            result = send_admin_message_to_user(current_user.telegram_id, test_message_text)
            if result:
                flash('✅ Test xabari muvaffaqiyatli yuborildi!', 'success')
            else:
                flash('❌ Test xabarini yuborishda xatolik yuz berdi!', 'error')
        else:
            flash('❌ Telegram ID topilmadi. Avval botga /start buyrug\'ini yuboring!', 'error')
            
    except Exception as e:
        flash(f'❌ Xatolik: {str(e)}', 'error')
        
    return redirect(url_for('admin_routes.admin'))


# =============== Instagram Diagnostics ===============
@admin_routes_bp.route('/admin/api/instagram/diagnostics/<int:bot_id>')
@login_required
def instagram_diagnostics(bot_id):
    """Simple diagnostics to verify Instagram token and show webhook URL.
    Returns JSON with checks: token_present, token_valid (via /me), webhook_url.
    """
    if not current_user.is_admin:
        return jsonify({'error': 'Access denied'}), 403
    try:
        bot = Bot.query.get_or_404(bot_id)
        if (bot.platform or '').lower() != 'instagram':
            return jsonify({'error': 'Not an Instagram bot'}), 400
        info = {
            'bot_id': bot_id,
            'platform': 'instagram',
            'token_present': bool(bot.instagram_token),
            'token_valid': False,
            'webhook_url': url_for('instagram.instagram_webhook', bot_id=bot_id, _external=True),
            'webhook_verify_param_example': '?hub.verify_token=YOUR_VERIFY_TOKEN&hub.challenge=123',
        }
        # Minimal token validation: call Graph /me
        if bot.instagram_token:
            try:
                resp = requests.get('https://graph.facebook.com/v18.0/me', params={'access_token': bot.instagram_token}, timeout=15)
                j = {}
                try:
                    j = resp.json()
                except Exception:
                    j = {'raw': resp.text}
                info['graph_status_code'] = resp.status_code
                info['graph_response'] = j
                if resp.status_code == 200 and j.get('id'):
                    info['token_valid'] = True
            except Exception as e:
                info['graph_error'] = str(e)
        return jsonify(info)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@admin_routes_bp.route('/admin/set_telegram_id', methods=['POST'])
@login_required
def set_telegram_id():
    if not current_user.is_admin:
        flash('Sizda admin huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        telegram_id = request.form.get('telegram_id')
        if telegram_id and telegram_id.isdigit():
            # Mavjud foydalanuvchini tekshirish
            existing_user = User.query.filter_by(telegram_id=telegram_id).first()
            
            if existing_user and existing_user.id != current_user.id:
                if existing_user.username.startswith('tg_'):
                    # Avtomatik yaratilgan foydalanuvchini o'chirish
                    # Avval uning barcha ma'lumotlarini admin ga ko'chirish
                    
                    # Botlarni ko'chirish
                    from models import Bot
                    for bot in existing_user.bots:
                        bot.user_id = current_user.id
                    
                    # Eski foydalanuvchini o'chirish
                    db.session.delete(existing_user)
                    db.session.flush()
                    
                    flash(f'✅ Telegram ID {telegram_id} ga ega avtomatik foydalanuvchi admin bilan birlashtirildi!', 'info')
                else:
                    flash(f'❌ Telegram ID {telegram_id} boshqa haqiqiy foydalanuvchi tomonidan ishlatilmoqda!', 'error')
                    return redirect(url_for('admin_routes.admin'))
            
            # Admin ga Telegram ID ni tayinlash
            current_user.telegram_id = telegram_id
            db.session.commit()
            flash('✅ Telegram ID muvaffaqiyatli saqlandi!', 'success')
        else:
            flash('❌ To\'g\'ri Telegram ID kiriting (faqat raqamlar)!', 'error')
            
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Xatolik: {str(e)}', 'error')
        
    return redirect(url_for('admin_routes.admin'))


@admin_routes_bp.route('/admin/export-chat-history')
@login_required
def export_chat_history():
    """Export chat history to Excel"""
    if not current_user.is_admin:
        flash('Sizda admin huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        # Get all chat history
        chat_data = ChatHistory.query.order_by(ChatHistory.created_at.desc()).all()
        
        # Prepare data for Excel
        export_data = []
        for chat in chat_data:
            # Get bot name
            bot = Bot.query.get(chat.bot_id)
            bot_name = bot.name if bot else 'Noma\'lum bot'
            
            export_data.append({
                'Vaqt': chat.created_at.strftime('%d.%m.%Y %H:%M:%S'),
                'Bot nomi': bot_name,
                'Platform': bot.platform if bot else 'Noma\'lum',
                'Telegram ID': chat.user_telegram_id or '',
                'Instagram ID': chat.user_instagram_id or '',
                'WhatsApp raqami': chat.user_whatsapp_number or '',
                'Foydalanuvchi xabari': chat.message or '',
                'Bot javobi': chat.response or '',
                'Til': chat.language or 'uz'
            })
        
        if not export_data:
            flash('Eksport qilish uchun yozishmalar mavjud emas!', 'warning')
            return redirect(url_for('admin_routes.admin'))
        
        # Create Excel file
        df = pd.DataFrame(export_data)
        
        # Create a BytesIO object
        output = BytesIO()
        
        # Write to Excel
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Bot Yozishmalari', index=False)
        
        output.seek(0)
        
        # Generate filename with current date
        filename = f"bot_yozishmalari_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=filename
        )
        
    except Exception as e:
        flash(f'Eksport qilishda xatolik: {str(e)}', 'error')
        return redirect(url_for('admin_routes.admin'))


@admin_routes_bp.route('/admin/cleanup-chat-history', methods=['POST'])
@login_required
def cleanup_chat_history():
    """Clean up old chat history to reduce database size"""
    if not current_user.is_admin:
        flash('Sizda admin huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    try:
        # Keep only last 1000 entries to reduce database load
        total_count = ChatHistory.query.count()
        
        if total_count > 1000:
            # Get IDs of records to keep (latest 1000)
            keep_ids = db.session.query(ChatHistory.id).order_by(ChatHistory.created_at.desc()).limit(1000).subquery()
            
            # Delete old records
            deleted_count = ChatHistory.query.filter(~ChatHistory.id.in_(keep_ids)).delete(synchronize_session=False)
            db.session.commit()
            
            flash(f'Eski yozishmalar tozalandi! {deleted_count} ta yozuv o\'chirildi, {1000} ta oxirgi yozuv saqlandi.', 'success')
        else:
            flash(f'Tozalash kerak emas. Jami {total_count} ta yozishma mavjud (1000 dan kam).', 'info')
    
    except Exception as e:
        flash(f'Tozalashda xatolik: {str(e)}', 'error')
    
    return redirect(url_for('admin_routes.admin'))


@admin_routes_bp.route('/admin/broadcast', methods=['POST'])
@login_required
def send_broadcast():
    if not current_user.is_admin:
        flash('Sizda admin huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    message_text = request.form.get('message_text')
    target_type = request.form.get('target_type', 'all')
    segment = request.form.get('segment', '').strip()
    
    if not message_text:
        flash('Xabar matni kiritilishi shart!', 'error')
        return redirect(url_for('admin_routes.admin'))
    
    # Create broadcast message record
    broadcast = BroadcastMessage()
    broadcast.admin_id = current_user.id
    broadcast.message_text = message_text
    broadcast.target_type = target_type
    broadcast.status = 'sending'
    broadcast.sent_at = datetime.utcnow()
    
    db.session.add(broadcast)
    db.session.commit()
    
    # Send messages
    try:
        sent_count = send_broadcast_messages(broadcast.id, message_text, target_type, segment)
        
        # Update broadcast record
        broadcast.sent_count = sent_count
        broadcast.status = 'completed'
        db.session.commit()
        
        flash(f'Xabar muvaffaqiyatli yuborildi! {sent_count} ta foydalanuvchiga yetkazildi.', 'success')
    except Exception as e:
        broadcast.status = 'failed'
        db.session.commit()
        flash('Xabar yuborishda xatolik yuz berdi!', 'error')
    
    return redirect(url_for('admin_routes.admin'))

@admin_routes_bp.route('/admin/approve-payment/<int:payment_id>', methods=['POST'])
@login_required
def approve_payment(payment_id):
    if not current_user.is_admin:
        flash("Sizda admin huquqi yo'q!", 'error')
        return redirect(url_for('main.dashboard'))
        
    payment = Payment.query.get_or_404(payment_id)
    if payment.status == 'completed':
        flash("Bu to'lov allaqachon tasdiqlangan!", 'warning')
        return redirect(url_for('admin_routes.admin'))
        
    try:
        payment.status = 'completed'
        
        # Obunani faollashtirish
        user = User.query.get(payment.user_id)
        if user:
            user.subscription_type = payment.subscription_type
            user.subscription_end_date = datetime.utcnow() + timedelta(days=30)
            
            # User ga telegram xabar yuborish
            try:
                from telegram_bot import send_admin_message_to_user
                if user.telegram_id:
                    text = f"🎉 <b>Tabriklaymiz!</b>\n\nTo'lovingiz tasdiqlandi va <b>{payment.subscription_type.capitalize()}</b> obunangiz faollashtirildi.\nEndi yangi imkoniyatlardan bemalol foydalanishingiz mumkin."
                    send_admin_message_to_user(user.telegram_id, text)
            except Exception:
                pass
                
        db.session.commit()
        flash(f"To'lov tasdiqlandi. @{user.username} obunasi faollashtirildi.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Xatolik yuz berdi: {str(e)}", "error")
        
    return redirect(url_for('admin_routes.admin'))

@admin_routes_bp.route('/admin/reject-payment/<int:payment_id>', methods=['POST'])
@login_required
def reject_payment(payment_id):
    if not current_user.is_admin:
        return redirect(url_for('main.dashboard'))
        
    payment = Payment.query.get_or_404(payment_id)
    
    try:
        payment.status = 'failed'
        db.session.commit()
        
        # Notify user maybe
        user = User.query.get(payment.user_id)
        try:
            from telegram_bot import send_admin_message_to_user
            if user and user.telegram_id:
                text = f"❌ <b>To'lov bekor qilindi</b>\n\nAdmin sizning oxirgi to'lov hisobotingizni tasdiqlamadi."
                send_admin_message_to_user(user.telegram_id, text)
        except Exception:
            pass
            
        flash("To'lov bekor qilindi.", "info")
    except Exception as e:
        db.session.rollback()
        flash(f"Xatolik: {str(e)}", "error")
        
    return redirect(url_for('admin_routes.admin'))

@admin_routes_bp.route('/admin/change-subscription', methods=['POST'])
@login_required
def change_user_subscription():
    if not current_user.is_admin:
        flash('Sizda admin huquqi yo\'q!', 'error')
        return redirect(url_for('main.dashboard'))
    
    user_id = request.form.get('user_id')
    subscription_type = request.form.get('subscription_type')
    subscription_duration = request.form.get('subscription_duration', '30')
    
    if not user_id or not subscription_type:
        flash('Xatolik: Ma\'lumotlar to\'liq emas!', 'error')
        return redirect(url_for('admin_routes.admin'))
    
    user = User.query.get_or_404(user_id)
    
    # Don't allow changing admin subscription
    if user.subscription_type == 'admin':
        flash('Xatolik: Admin obunasini o\'zgartirib bo\'lmaydi!', 'error')
        return redirect(url_for('admin_routes.admin'))
    
    # Handle trial_14 as a special case
    if subscription_type == 'trial_14':
        user.subscription_type = 'basic'
        user.subscription_end_date = datetime.utcnow() + timedelta(days=7)
        subscription_name = '7 kun test'
        duration_text = '7 kun'
    elif subscription_type == 'free':
        user.subscription_type = 'free'
        user.subscription_end_date = None
        subscription_name = 'Bepul'
        duration_text = 'cheksiz'
    else:
        # Set new subscription
        user.subscription_type = subscription_type
        days = int(subscription_duration)
        user.subscription_end_date = datetime.utcnow() + timedelta(days=days)
        subscription_names = {
            'starter': 'Standart',
            'basic': 'Standart',
            'premium': 'Premium'
        }
        subscription_name = subscription_names.get(subscription_type, subscription_type)
        duration_text = f'{subscription_duration} kun'
    
    try:
        db.session.commit()
        
        # Create payment record for manual subscription change
        payment = Payment()
        payment.user_id = user.id
        payment.amount = 0
        payment.method = 'Admin'
        payment.status = 'completed'
        payment.subscription_type = subscription_type
        payment.transaction_id = f'ADMIN_{current_user.id}_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}'
        
        db.session.add(payment)
        db.session.commit()
        
        flash(f'{user.username} foydalanuvchisining obunasi {subscription_name} ga o\'zgartirildi ({duration_text})', 'success')
    except Exception as e:
        db.session.rollback()
        flash('Obunani o\'zgartirishda xatolik yuz berdi!', 'error')
    
    return redirect(url_for('admin_routes.admin'))


def send_broadcast_messages(broadcast_id, message_text, target_type, segment: str = ""):
    """Send broadcast message to users"""
    sent_count = 0
    sent_keys = set()

    # 1) Platform Users (with telegram_id)
    if target_type == 'customers':
        base_q = User.query.filter(User.subscription_type.in_(['starter', 'basic', 'premium']))
    else:
        base_q = User.query

    # Apply segment filters to platform users
    now = datetime.utcnow()
    if segment == 'trial_14':
        users = base_q.filter(
            User.subscription_type == 'free',
            (
                (User.subscription_end_date != None) & (User.subscription_end_date > now) & (User.subscription_end_date <= now + timedelta(days=1))
            ) | (
                (User.subscription_end_date == None)
            )
        ).all()
    elif segment == 'active_30d':
        from models import ChatHistory
        cutoff = now - timedelta(days=30)
        subq = db.session.query(ChatHistory.user_telegram_id).filter(ChatHistory.created_at >= cutoff).subquery()
        users = base_q.filter(User.telegram_id.isnot(None), User.telegram_id.in_(subq)).all()
    elif segment == 'paid':
        users = base_q.filter(User.subscription_type.in_(['starter', 'basic', 'premium'])).all()
    elif segment == 'unpaid':
        users = base_q.filter(User.subscription_type == 'free').all()
    else:
        users = base_q.filter(User.telegram_id.isnot(None)).all()

    try:
        from telegram_bot import send_admin_message_to_user, send_message_to_bot_customer
        # Send to platform users first
        for user in users:
            if not user.telegram_id:
                continue
            key = ('user', str(user.telegram_id))
            if key in sent_keys:
                continue
            try:
                if send_admin_message_to_user(user.telegram_id, message_text):
                    sent_keys.add(key)
                    sent_count += 1
            except Exception:
                continue

        # 2) Bot end-users (BotCustomer) — telegram/instagram/whatsapp
        if target_type != 'customers':
            cust_q = BotCustomer.query.filter(BotCustomer.is_active.is_(True))
            if segment == 'active_30d':
                cust_q = cust_q.filter(BotCustomer.last_interaction >= now - timedelta(days=30))
            customers = cust_q.all()
            for c in customers:
                key = ('bot', c.bot_id, c.platform, str(c.platform_user_id))
                if ('user', str(c.platform_user_id)) in sent_keys or key in sent_keys:
                    continue
                try:
                    ok = False
                    if c.platform == 'telegram':
                        ok = send_message_to_bot_customer(c.bot_id, c.platform, str(c.platform_user_id), f"📢 Admin xabari:\n\n{message_text}")
                    elif c.platform == 'instagram':
                        from instagram_bot import send_message_to_instagram_customer
                        ok = send_message_to_instagram_customer(c.bot_id, str(c.platform_user_id), f"📢 Admin xabari:\n\n{message_text}")
                    elif c.platform == 'whatsapp':
                        from whatsapp_bot import send_message_to_whatsapp_customer
                        ok = send_message_to_whatsapp_customer(c.bot_id, str(c.platform_user_id), f"📢 Admin xabari:\n\n{message_text}")
                    if ok:
                        sent_keys.add(key)
                        sent_count += 1
                except Exception:
                    continue
    except Exception:
        pass

    return sent_count
