"""
CRM (Customer Relationship Management) routes
"""
from flask import Blueprint, jsonify, abort
from flask_login import login_required, current_user
import json
import logging

crm_bp = Blueprint('crm', __name__)
logger = logging.getLogger(__name__)

@crm_bp.route('/bot/<int:bot_id>/customers')
@login_required
def get_customers(bot_id):
    """Get all customers and their order history for a bot (JSON API)"""
    from models import Bot, BotCustomer, MiniAppOrder
    
    bot = Bot.query.get_or_404(bot_id)
    # Check access rights: owner or admin
    if bot.user_id != current_user.id and not current_user.is_admin:
        abort(403)
        
    # Check premium sub requirement
    owner_sub = (bot.owner.subscription_type or 'free').lower().strip()
    if owner_sub not in ['premium', 'admin']:
        return jsonify({'error': 'Ushbu xususiyat faqat Premium ta\'rifida mavjud'}), 403
    
    # 1. Get all BotCustomers for this bot
    customers = BotCustomer.query.filter_by(bot_id=bot_id).order_by(
        BotCustomer.last_interaction.desc()
    ).all()
    
    # 2. Get all Orders for this bot
    orders = MiniAppOrder.query.filter_by(bot_id=bot_id).order_by(
        MiniAppOrder.created_at.desc()
    ).all()
    
    # Map orders by telegram_user_id
    orders_by_customer = {}
    for o in orders:
        if not o.telegram_user_id:
            continue
            
        tid = str(o.telegram_user_id)
        if tid not in orders_by_customer:
            orders_by_customer[tid] = {
                'total_spent': 0,
                'order_count': 0,
                'orders_list': []
            }
            
        # Parse items for order history display
        try:
            items = json.loads(o.items) if o.items else []
        except Exception:
            items = []
            
        orders_by_customer[tid]['total_spent'] += (o.total_amount or 0)
        orders_by_customer[tid]['order_count'] += 1
        orders_by_customer[tid]['orders_list'].append({
            'id': o.id,
            'date': o.created_at.strftime('%d.%m.%Y %H:%M') if o.created_at else '',
            'status': o.status,
            'total': o.total_amount or 0,
            'items_summary': ", ".join([f"{i.get('name')} x{i.get('quantity')}" for i in items])
        })
    
    # 3. Combine customer data with order data
    result = []
    
    # First, add all known BotCustomers
    processed_tids = set()
    for c in customers:
        tid = str(c.platform_user_id)
        processed_tids.add(tid)
        
        ord_data = orders_by_customer.get(tid, {'total_spent': 0, 'order_count': 0, 'orders_list': []})
        
        result.append({
            'source': 'telegram',
            'telegram_id': tid,
            'name': c.display_name,
            'username': c.username or '',
            'language': c.language or 'uz',
            'message_count': c.message_count or 0,
            'first_interaction': c.first_interaction.strftime('%d.%m.%Y') if c.first_interaction else '',
            'last_interaction': c.last_interaction.strftime('%d.%m.%Y %H:%M') if c.last_interaction else '',
            'total_spent': ord_data['total_spent'],
            'order_count': ord_data['order_count'],
            'orders_history': ord_data['orders_list']
        })
        
    # Second, add any customers who have Orders but NO BotCustomer record (edge case fallback)
    for tid, ord_data in orders_by_customer.items():
        if tid not in processed_tids:
            # Find the most recent order for this customer to extract their name
            last_order = next((o for o in orders if str(o.telegram_user_id) == tid), None)
            name = last_order.customer_name if last_order else f"Mijoz {tid}"
            
            result.append({
                'source': 'miniapp_only',
                'telegram_id': tid,
                'name': name,
                'username': '',
                'language': 'uz',
                'message_count': 0,
                'first_interaction': ord_data['orders_list'][-1]['date'] if ord_data['orders_list'] else '',
                'last_interaction': ord_data['orders_list'][0]['date'] if ord_data['orders_list'] else '',
                'total_spent': ord_data['total_spent'],
                'order_count': ord_data['order_count'],
                'orders_history': ord_data['orders_list']
            })
            
    # Sort the combined list by 'last_interaction' or 'total_spent'
    # Default sorting: active customers with physical orders go first
    result.sort(key=lambda x: (x['order_count'] > 0, x['total_spent']), reverse=True)
    
    return jsonify(result)
