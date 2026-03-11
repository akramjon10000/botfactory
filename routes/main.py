"""Main routes - core pages, SEO, settings, dashboard"""
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_login import login_required, current_user
from app import db, csrf
from models import User, Bot, Payment
from datetime import datetime, timedelta
from sqlalchemy import text
from rate_limiter import rate_limiter, get_client_ip

main_bp = Blueprint('main', __name__)


@main_bp.route('/')
def index():
    from routes.blog import load_blog_posts
    latest_posts = load_blog_posts()[:3]
    return render_template('index.html', latest_posts=latest_posts)


@main_bp.route('/api/webchat', methods=['POST'])
@csrf.exempt
def api_webchat():
    """
    Frontend web chat endpoint. Returns AI reply as JSON.
    ---
    tags:
      - Chat API
    description: Ushbu endpoint orqali veb-sahifadagi vidjet AI bot bilan yozishadi.
    parameters:
      - in: body
        name: body
        schema:
          type: object
          properties:
            message:
              type: string
              example: "Salom, menga yordam bera olasizmi?"
              description: Foydalanuvchi xabari
    responses:
      200:
        description: AI javobi muvaffaqiyatli saqlandi
        schema:
          type: object
          properties:
            ok:
              type: boolean
              example: true
            reply:
              type: string
              example: "Assalomu alaykum! Ha, men BotFactory yordamchisiman..."
      400:
        description: Xabar bo'sh yoki noto'g'ri so'rov
      429:
        description: Rate limitdan o'tildi
    """
    try:
        client_ip = get_client_ip(request)
        allowed, retry_after = rate_limiter.is_allowed(
            key=f"webchat:{client_ip}",
            limit=30,
            window_seconds=60
        )
        if not allowed:
            return jsonify({
                "ok": False,
                "error": "rate_limited",
                "retry_after": retry_after
            }), 429

        data = request.get_json(silent=True) or {}
        message = (data.get('message') or '').strip()
        if not message:
            return jsonify({"ok": False, "error": "empty_message"}), 400

        # Resolve language preference
        user_lang = 'uz'
        try:
            from flask_login import current_user
            if current_user.is_authenticated and current_user.language:
                user_lang = current_user.language
        except Exception:
            pass

        bot_name = 'BotFactory AI'
        from ai import get_ai_response

        # Use dedicated BotFactory AI knowledge for the website widget
        # (NOT a random user's bot knowledge base!)
        kb_text = """BotFactory AI — O'zbekiston uchun mo'ljallangan AI chatbot platformasi.

Asosiy xususiyatlar:
- Telegram botlar yaratish va boshqarish
- Google Gemini AI asosida aqlli javoblar (o'zbek, rus, ingliz tillarida)
- Bilim bazasi yuklash (PDF, Word, TXT, CSV)
- Mijozlar bilan avtomatik suhbat
- Boshqaruv paneli va analitika
- Marketing kampaniyalari

Tariflar:
- Test (Bepul): 7 kunlik sinov, 1 ta bot, faqat Telegram, o'zbek tili
- Standart: 165,000 so'm/oy, 1 ta bot, 3 til, kengaytirilgan AI (GPT)
- Premium: 590,000 so'm/oy, 3 tagacha bot, texnik ko'mak, haftalik hisobot

Qanday boshlash:
1. Ro'yxatdan o'ting (https://botfactory-am64.onrender.com/auth/register)
2. BotFather'dan Telegram token oling
3. Dashboard'da yangi bot yarating va tokenni kiriting
4. Bilim bazasini yuklang — bot tayyor!

Bog'lanish: Telegram orqali yozing yoki saytda ro'yxatdan o'ting.
Instagram va WhatsApp integratsiyasi tez kunda qo'shiladi.
"""
        owner_contact_info = ''

        reply = get_ai_response(message=message, bot_name=bot_name, user_language=user_lang, knowledge_base=kb_text, chat_history='', owner_contact_info=owner_contact_info)
        reply = reply or 'Salom! Hozircha javob tayyorlanmoqda. 🤖'
        return jsonify({"ok": True, "reply": reply})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)[:120]}), 500


