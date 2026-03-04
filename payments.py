import os
import json
import hashlib
import hmac
import logging
import requests
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, flash, redirect, url_for
from flask_login import login_required, current_user
from app import db, csrf
from models import User, Payment
from utils import generate_transaction_id, format_currency
from rate_limiter import rate_limiter, get_client_ip
from payment_security import (
    build_click_signature_payload,
    extract_click_order_id,
    extract_payme_order_id,
    extract_uzum_order_id,
    normalize_md5_signature,
    normalize_sha1_signature,
    normalize_sha256_signature,
    validate_click_payload,
    validate_payme_payload,
    validate_uzum_payload,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

payment_bp = Blueprint('payment', __name__)

class PaymeAPI:
    """Payme to'lov tizimi integratsiyasi"""
    
    def __init__(self):
        self.merchant_id = os.environ.get('PAYME_MERCHANT_ID', '')
        self.secret_key = os.environ.get('PAYME_SECRET_KEY', '')
        self.base_url = "https://checkout.paycom.uz/api"
    
    def create_payment(self, amount, order_id, return_url):
        """To'lov yaratish"""
        try:
            # Payme uchun parametrlar
            params = {
                'm': self.merchant_id,
                'ac.order_id': str(order_id),
                'a': int(amount * 100),  # Tiyin hisobida
                'c': return_url
            }
            
            # URL yaratish
            base64_params = self._encode_params(params)
            payment_url = f"https://checkout.paycom.uz/{base64_params}"
            
            logger.info(f"Payme to'lov yaratildi: {order_id}")
            return {
                'success': True,
                'payment_url': payment_url,
                'order_id': order_id
            }
            
        except Exception as e:
            logger.error(f"Payme to'lov yaratishda xato: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _encode_params(self, params):
        """Parametrlarni encode qilish"""
        import base64
        param_string = ";".join([f"{k}={v}" for k, v in params.items()])
        return base64.b64encode(param_string.encode()).decode()
    
    def verify_webhook(self, data, signature):
        """Webhook ni tasdiqlash"""
        try:
            if not self.secret_key:
                logger.error("Payme secret key configured emas")
                return False

            normalized_signature = normalize_sha1_signature(signature)
            if not normalized_signature:
                logger.error("Payme signature formati noto'g'ri")
                return False

            calculated_signature = hmac.new(
                self.secret_key.encode('utf-8'),
                data.encode('utf-8'),
                hashlib.sha1
            ).hexdigest().lower()
            
            return hmac.compare_digest(normalized_signature, calculated_signature)
        except Exception as e:
            logger.error(f"Payme webhook tasdiqlashda xato: {str(e)}")
            return False

class ClickAPI:
    """Click to'lov tizimi integratsiyasi"""
    
    def __init__(self):
        self.merchant_id = os.environ.get('CLICK_MERCHANT_ID', '')
        self.secret_key = os.environ.get('CLICK_SECRET_KEY', '')
        self.service_id = os.environ.get('CLICK_SERVICE_ID', '')
        self.base_url = "https://api.click.uz/v2"
    
    def create_payment(self, amount, order_id, return_url):
        """To'lov yaratish"""
        try:
            # Click uchun parametrlar
            params = {
                'service_id': self.service_id,
                'merchant_id': self.merchant_id,
                'amount': float(amount),
                'transaction_param': str(order_id),
                'return_url': return_url,
                'merchant_user_id': str(current_user.id) if current_user.is_authenticated else '0'
            }
            
            # Imzo yaratish
            params['sign'] = self._create_signature(params)
            
            # To'lov URL yaratish
            payment_url = f"https://my.click.uz/services/pay?{self._build_query_string(params)}"
            
            logger.info(f"Click to'lov yaratildi: {order_id}")
            return {
                'success': True,
                'payment_url': payment_url,
                'order_id': order_id
            }
            
        except Exception as e:
            logger.error(f"Click to'lov yaratishda xato: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _create_signature(self, params):
        """Click imzo yaratish"""
        sign_string = (
            f"{str(params.get('service_id', '')).strip()}"
            f"{str(params.get('merchant_id', '')).strip()}"
            f"{str(params.get('amount', '')).strip()}"
            f"{str(params.get('transaction_param', '')).strip()}"
            f"{self.secret_key}"
        )
        return hashlib.md5(sign_string.encode('utf-8')).hexdigest().lower()
    
    def _build_query_string(self, params):
        """Query string yaratish"""
        return "&".join([f"{k}={v}" for k, v in params.items()])
    
    def verify_signature(self, params):
        """Imzoni tasdiqlash"""
        try:
            if not self.secret_key:
                logger.error("Click secret key configured emas")
                return False

            received_sign = normalize_md5_signature(params.pop('sign', ''))
            if not received_sign:
                logger.error("Click signature formati noto'g'ri")
                return False

            signature_payload = build_click_signature_payload(params)
            calculated_sign = self._create_signature(signature_payload)
            return hmac.compare_digest(received_sign, calculated_sign)
        except Exception as e:
            logger.error(f"Click imzo tasdiqlashda xato: {str(e)}")
            return False

class UzumAPI:
    """Uzum to'lov tizimi integratsiyasi"""
    
    def __init__(self):
        self.merchant_id = os.environ.get('UZUM_MERCHANT_ID', '')
        self.secret_key = os.environ.get('UZUM_SECRET_KEY', '')
        self.base_url = "https://api.uzumpay.uz/v1"
    
    def create_payment(self, amount, order_id, return_url):
        """To'lov yaratish"""
        try:
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f'Bearer {self._get_access_token()}'
            }
            
            payload = {
                'merchant_id': self.merchant_id,
                'amount': int(amount * 100),  # Tiyin hisobida
                'currency': 'UZS',
                'order_id': str(order_id),
                'description': f'Chatbot Factory AI - Obuna to\'lovi #{order_id}',
                'return_url': return_url,
                'callback_url': url_for('payment.uzum_callback', _external=True)
            }
            
            response = requests.post(
                f"{self.base_url}/payments",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                logger.info(f"Uzum to'lov yaratildi: {order_id}")
                return {
                    'success': True,
                    'payment_url': result.get('payment_url'),
                    'order_id': order_id,
                    'payment_id': result.get('payment_id')
                }
            else:
                logger.error(f"Uzum API xato: {response.status_code}")
                return {'success': False, 'error': 'API xatosi'}
                
        except Exception as e:
            logger.error(f"Uzum to'lov yaratishda xato: {str(e)}")
            return {'success': False, 'error': str(e)}
    
    def _get_access_token(self):
        """Access token olish"""
        # Bu yerda OAuth2 access token olish logikasi bo'ladi
        return os.environ.get('UZUM_ACCESS_TOKEN', '')
    
    def verify_callback(self, raw_payload: str, signature: str):
        """Callback signature ni tasdiqlash (HMAC-SHA256)."""
        try:
            if not self.secret_key:
                logger.error("Uzum secret key configured emas")
                return False

            normalized_signature = normalize_sha256_signature(signature)
            if not normalized_signature:
                logger.error("Uzum callback signature formati noto'g'ri")
                return False

            if raw_payload is None:
                logger.error("Uzum callback payload topilmadi")
                return False

            expected_signature = hmac.new(
                self.secret_key.encode('utf-8'),
                raw_payload.encode('utf-8'),
                hashlib.sha256
            ).hexdigest().lower()

            return hmac.compare_digest(normalized_signature, expected_signature)
        except Exception as e:
            logger.error(f"Uzum callback tasdiqlashda xato: {str(e)}")
            return False

# Payment processor
class PaymentProcessor:
    """To'lov processori"""
    
    def __init__(self):
        self.payme = PaymeAPI()
        self.click = ClickAPI()
        self.uzum = UzumAPI()
    
    def create_payment(self, user_id, subscription_type, payment_method):
        """To'lov yaratish"""
        try:
            # Subscription narxlarini olish
            prices = {
                'starter': 165000,
                'basic': 290000,
                'premium': 590000
            }
            
            if subscription_type not in prices:
                return {'success': False, 'error': 'Noto\'g\'ri tarif turi'}
            
            amount = prices[subscription_type]
            
            # Payment record yaratish
            payment = Payment()
            payment.user_id = user_id
            payment.amount = amount
            payment.method = payment_method
            payment.subscription_type = subscription_type
            payment.status = 'pending'
            payment.transaction_id = generate_transaction_id(0)  # Temporary
            
            db.session.add(payment)
            db.session.commit()
            
            # Transaction ID ni yangilash
            payment.transaction_id = generate_transaction_id(payment.id)
            db.session.commit()
            
            # Return URL
            return_url = f'https://botfactory.uz/payment/success/{payment.id}'
            
            # To'lov yaratish
            if payment_method == 'payme':
                result = self.payme.create_payment(amount, payment.id, return_url)
            elif payment_method == 'click':
                result = self.click.create_payment(amount, payment.id, return_url)
            elif payment_method == 'uzum':
                result = self.uzum.create_payment(amount, payment.id, return_url)
            else:
                return {'success': False, 'error': 'Noto\'g\'ri to\'lov usuli'}
            
            if result['success']:
                return {
                    'success': True,
                    'payment_url': result['payment_url'],
                    'payment_id': payment.id
                }
            else:
                payment.status = 'failed'
                db.session.commit()
                return result
                
        except Exception as e:
            logger.error(f"To'lov yaratishda xato: {str(e)}")
            db.session.rollback()
            return {'success': False, 'error': str(e)}
    
    def confirm_payment(self, payment_id, transaction_data=None):
        """To'lovni tasdiqlash"""
        try:
            payment = Payment.query.get(payment_id)
            if not payment:
                return {'success': False, 'error': 'To\'lov topilmadi'}

            # Idempotency: already confirmed payments must not extend subscription again
            if payment.status == 'completed':
                return {'success': True, 'payment': payment, 'already_processed': True}

            if payment.status not in ['pending']:
                return {'success': False, 'error': f"To'lov holati noto'g'ri: {payment.status}"}
            
            # To'lovni tasdiqlash
            payment.status = 'completed'
            if transaction_data:
                payment.transaction_id = transaction_data.get('transaction_id', payment.transaction_id)
            
            # Foydalanuvchi obunasini yangilash
            user = User.query.get(payment.user_id)
            if user:
                user.subscription_type = payment.subscription_type
                user.subscription_end_date = datetime.utcnow() + timedelta(days=30)
            
            db.session.commit()
            
            # Telegram orqali to'lov haqida bildirishnoma yuborish
            if user and user.admin_chat_id:
                try:
                    from notification_service import TelegramNotificationService
                    telegram_service = TelegramNotificationService()
                    
                    payment_info = {
                        'username': user.username,
                        'amount': payment.amount,
                        'method': payment.method,
                        'subscription_type': payment.subscription_type
                    }
                    
                    telegram_service.send_payment_success_notification(
                        user.admin_chat_id, payment_info
                    )
                except Exception as tg_error:
                    logger.error(f"Telegram payment notification error: {str(tg_error)}")
            
            logger.info(f"To'lov tasdiqlandi: {payment_id}")
            return {'success': True, 'payment': payment}
            
        except Exception as e:
            logger.error(f"To'lovni tasdiqlashda xato: {str(e)}")
            db.session.rollback()
            return {'success': False, 'error': str(e)}

# Flask routes
processor = PaymentProcessor()

@payment_bp.route('/create_payment', methods=['POST'])
@login_required
def create_payment():
    """To'lov yaratish route"""
    try:
        # Form dan ma'lumotlarni olish
        subscription_type = request.form.get('subscription_type')
        method = request.form.get('method')
        
        if not subscription_type or not method:
            flash('Iltimos, barcha maydonlarni to\'ldiring!', 'error')
            return redirect(url_for('main.subscription'))
        
        result = processor.create_payment(
            user_id=current_user.id,
            subscription_type=subscription_type,
            payment_method=method.lower()
        )
        
        if result['success']:
            return redirect(result['payment_url'])
        else:
            flash(f'To\'lov yaratishda xato: {result["error"]}', 'error')
            return redirect(url_for('main.subscription'))
            
    except Exception as e:
        logger.error(f"Payment creation route error: {str(e)}")
        flash('To\'lov yaratishda xato yuz berdi!', 'error')
        return redirect(url_for('main.subscription'))

@payment_bp.route('/success/<int:payment_id>')
def payment_success(payment_id):
    """To'lov muvaffaqiyatli yakunlanganda"""
    try:
        payment = Payment.query.get(payment_id)
        if not payment:
            flash('To\'lov topilmadi!', 'error')
            return redirect(url_for('main.subscription'))

        # Security: never confirm payment from redirect URL; webhook must confirm it
        if payment.status == 'completed':
            flash('To\'lov muvaffaqiyatli tasdiqlandi!', 'success')
        elif payment.status == 'pending':
            flash('To\'lov qabul qilindi. To\'lov tizimidan tasdiq kutilmoqda.', 'info')
        else:
            flash(f"To'lov holati: {payment.status}", 'warning')
            
    except Exception as e:
        logger.error(f"Payment success error: {str(e)}")
        flash('To\'lov jarayonida xato!', 'error')
    
    return redirect(url_for('main.dashboard'))

@payment_bp.route('/webhook/payme', methods=['POST'])
@csrf.exempt
def payme_webhook():
    """Payme webhook handler"""
    try:
        client_ip = get_client_ip(request)
        allowed, retry_after = rate_limiter.is_allowed(
            key=f"payme_webhook:{client_ip}",
            limit=360,
            window_seconds=60
        )
        if not allowed:
            return jsonify({'error': 'Rate limited', 'retry_after': retry_after}), 429

        data = request.get_data(as_text=True)
        signature = request.headers.get('X-PaycomSignature', '')
        
        if not processor.payme.verify_webhook(data, signature):
            return jsonify({'error': 'Invalid signature'}), 400
        
        webhook_data = json.loads(data)
        if not validate_payme_payload(webhook_data):
            return jsonify({'error': 'Invalid payload format'}), 400
        
        # Webhook ni qayta ishlash
        method = webhook_data.get('method')
        if method == 'CheckTransaction':
            # To'lovni tekshirish
            pass
        elif method == 'CreateTransaction':
            # To'lovni yaratish
            pass
        elif method == 'PerformTransaction':
            # To'lovni amalga oshirish
            order_id = extract_payme_order_id(webhook_data)
            if order_id is None:
                return jsonify({'error': 'Invalid order_id'}), 400
            processor.confirm_payment(order_id, webhook_data)
        
        return jsonify({'result': {'success': True}})
        
    except json.JSONDecodeError:
        return jsonify({'error': 'Invalid JSON payload'}), 400
    except Exception as e:
        logger.error(f"Payme webhook error: {str(e)}")
        return jsonify({'error': 'Internal error'}), 500

@payment_bp.route('/webhook/click', methods=['POST'])
@csrf.exempt
def click_webhook():
    """Click webhook handler"""
    try:
        client_ip = get_client_ip(request)
        allowed, retry_after = rate_limiter.is_allowed(
            key=f"click_webhook:{client_ip}",
            limit=360,
            window_seconds=60
        )
        if not allowed:
            return jsonify({'error': -1, 'error_note': 'Rate limited', 'retry_after': retry_after}), 429

        params = request.form.to_dict()
        if not validate_click_payload(params, processor.click.service_id, processor.click.merchant_id):
            return jsonify({'error': -1, 'error_note': 'Invalid payload format'})
        
        if not processor.click.verify_signature(params.copy()):
            return jsonify({'error': -1, 'error_note': 'Invalid signature'})
        
        action = str(params.get('action', '')).strip()
        
        if action == '1':  # To'lovni tasdiqash
            order_id = extract_click_order_id(params)
            if order_id is None:
                return jsonify({'error': -1, 'error_note': 'Invalid order_id'})
            result = processor.confirm_payment(order_id, params)
            if result['success']:
                return jsonify({'error': 0, 'error_note': 'Success'})
        
        return jsonify({'error': -1, 'error_note': 'Unknown action'})
        
    except Exception as e:
        logger.error(f"Click webhook error: {str(e)}")
        return jsonify({'error': -1, 'error_note': 'Internal error'})

@payment_bp.route('/webhook/uzum', methods=['POST'])
@csrf.exempt
def uzum_callback():
    """Uzum callback handler"""
    try:
        client_ip = get_client_ip(request)
        allowed, retry_after = rate_limiter.is_allowed(
            key=f"uzum_webhook:{client_ip}",
            limit=360,
            window_seconds=60
        )
        if not allowed:
            return jsonify({'status': 'error', 'message': 'Rate limited', 'retry_after': retry_after}), 429

        raw_payload = request.get_data(as_text=True)
        signature = (
            request.headers.get('X-Uzum-Signature') or
            request.headers.get('X-Signature') or
            request.headers.get('Signature') or
            ''
        )

        if not processor.uzum.verify_callback(raw_payload, signature):
            return jsonify({'status': 'error', 'message': 'Invalid signature'}), 400

        data = request.get_json(silent=True)
        if data is None:
            return jsonify({'status': 'error', 'message': 'Invalid JSON payload'}), 400

        if not validate_uzum_payload(data):
            return jsonify({'status': 'error', 'message': 'Invalid payload format'}), 400
        
        order_id = extract_uzum_order_id(data)
        status = str(data.get('status', '')).strip().lower()
        
        if status == 'success':
            result = processor.confirm_payment(int(order_id), data)
            if result['success']:
                return jsonify({'status': 'ok'})
            return jsonify({'status': 'error'})

        # failed/pending/cancelled callbacklar ham qabul qilinadi (ack)
        if status in {'failed', 'pending', 'cancelled'}:
            return jsonify({'status': 'ok'})
        
        return jsonify({'status': 'error'})
        
    except Exception as e:
        logger.error(f"Uzum callback error: {str(e)}")
        return jsonify({'status': 'error'}), 500

@payment_bp.route('/status/<int:payment_id>')
@login_required
def payment_status(payment_id):
    """To'lov holatini tekshirish"""
    try:
        payment = Payment.query.get_or_404(payment_id)
        
        if payment.user_id != current_user.id and not current_user.is_admin:
            flash('Sizda bu to\'lovni ko\'rish huquqi yo\'q!', 'error')
            return redirect(url_for('main.dashboard'))
        
        return jsonify({
            'id': payment.id,
            'amount': payment.amount,
            'method': payment.method,
            'status': payment.status,
            'created_at': payment.created_at.isoformat(),
            'subscription_type': payment.subscription_type
        })
        
    except Exception as e:
        logger.error(f"Payment status error: {str(e)}")
        return jsonify({'error': 'To\'lov ma\'lumotlarini olishda xato'}), 500
