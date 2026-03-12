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
    from flask import send_from_directory
    import os
    base_dir = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    miniapp_dir = os.path.join(base_dir, 'static', 'miniapp')
    return send_from_directory(miniapp_dir, 'index.html')


@miniapp_bp.route('/business/<int:bot_id>')
def get_business_info(bot_id):
    """Get business information for a bot"""
    try:
        from models import Bot
        bot = Bot.query.get(bot_id)
        
        if not bot:
            return jsonify({'error': 'Bot topilmadi'}), 404
        
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
        from models import KnowledgeBase
        
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
        from models import Bot
        import os
        
        bot = Bot.query.get(bot_id)
        
        if not bot:
            return jsonify({'error': 'Bot topilmadi'}), 404
        
        # Get contact info from bot owner
        phone = ''
        telegram = ''
        address = 'Ko\'rsatilmagan'
        working_hours = '09:00 - 18:00'
        
        if bot.owner:
            phone = bot.owner.phone_number or ''
            telegram = bot.owner.telegram_id or ''
        
        # Fallback to env if owner has no info
        if not phone:
            phone = os.environ.get('SUPPORT_PHONE', '+998996448444')
        if not telegram:
            telegram = os.environ.get('SUPPORT_TELEGRAM', 'https://t.me/akramjon0011')
        
        # Try to get working hours from bot settings
        if hasattr(bot, 'working_hours') and bot.working_hours:
            working_hours = bot.working_hours
        
        return jsonify({
            'phone': phone,
            'address': address,
            'working_hours': working_hours,
            'telegram': telegram
        })
        
    except Exception as e:
        logger.error(f"Error getting contact info: {e}")
        return jsonify({
            'phone': '+998996448444',
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
        order.note = data.get('note', '')
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