@main_bp.route('/healthz')
def healthz():
    """Simple health check endpoint for deployment monitoring"""
    try:
        from app import db
        db.session.execute(text('SELECT 1'))
        return jsonify({"status": "ok", "db": "ok"}), 200
    except Exception:
        return jsonify({"status": "ok", "db": "degraded"}), 200


@main_bp.route('/enable-miniapp', methods=['POST'])
@login_required
def enable_miniapp():
    """Enable Mini App for all bots (admin-only maintenance endpoint)"""
    if not current_user.is_admin:
        return jsonify({"status": "error", "error": "Forbidden"}), 403

    try:
        bots = Bot.query.all()
        enabled_count = 0
        for bot in bots:
            if not getattr(bot, 'miniapp_enabled', True):
                bot.miniapp_enabled = True
                enabled_count += 1
            elif bot.miniapp_enabled is None:
                bot.miniapp_enabled = True
                enabled_count += 1
        
        # Set all to True just in case
        for bot in bots:
            bot.miniapp_enabled = True
        
        db.session.commit()
        return jsonify({
            "status": "ok",
            "message": f"Mini App enabled for {len(bots)} bots",
            "bots_enabled": len(bots)
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500


@main_bp.route('/dashboard')
@login_required
def dashboard():
    bots = Bot.query.filter_by(user_id=current_user.id).all()
    bot_count = len(bots)
    
    # Get subscription info
    subscription_info = {
        'type': current_user.subscription_type,
        'end_date': current_user.subscription_end_date,
        'active': current_user.subscription_active(),
        'can_create': current_user.can_create_bot()
    }
    
    return render_template('dashboard.html', bots=bots, bot_count=bot_count, 
                         subscription_info=subscription_info)


# ================= SEO: sitemap.xml and robots.txt =================
@main_bp.route('/sitemap.xml')
def sitemap_xml():
    """Generate a simple sitemap for key pages"""
    from routes.blog import load_blog_posts
    base = request.url_root.rstrip('/')
    urls = [
        f"{base}/",
        f"{base}/dashboard",
        f"{base}/admin",
        f"{base}/login",
        f"{base}/register",
        f"{base}/help",
    ]
    # Add blog posts
    try:
        for p in load_blog_posts():
            urls.append({
                'loc': f"{base}/blog/{p['slug']}",
                'lastmod': p.get('lastmod')
            })
    except Exception:
        pass
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    ]
    for u in urls:
        xml.append('<url>')
        if isinstance(u, dict):
            xml.append(f"<loc>{u['loc']}</loc>")
            if u.get('lastmod'):
                xml.append(f"<lastmod>{u['lastmod']}</lastmod>")
        else:
            xml.append(f'<loc>{u}</loc>')
        xml.append('</url>')
    xml.append('</urlset>')
    return Response("\n".join(xml), mimetype='application/xml')


@main_bp.route('/robots.txt')
def robots_txt():
    """Basic robots.txt allowing all and pointing to sitemap"""
    base = request.url_root.rstrip('/')
    content = f"""User-agent: *
Allow: /
Sitemap: {base}/sitemap.xml
"""
    return Response(content, mimetype='text/plain')


# ===================== Help / Getting Started =====================
@main_bp.route('/help')
def help_getting_started():
    return render_template('help_getting_started.html')


@main_bp.route('/settings')
@login_required
def settings():
    """User settings page"""
    return render_template('settings.html')


@main_bp.route('/settings/notifications', methods=['POST'])
@login_required
def update_notification_settings():
    """Update notification settings"""
    admin_chat_id = request.form.get('admin_chat_id', '').strip()
    notification_channel = request.form.get('notification_channel', '').strip()
    notifications_enabled = 'notifications_enabled' in request.form
    
    try:
        current_user.admin_chat_id = admin_chat_id if admin_chat_id else None
        current_user.notification_channel = notification_channel if notification_channel else None
        current_user.notifications_enabled = notifications_enabled
        
        db.session.commit()
        
        # Test notification yuborish
        if notifications_enabled and admin_chat_id:
            from notification_service import notification_service
            if notification_service.test_notification(admin_chat_id):
                flash('Bildirishnoma sozlamalari saqlandi va test xabar yuborildi!', 'success')
            else:
                flash('Sozlamalar saqlandi, lekin test xabarni yuborishda xatolik!', 'warning')
        else:
            flash('Bildirishnoma sozlamalari muvaffaqiyatli saqlandi!', 'success')
            
    except Exception as e:
        flash(f'Sozlamalarni saqlashda xatolik: {str(e)}', 'error')
    
    return redirect(url_for('main.settings'))


@main_bp.route('/subscription')
@login_required
def subscription():
    return render_template('subscription.html')

@main_bp.route('/report-payment', methods=['POST'])
@login_required
def report_payment():
    try:
        method = request.form.get('payment_method', 'Xazna')
        subscription_type = request.form.get('subscription_type')
        
        amounts = {
            'starter': 165000,
            'basic': 290000,
            'premium': 590000
        }
        
        if not subscription_type or subscription_type not in amounts:
            flash("Noto'g'ri tarif turi tanlandi!", 'error')
            return redirect(url_for('main.subscription'))
            
        print(f"Report Payment: Method: {method}, SubType: {subscription_type}")
        
        # Check if user already has a pending payment
        existing = Payment.query.filter_by(
            user_id=current_user.id, 
            status='pending',
            subscription_type=subscription_type
        ).first()
        
        if existing:
            flash("Ayni paytda ushbu tarif uchun tasdiqlanmagan to'lovingiz kutilmoqda! Iltimos, admin tasdiqlashini kuting.", "warning")
            return redirect(url_for('main.dashboard'))
            
        # Create pending payment record
        payment = Payment(
            user_id=current_user.id,
            amount=amounts[subscription_type],
            method=method,
            status='pending',
            subscription_type=subscription_type,
            transaction_id=f'REPORT_{current_user.id}_{datetime.utcnow().strftime("%y%m%d%H%M")}'
        )
        db.session.add(payment)
        
        # Try to send admin notification
        try:
            from telegram_bot import send_admin_message_to_user
            admin_users = User.query.filter_by(is_admin=True, is_active=True).all()
            for admin in admin_users:
                if admin.telegram_id:
                    text = f"💰 <b>Yangi to'lov hisoboti!</b>\n\n"
                    text += f"👤 <b>Foydalanuvchi:</b> @{current_user.username}\n"
                    text += f"💳 <b>Tarif:</b> {subscription_type.capitalize()}\n"
                    text += f"💵 <b>Miqdor:</b> {amounts[subscription_type]:,} so'm\n"
                    text += f"🏦 <b>Uslub:</b> {method}\n\n"
                    text += f"✅ Admin panel → To'lovlar orqali tasdiqlang."
                    send_admin_message_to_user(admin.telegram_id, text)
        except Exception as e:
            print(f"Admin notification error: {e}")
            
        db.session.commit()
        
        flash("To'lov hisoboti yuborildi! Adminlar uni tez orada tasdiqlaydi.", "success")
        return redirect(url_for('main.dashboard'))
    except Exception as e:
        db.session.rollback()
        flash(f"Xatolik yuz berdi: {str(e)}", "error")
        return redirect(url_for('main.subscription'))


@main_bp.route('/payment/<subscription_type>', methods=['POST'])
@login_required
def process_payment(subscription_type):
    method = request.form.get('method')
    
    amounts = {
        'starter': 165000,
        'basic': 290000,
        'premium': 590000
    }
    
    if subscription_type not in amounts:
        flash('Noto\'g\'ri tarif turi!', 'error')
        return redirect(url_for('main.subscription'))
    
    payment = Payment()
    payment.user_id = current_user.id
    payment.amount = amounts[subscription_type]
    payment.method = method
    payment.subscription_type = subscription_type
    payment.status = 'pending'
    
    db.session.add(payment)
    db.session.commit()
    
    # Simulate successful payment
    payment.status = 'completed'
    payment.transaction_id = f'TXN_{payment.id}_{datetime.utcnow().strftime("%Y%m%d%H%M%S")}'
    
    # Update user subscription
    current_user.subscription_type = subscription_type
    if subscription_type == 'starter':
        current_user.subscription_end_date = datetime.utcnow() + timedelta(days=30)
    elif subscription_type == 'basic':
        current_user.subscription_end_date = datetime.utcnow() + timedelta(days=30)
    elif subscription_type == 'premium':
        current_user.subscription_end_date = datetime.utcnow() + timedelta(days=30)
    
    db.session.commit()
    
    flash('To\'lov muvaffaqiyatli amalga oshirildi!', 'success')
    return redirect(url_for('main.dashboard'))


@main_bp.route('/api/admin/stats')
@login_required
def admin_stats_api():
    """
    API endpoint for Chart.js dashboard visualizations
    ---
    tags:
      - Admin Analytics
    description: Dashbord uchun kunlik xaridorlar o'sishi va tillar bo'yicha vizual grafik ma'lumotlarini qaytaradi.
    security:
      - cookieAuth: []
    responses:
      200:
        description: Statistik ma'lumotlar
        schema:
          type: object
          properties:
            status:
              type: string
              example: success
            growth:
              type: object
              properties:
                labels:
                  type: array
                  items:
                    type: string
                  example: ["03-04", "03-05", "03-06"]
                data:
                  type: array
                  items:
                    type: integer
                  example: [5, 12, 3]
            languages:
              type: object
              properties:
                labels:
                  type: array
                  items:
                    type: string
                  example: ["UZ", "RU", "EN"]
                data:
                  type: array
                  items:
                    type: integer
                  example: [45, 10, 2]
      401:
        description: Avtorizatsiyadan o'tilmagan
    """
    from models import BotCustomer, Bot
    from sqlalchemy import func
    from datetime import datetime, timedelta
    
    # 1. User Growth (Last 7 days)
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=6)
    
    # Identify bots owned by this user
    user_bot_ids = [b.id for b in Bot.query.filter_by(user_id=current_user.id).all()]
    
    # Daily growth data (New Customers)
    daily_stats = db.session.query(
        func.date(BotCustomer.created_at).label('date'),
        func.count(BotCustomer.id).label('count')
    ).filter(
        BotCustomer.bot_id.in_(user_bot_ids) if user_bot_ids else False,
        BotCustomer.created_at >= start_date
    ).group_by(
        func.date(BotCustomer.created_at)
    ).all()
    
    # Daily messages data (Total Messages)
    from models import ChatHistory
    daily_messages = db.session.query(
        func.date(ChatHistory.created_at).label('date'),
        func.count(ChatHistory.id).label('count')
    ).filter(
        ChatHistory.bot_id.in_(user_bot_ids) if user_bot_ids else False,
        ChatHistory.created_at >= start_date
    ).group_by(
        func.date(ChatHistory.created_at)
    ).all()
    
    # Format for Chart.js
    dates = [(start_date + timedelta(days=i)).strftime('%Y-%m-%d') for i in range(7)]
    
    growth_dict = {str(d.date): d.count for d in daily_stats}
    growth_data = [growth_dict.get(date, 0) for date in dates]
    
    messages_dict = {str(d.date): d.count for d in daily_messages}
    messages_data = [messages_dict.get(date, 0) for date in dates]
    
    # 2. Language Distribution
    lang_stats = db.session.query(
        BotCustomer.language,
        func.count(BotCustomer.id)
    ).filter(
        BotCustomer.bot_id.in_(user_bot_ids) if user_bot_ids else False
    ).group_by(
        BotCustomer.language
    ).all()
    
    lang_labels = []
    lang_data = []
    for lang, count in lang_stats:
        lang_str = lang if lang else 'uz' # Default fallback
        lang_labels.append(lang_str.upper())
        lang_data.append(count)
        
    if not lang_labels:
        lang_labels = ['UZ', 'RU', 'EN']
        lang_data = [0, 0, 0]

    return jsonify({
        'status': 'success',
        'growth': {
            'labels': [d[-5:] for d in dates], # Only MM-DD
            'data': growth_data,
            'messages_data': messages_data
        },
        'languages': {
            'labels': lang_labels,
            'data': lang_data
        }
    })


@main_bp.route('/api/dashboard/refresh')
@login_required
def dashboard_api():
    """API endpoint for dashboard data refresh"""
    bots = Bot.query.filter_by(user_id=current_user.id).all()
    active_bots = sum(1 for bot in bots if bot.is_active)
    
    return jsonify({
        'bot_count': len(bots),
        'active_bots': active_bots,
        'subscription_type': current_user.subscription_type,
        'subscription_active': current_user.subscription_active()
    })
