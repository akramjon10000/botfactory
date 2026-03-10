import os
import json
import logging
import requests
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, render_template_string
from flask_login import login_required, current_user
from app import db, app
from models import User, Bot, Payment
from utils import format_currency, format_date

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

marketing_bp = Blueprint('marketing', __name__)

class EmailService:
    """Email yuborish xizmati"""
    
    def __init__(self):
        self.smtp_host = os.environ.get('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        self.smtp_user = os.environ.get('SMTP_USER', '')
        self.smtp_password = os.environ.get('SMTP_PASSWORD', '')
        self.from_email = os.environ.get('FROM_EMAIL', 'noreply@chatbotfactory.uz')
        
        # SendGrid API (alternative)
        self.sendgrid_api_key = os.environ.get('SENDGRID_API_KEY', '')
        self.sendgrid_url = "https://api.sendgrid.com/v3/mail/send"
    
    def send_smtp_email(self, to_email, subject, html_content, text_content=""):
        """SMTP orqali email yuborish"""
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            
            if not self.smtp_user or not self.smtp_password:
                logger.error("SMTP credentials not configured")
                return False
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = to_email
            
            # Add text and HTML parts
            if text_content:
                text_part = MIMEText(text_content, 'plain', 'utf-8')
                msg.attach(text_part)
            
            if html_content:
                html_part = MIMEText(html_content, 'html', 'utf-8')
                msg.attach(html_part)
            
            # Send email
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"SMTP email sent to {to_email}")
            return True
            
        except Exception as e:
            logger.error(f"SMTP email error: {str(e)}")
            return False
    
    def send_sendgrid_email(self, to_email, subject, html_content, text_content=""):
        """SendGrid API orqali email yuborish"""
        try:
            headers = {
                'Authorization': f'Bearer {self.sendgrid_api_key}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'personalizations': [{
                    'to': [{'email': to_email}],
                    'subject': subject
                }],
                'from': {'email': self.from_email, 'name': 'Chatbot Factory AI'},
                'content': [
                    {'type': 'text/plain', 'value': text_content},
                    {'type': 'text/html', 'value': html_content}
                ]
            }
            
            response = requests.post(
                self.sendgrid_url,
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 202:
                logger.info(f"SendGrid email sent to {to_email}")
                return True
            else:
                logger.error(f"SendGrid error: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"SendGrid email error: {str(e)}")
            return False
    
    def send_email(self, to_email, subject, html_content, text_content=""):
        """Email yuborish (SMTP yoki SendGrid)"""
        # O'zbekistonda SMTP ni afzal ko'ramiz
        if self.smtp_user and self.smtp_password:
            return self.send_smtp_email(to_email, subject, html_content, text_content)
        elif self.sendgrid_api_key:
            return self.send_sendgrid_email(to_email, subject, html_content, text_content)
        else:
            logger.error("No email service configured (SMTP or SendGrid)")
            return False

class SMSService:
    """SMS yuborish xizmati (O'zbekiston)"""
    
    def __init__(self):
        # Uzbekistan SMS providers
        self.eskiz_email = os.environ.get('ESKIZ_EMAIL', '')
        self.eskiz_password = os.environ.get('ESKIZ_PASSWORD', '')
        self.eskiz_api_url = "https://notify.eskiz.uz/api"
        self.eskiz_token = None
        
        # PlayMobile SMS
        self.playmobile_login = os.environ.get('PLAYMOBILE_LOGIN', '')
        self.playmobile_password = os.environ.get('PLAYMOBILE_PASSWORD', '')
        self.playmobile_api_url = "https://api.playmobile.uz"
    
    def get_eskiz_token(self):
        """Eskiz SMS token olish"""
        try:
            response = requests.post(
                f"{self.eskiz_api_url}/auth/login",
                data={
                    'email': self.eskiz_email,
                    'password': self.eskiz_password
                },
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                self.eskiz_token = data.get('data', {}).get('token')
                return True
            return False
            
        except Exception as e:
            logger.error(f"Eskiz token error: {str(e)}")
            return False
    
    def send_eskiz_sms(self, phone_number, message):
        """Eskiz orqali SMS yuborish"""
        try:
            if not self.eskiz_token:
                if not self.get_eskiz_token():
                    return False
            
            headers = {
                'Authorization': f'Bearer {self.eskiz_token}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'mobile_phone': phone_number,
                'message': message,
                'from': '4546',
                'callback_url': 'https://botfactory.uz/marketing/sms/callback'
            }
            
            response = requests.post(
                f"{self.eskiz_api_url}/message/sms/send",
                headers=headers,
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'success':
                    logger.info(f"Eskiz SMS sent to {phone_number}")
                    return True
            
            logger.error(f"Eskiz SMS error: {response.status_code}")
            return False
            
        except Exception as e:
            logger.error(f"Eskiz SMS error: {str(e)}")
            return False
    
    def send_playmobile_sms(self, phone_number, message):
        """PlayMobile orqali SMS yuborish"""
        try:
            data = {
                'login': self.playmobile_login,
                'password': self.playmobile_password,
                'data': [{
                    'phone': phone_number,
                    'text': message
                }]
            }
            
            response = requests.post(
                f"{self.playmobile_api_url}/send",
                json=data,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                if result.get('status') == 'ok':
                    logger.info(f"PlayMobile SMS sent to {phone_number}")
                    return True
            
            logger.error(f"PlayMobile SMS error: {response.status_code}")
            return False
            
        except Exception as e:
            logger.error(f"PlayMobile SMS error: {str(e)}")
            return False
    
    def send_sms(self, phone_number, message):
        """SMS yuborish"""
        # Clean phone number
        phone_number = phone_number.replace('+', '').replace(' ', '').replace('-', '')
        
        # Try Eskiz first, then PlayMobile
        if self.eskiz_email:
            return self.send_eskiz_sms(phone_number, message)
        elif self.playmobile_login:
            return self.send_playmobile_sms(phone_number, message)
        else:
            logger.error("No SMS provider configured")
            return False

class MarketingCampaigns:
    """Marketing kampaniyalari"""
    
    def __init__(self):
        self.email_service = EmailService()
        self.sms_service = SMSService()
    
    def send_welcome_email(self, user):
        """Xush kelibsiz emaili"""
        subject = "🎉 Chatbot Factory AI ga xush kelibsiz!"
        
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Xush kelibsiz</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #2563eb;">🤖 Chatbot Factory AI</h1>
                <h2>Salom, {{ username }}!</h2>
                
                <p>Chatbot Factory AI platformasiga xush kelibsiz! Siz endi o'zingizning AI chatbotlaringizni yaratishingiz mumkin.</p>
                
                <div style="background: #f3f4f6; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3>🎁 7 kunlik bepul sinov:</h3>
                    <ul>
                        <li>✅ 1 ta bot yaratish</li>
                        <li>✅ Telegram integratsiyasi</li>
                        <li>✅ O'zbek tilida AI javoblar</li>
                        <li>✅ Bilim bazasi yuklash</li>
                    </ul>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="https://botfactory.uz/dashboard" 
                       style="background: #2563eb; color: white; padding: 15px 30px; 
                              text-decoration: none; border-radius: 8px; font-weight: bold;">
                        🚀 Birinchi botingizni yarating
                    </a>
                </div>
                
                <h3>💎 Premium imkoniyatlar:</h3>
                <ul>
                    <li>🤖 5 ta bot yaratish</li>
                    <li>🌍 3 tilda AI (O'zbek/Rus/Ingliz)</li>
                    <li>📱 Barcha platformalar yordami (Tez kunda)</li>
                    <li>📞 Prioritet yordam</li>
                </ul>
                
                <p>Savollaringiz bo'lsa, <a href="mailto:support@botfactory.uz">support@botfactory.uz</a> ga yozing.</p>
                
                <hr style="margin: 30px 0;">
                <p style="font-size: 12px; color: #666;">
                    Chatbot Factory AI - O'zbekistondagi birinchi AI chatbot platformasi<br>
                    <a href="https://botfactory.uz">botfactory.uz</a>
                </p>
            </div>
        </body>
        </html>
        """
        
        html_content = render_template_string(html_template, username=user.username)
        
        text_content = f"""
Salom, {user.username}!

Chatbot Factory AI ga xush kelibsiz! Siz endi o'zingizning AI chatbotlaringizni yaratishingiz mumkin.

7 kunlik bepul sinov:
- 1 ta bot yaratish
- Telegram integratsiyasi  
- O'zbek tilida AI javoblar

Birinchi botingizni yaratish: https://botfactory.uz/dashboard

Savollar: support@botfactory.uz
        """
        
        return self.email_service.send_email(user.email, subject, html_content, text_content)
    
    def send_subscription_reminder(self, user, days_left):
        """Obuna tugashi haqida eslatma"""
        subject = f"⏰ Obunangiz {days_left} kundan keyin tugaydi"
        
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Obuna eslatmasi</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #dc2626;">⏰ Obuna tugash eslatmasi</h1>
                
                <p>Hurmatli {{ username }},</p>
                
                <div style="background: #fef2f2; border-left: 4px solid #dc2626; padding: 15px; margin: 20px 0;">
                    <p><strong>Sizning {{ subscription_type }} obunangiz {{ days_left }} kundan keyin tugaydi!</strong></p>
                    <p>Tugash sanasi: {{ end_date }}</p>
                </div>
                
                <p>Xizmatlarimizdan uzluksiz foydalanish uchun obunangizni yangilang:</p>
                
                <div style="display: flex; gap: 10px; margin: 30px 0; flex-wrap: wrap;">
                    <div style="flex: 1; min-width: 180px; background: #ecfccb; padding: 20px; border-radius: 8px;">
                        <h3 style="color: #65a30d;">🚀 Starter - 165,000 so'm/oy</h3>
                        <ul>
                            <li>1 ta bot</li>
                            <li>Faqat Telegram</li>
                            <li>3 til AI</li>
                            <li>Bilim bazasi</li>
                        </ul>
                    </div>
                    <div style="flex: 1; min-width: 180px; background: #f3f4f6; padding: 20px; border-radius: 8px;">
                        <h3 style="color: #059669;">💰 Basic - 290,000 so'm/oy</h3>
                        <ul>
                            <li>1 ta bot</li>
                            <li>Barcha platformalar</li>
                            <li>3 til AI</li>
                            <li>Bilim bazasi</li>
                        </ul>
                    </div>
                    <div style="flex: 1; min-width: 180px; background: #fef3c7; padding: 20px; border-radius: 8px;">
                        <h3 style="color: #d97706;">💎 Premium - 590,000 so'm/oy</h3>
                        <ul>
                            <li>5 ta bot</li>
                            <li>Barcha platformalar</li>
                            <li>3 til AI</li>
                            <li>Prioritet yordam</li>
                        </ul>
                    </div>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="https://botfactory.uz/subscription" 
                       style="background: #dc2626; color: white; padding: 15px 30px; 
                              text-decoration: none; border-radius: 8px; font-weight: bold;">
                        💳 Obunani yangilash
                    </a>
                </div>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #495057;">📞 Murojaat uchun:</h3>
                    <p><strong>Telefon:</strong> <a href="tel:+998996448444">+998 99 644-84-44</a></p>
                    <p><strong>Telegram:</strong> <a href="https://t.me/akramjon0011">@akramjon0011</a></p>
                    <p><strong>Email:</strong> <a href="mailto:support@botfactory.uz">support@botfactory.uz</a></p>
                </div>
            </div>
        </body>
        </html>
        """
        
        html_content = render_template_string(
            html_template,
            username=user.username,
            subscription_type=user.subscription_type.title(),
            days_left=days_left,
            end_date=format_date(user.subscription_end_date)
        )
        
        return self.email_service.send_email(user.email, subject, html_content)
    
    def send_trial_ending_sms(self, user, days_left):
        """Sinov tugashi SMS"""
        message = f"""🤖 Chatbot Factory AI

Hurmatli {user.username}, sinov muddatingiz {days_left} kundan keyin tugaydi.

💰 Ta'riflar:
Basic: 290,000 so'm/oy
Premium: 590,000 so'm/oy

🌐 To'lov: botfactory.uz

📞 Murojaat:
+998 99 644-84-44
https://t.me/akramjon0011"""
        
        # Get phone number from user
        phone = getattr(user, 'phone_number', None)
        if phone:
            return self.sms_service.send_sms(phone, message)
        return False
    
    def send_free_user_marketing(self, user):
        """Bepul foydalanuvchilarga marketing"""
        subject = "🚀 Botlaringizni yangi darajaga ko'taring!"
        
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Premium taklif</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #7c3aed;">🚀 Yangi imkoniyatlar!</h1>
                
                <p>Salom, {{ username }}!</p>
                
                <p>Siz Chatbot Factory AI dan yaxshi foydalanyapsiz. Ko'proq imkoniyatlar qanday?</p>
                
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                           color: white; padding: 30px; border-radius: 15px; margin: 30px 0;">
                    <h2 style="margin-top: 0;">✨ Premium bilan yangi dunyo:</h2>
                    <ul style="font-size: 16px;">
                        <li>🤖 <strong>5 ta bot</strong> yarating</li>
                        <li>🌍 <strong>3 tilda AI</strong> (O'zbek/Rus/Ingliz)</li>
                        <li>📞 <strong>Prioritet yordam</strong></li>
                        <li>📊 <strong>Tahlil va statistika</strong></li>
                    </ul>
                </div>
                
                <div style="background: #fef9e7; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3>🎁 Maxsus taklif:</h3>
                    <p>Birinchi oy uchun <strong>30% chegirma</strong>!</p>
                    <p>Premium: <strike>590,000</strike> → <strong style="color: #dc2626;">413,000 so'm</strong></p>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="https://botfactory.uz/subscription?promo=PREMIUM30" 
                       style="background: #7c3aed; color: white; padding: 15px 30px; 
                              text-decoration: none; border-radius: 8px; font-weight: bold;">
                        💎 Premium olish
                    </a>
                </div>
                
                <p><small>Taklifning amal qilish muddati: {{ expiry_date }}</small></p>
            </div>
        </body>
        </html>
        """
        
        expiry_date = (datetime.utcnow() + timedelta(days=7)).strftime("%d.%m.%Y")
        html_content = render_template_string(
            html_template, 
            username=user.username,
            expiry_date=expiry_date
        )
        
        return self.email_service.send_email(user.email, subject, html_content)
    
    def send_subscription_expired_notification(self, user):
        """Bepul ta'rif tugagan kun uchun eslatma"""
        subject = "⚠️ Bepul sinov muddati tugadi - Premium'ga o'ting!"
        
        html_template = """
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Bepul sinov tugadi</title>
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
                <h1 style="color: #dc2626;">⚠️ Bepul sinov muddati tugadi</h1>
                
                <p>Hurmatli {{ username }},</p>
                
                <div style="background: #fee2e2; border: 2px solid #fca5a5; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <p><strong>🕐 Sizning 7 kunlik bepul sinov muddatingiz bugun tugadi!</strong></p>
                    <p>Barcha premium imkoniyatlardan foydalanishni davom ettirish uchun to'lov ta'rifini tanlang.</p>
                </div>
                
                <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); 
                           color: white; padding: 30px; border-radius: 15px; margin: 30px 0;">
                    <h2 style="margin-top: 0; color: white;">🚀 Premium ta'riflari:</h2>
                    
                    <div style="background: rgba(255,255,255,0.1); padding: 15px; border-radius: 8px; margin: 15px 0;">
                        <h3 style="color: #fef3c7; margin-top: 0;">💰 Basic - 290,000 so'm/oy</h3>
                        <ul style="color: white;">
                            <li>✅ 1 ta bot yaratish</li>
                            <li>✅ Barcha platformalar yordami (Tez kunda)</li>
                            <li>✅ 3 tilda AI (O'zbek/Rus/Ingliz)</li>
                            <li>✅ Bilim bazasi yuklash</li>
                        </ul>
                    </div>
                    
                    <div style="background: rgba(255,255,255,0.1); padding: 15px; border-radius: 8px; margin: 15px 0;">
                        <h3 style="color: #fde68a; margin-top: 0;">💎 Premium - 590,000 so'm/oy</h3>
                        <ul style="color: white;">
                            <li>✅ 5 ta bot yaratish</li>
                            <li>✅ Barcha platformalar</li>
                            <li>✅ 3 tilda AI</li>
                            <li>✅ Prioritet yordam</li>
                            <li>✅ Tahlil va statistika</li>
                        </ul>
                    </div>
                </div>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="https://botfactory.uz/subscription" 
                       style="background: #dc2626; color: white; padding: 20px 40px; 
                              text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 18px;">
                        💳 Hozir to'lash va davom ettirish
                    </a>
                </div>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
                    <h3 style="color: #495057;">📞 Murojaat uchun:</h3>
                    <p><strong>Telefon:</strong> <a href="tel:+998996448444">+998 99 644-84-44</a></p>
                    <p><strong>Telegram:</strong> <a href="https://t.me/akramjon0011">@akramjon0011</a></p>
                    <p><strong>Email:</strong> <a href="mailto:support@botfactory.uz">support@botfactory.uz</a></p>
                </div>
                
                <p style="font-size: 12px; color: #666; text-align: center;">
                    Chatbot Factory AI - O'zbekistondagi birinchi AI chatbot platformasi<br>
                    <a href="https://botfactory.uz">botfactory.uz</a>
                </p>
            </div>
        </body>
        </html>
        """
        
        html_content = render_template_string(html_template, username=user.username)
        
        text_content = f"""Hurmatli {user.username},

🕐 Sizning 7 kunlik bepul sinov muddatingiz bugun tugadi!

🚀 Premium ta'riflari:
💰 Basic - 290,000 so'm/oy
💎 Premium - 590,000 so'm/oy

💳 To'lov: https://botfactory.uz/subscription

📞 Murojaat uchun:
+998 99 644-84-44
https://t.me/akramjon0011"""
        
        # Email yuborish
        email_success = self.email_service.send_email(user.email, subject, html_content, text_content)
        
        # SMS ham yuborish
        sms_message = f"""🤖 Chatbot Factory AI

{user.username}, 7 kunlik bepul sinov tugadi!

💰 Basic: 290,000 so'm
💎 Premium: 590,000 so'm

🌐 To'lov: botfactory.uz

📞 +998 99 644-84-44
📱 https://t.me/akramjon0011"""
        
        # SMS yuborish (agar phone_number mavjud bo'lsa)
        phone = getattr(user, 'phone_number', None)
        sms_success = False
        if phone:
            sms_success = self.sms_service.send_sms(phone, sms_message)
        
        return email_success or sms_success
    
    def send_bulk_marketing(self, user_ids, campaign_type):
        """Ommaviy marketing xabarlari"""
        success_count = 0
        total_count = len(user_ids)
        
        with app.app_context():
            users = User.query.filter(User.id.in_(user_ids)).all()
            
            for user in users:
                try:
                    if campaign_type == 'welcome':
                        success = self.send_welcome_email(user)
                    elif campaign_type == 'marketing':
                        success = self.send_free_user_marketing(user)
                    else:
                        success = False
                    
                    if success:
                        success_count += 1
                        
                except Exception as e:
                    logger.error(f"Bulk marketing error for user {user.id}: {str(e)}")
        
        return {
            'total': total_count,
            'success': success_count,
            'failed': total_count - success_count
        }

# Marketing campaigns instance
campaigns = MarketingCampaigns()

# Flask routes
@marketing_bp.route('/send/welcome/<int:user_id>', methods=['POST'])
@login_required
def send_welcome(user_id):
    """Xush kelibsiz emaili yuborish"""
    if not current_user.is_admin:
        return jsonify({'error': 'Ruxsat yo\'q'}), 403
    
    try:
        with app.app_context():
            user = User.query.get_or_404(user_id)
            success = campaigns.send_welcome_email(user)
            
            return jsonify({
                'success': success,
                'message': 'Xabar yuborildi' if success else 'Xabar yuborishda xato'
            })
    
    except Exception as e:
        logger.error(f"Send welcome error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@marketing_bp.route('/send/reminder/<int:user_id>/<int:days>', methods=['POST'])
@login_required  
def send_reminder(user_id, days):
    """Obuna eslatmasi yuborish"""
    if not current_user.is_admin:
        return jsonify({'error': 'Ruxsat yo\'q'}), 403
    
    try:
        with app.app_context():
            user = User.query.get_or_404(user_id)
            success = campaigns.send_subscription_reminder(user, days)
            
            return jsonify({
                'success': success,
                'message': 'Eslatma yuborildi' if success else 'Eslatma yuborishda xato'
            })
    
    except Exception as e:
        logger.error(f"Send reminder error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@marketing_bp.route('/send/bulk', methods=['POST'])
@login_required
def send_bulk():
    """Ommaviy xabar yuborish"""
    if not current_user.is_admin:
        return jsonify({'error': 'Ruxsat yo\'q'}), 403
    
    try:
        data = request.get_json()
        user_ids = data.get('user_ids', [])
        campaign_type = data.get('campaign_type', 'marketing')
        
        result = campaigns.send_bulk_marketing(user_ids, campaign_type)
        
        return jsonify({
            'success': True,
            'result': result
        })
    
    except Exception as e:
        logger.error(f"Bulk marketing error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@marketing_bp.route('/sms/callback', methods=['POST'])
def sms_callback():
    """SMS yuborish callback"""
    try:
        data = request.get_json()
        logger.info(f"SMS callback: {data}")
        return jsonify({'status': 'ok'})
    
    except Exception as e:
        logger.error(f"SMS callback error: {str(e)}")
        return jsonify({'error': str(e)}), 500

@marketing_bp.route('/stats')
@login_required
def marketing_stats():
    """Marketing statistikalari"""
    if not current_user.is_admin:
        return jsonify({'error': 'Ruxsat yo\'q'}), 403
    
    try:
        with app.app_context():
            stats = {
                'total_users': User.query.count(),
                'free_users': User.query.filter_by(subscription_type='free').count(),
                'trial_ending_soon': User.query.filter(
                    User.subscription_type == 'free',
                    User.subscription_end_date <= datetime.utcnow() + timedelta(days=3),
                    User.subscription_end_date > datetime.utcnow()
                ).count(),
                'expired_subscriptions': User.query.filter(
                    User.subscription_end_date <= datetime.utcnow(),
                    User.subscription_type.in_(['basic', 'premium'])
                ).count()
            }
            
            return jsonify(stats)
    
    except Exception as e:
        logger.error(f"Marketing stats error: {str(e)}")
        return jsonify({'error': str(e)}), 500