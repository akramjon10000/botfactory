"""
Orders management routes for MiniApp order tracking
"""
from flask import Blueprint, jsonify, request, abort
from flask_login import login_required, current_user
import json
import logging
import requests
import os

orders_bp = Blueprint('orders', __name__)
logger = logging.getLogger(__name__)


@orders_bp.route('/bot/<int:bot_id>/orders')
@login_required
def get_orders(bot_id):
    """Get all orders for a bot (JSON API)"""
    from models import Bot, MiniAppOrder
    
    bot = Bot.query.get_or_404(bot_id)
    if bot.user_id != current_user.id and current_user.role != 'admin':
        abort(403)
    
    orders = MiniAppOrder.query.filter_by(bot_id=bot_id).order_by(
        MiniAppOrder.created_at.desc()
    ).all()
    
    result = []
    for o in orders:
        try:
            items = json.loads(o.items) if o.items else []
        except Exception:
            items = []
        
        result.append({
            'id': o.id,
            'customer_name': o.customer_name,
            'customer_phone': o.customer_phone,
            'customer_address': o.customer_address or '',
            'note': o.note or '',
            'items': items,
            'total_amount': o.total_amount or 0,
            'telegram_user_id': o.telegram_user_id,
            'status': o.status or 'pending',
            'created_at': o.created_at.strftime('%d.%m.%Y %H:%M') if o.created_at else '',
        })
    
    return jsonify(result)


@orders_bp.route('/bot/<int:bot_id>/orders/<int:order_id>/status', methods=['POST'])
@login_required
def update_order_status(bot_id, order_id):
    """Update order status and notify customer via Telegram"""
    from models import Bot, MiniAppOrder
    from app import db
    
    bot = Bot.query.get_or_404(bot_id)
    if bot.user_id != current_user.id and current_user.role != 'admin':
        abort(403)
    
    order = MiniAppOrder.query.get_or_404(order_id)
    if order.bot_id != bot_id:
        abort(404)
    
    data = request.get_json()
    new_status = data.get('status')
    
    valid_statuses = ['pending', 'confirmed', 'preparing', 'delivered', 'cancelled']
    if new_status not in valid_statuses:
        return jsonify({'error': 'Noto\'g\'ri status'}), 400
    
    old_status = order.status
    order.status = new_status
    db.session.commit()
    
    # Send notification to customer via Telegram
    if order.telegram_user_id and bot.telegram_token:
        try:
            notify_customer_status(bot.telegram_token, order.telegram_user_id, order, new_status)
        except Exception as e:
            logger.error(f"Failed to notify customer about status change: {e}")
    
    logger.info(f"Order #{order.id} status changed: {old_status} -> {new_status}")
    
    return jsonify({
        'success': True,
        'order_id': order.id,
        'new_status': new_status
    })


def notify_customer_status(bot_token, chat_id, order, new_status):
    """Send order status update to customer via Telegram"""
    status_messages = {
        'confirmed': f"✅ Buyurtmangiz #{order.id} qabul qilindi! Tez orada tayyorlanadi.",
        'preparing': f"👨‍🍳 Buyurtmangiz #{order.id} tayyorlanmoqda...",
        'delivered': f"📦 Buyurtmangiz #{order.id} yetkazib berildi! Xaridingiz uchun rahmat! 🙏",
        'cancelled': f"❌ Buyurtmangiz #{order.id} bekor qilindi. Noqulaylik uchun uzr so'raymiz.",
        'pending': f"🕐 Buyurtmangiz #{order.id} kutilmoqda."
    }
    
    message = status_messages.get(new_status, f"Buyurtmangiz #{order.id} holati: {new_status}")
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    try:
        requests.post(url, json={
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }, timeout=10)
    except Exception as e:
        logger.error(f"Telegram notification error: {e}")
