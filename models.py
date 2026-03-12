from typing import Optional, List
from app import db
from flask_login import UserMixin
from datetime import datetime, timedelta
from sqlalchemy import Text, String
from sqlalchemy.dialects import sqlite, mysql, postgresql

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    language = db.Column(db.String(2), default='uz')  # uz/ru/en
    subscription_type = db.Column(db.String(20), default='free')  # free/basic/premium/admin
    subscription_start_date = db.Column(db.DateTime, default=datetime.utcnow)
    subscription_end_date = db.Column(db.DateTime)
    is_admin = db.Column(db.Boolean, default=False)
    _is_active = db.Column('is_active', db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    telegram_id = db.Column(db.String(50), unique=True)
    instagram_id = db.Column(db.String(50), unique=True)
    whatsapp_number = db.Column(db.String(20), unique=True)
    phone_number = db.Column(db.String(20))
    
    # Notification settings
    admin_chat_id = db.Column(db.String(50))  # Admin telegram chat ID for notifications
    notification_channel = db.Column(db.String(100))  # Telegram channel for notifications
    notifications_enabled = db.Column(db.Boolean, default=False)
    
    # Relationships
    bots = db.relationship('Bot', backref='owner', lazy=True, cascade='all, delete-orphan')
    payments = db.relationship('Payment', backref='user', lazy=True)
    
    def __repr__(self):
        return f'<User {self.username}>'
    
    @property
    def is_active(self):
        """Override UserMixin's is_active property"""
        return self._is_active
    
    @is_active.setter
    def is_active(self, value):
        """Allow setting is_active"""
        self._is_active = value
    
    def can_create_bot(self) -> bool:
        if self.subscription_type == 'admin':
            return True
        # Query orqali botlar sonini olish (relationship emas)
        bot_count = Bot.query.filter_by(user_id=self.id).count()
        if self.subscription_type == 'free' and bot_count >= 1:
            return False
        elif self.subscription_type in ['starter', 'basic'] and bot_count >= 1:
            return False
        elif self.subscription_type == 'premium' and bot_count >= 3:
            return False
        return True
    
    def can_use_language(self, lang: str) -> bool:
        if self.subscription_type in ['free']:
            return lang == 'uz'
        elif self.subscription_type in ['starter', 'basic', 'premium', 'admin']:
            return lang in ['uz', 'ru', 'en']
        return False
    
    def subscription_active(self) -> bool:
        # Admin users are always active
        if self.subscription_type == 'admin' or self.is_admin:
            return True
            
        if self.subscription_type == 'free':
            # For free users, calculate expiry based on available dates
            if self.subscription_end_date is not None:
                return self.subscription_end_date > datetime.utcnow()
            else:
                # For legacy free users without end_date, give them 15 days from start or creation
                base_date = self.subscription_start_date or self.created_at or datetime.utcnow()
                computed_end = base_date + timedelta(days=7)
                return datetime.utcnow() < computed_end
                
        # For paid subscriptions, require valid end_date
        if self.subscription_type in ['starter', 'basic', 'premium']:
            if self.subscription_end_date:
                return self.subscription_end_date > datetime.utcnow()
                
        return False

class Bot(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    platform = db.Column(db.String(20), default='Telegram')  # Telegram/Instagram/WhatsApp
    telegram_token = db.Column(db.String(500))
    telegram_username = db.Column(db.String(100))
    instagram_token = db.Column(db.String(500))
    whatsapp_token = db.Column(db.String(500))
    whatsapp_phone_id = db.Column(db.String(100))
    daily_messages = db.Column(db.Integer, default=0)
    weekly_messages = db.Column(db.Integer, default=0)
    last_updated = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Mini App / Business settings
    business_type = db.Column(db.String(20), default='product')  # product/service
    business_description = db.Column(db.String(500))
    business_logo = db.Column(db.String(500))
    working_hours = db.Column(db.String(100))
    miniapp_enabled = db.Column(db.Boolean, default=True)
    description = db.Column(db.String(500))
    
    # MiniApp Customization (Premium only)
    miniapp_theme_color = db.Column(db.String(20), default='#00d4aa')
    miniapp_bg_color = db.Column(db.String(20), default='#0f0f0f')
    miniapp_card_color = db.Column(db.String(20), default='#252525')
    miniapp_welcome_text = db.Column(db.String(300), default='')
    miniapp_currency = db.Column(db.String(20), default="so'm")
    custom_welcome_message = db.Column(Text, default='')
    
    # Relationships
    knowledge_base = db.relationship('KnowledgeBase', backref='bot', lazy=True, cascade='all, delete-orphan')
    orders = db.relationship('MiniAppOrder', backref='bot', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Bot {self.name}>'

class KnowledgeBase(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bot_id = db.Column(db.Integer, db.ForeignKey('bot.id'), nullable=False)
    # UTF-8 enabled text column for multilingual content
    content = db.Column(Text().with_variant(
        mysql.TEXT(charset='utf8mb4', collation='utf8mb4_unicode_ci'), 'mysql'
    ).with_variant(
        postgresql.TEXT(), 'postgresql'
    ), nullable=False)
    filename = db.Column(db.String(200))
    content_type = db.Column(db.String(20), default='file')  # file, text, image_link
    source_name = db.Column(db.String(200))  # Custom name for text/image entries
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<KnowledgeBase {self.source_name or self.filename}>'

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    method = db.Column(db.String(20), nullable=False)  # Payme/Click/Uzum
    status = db.Column(db.String(20), default='pending')  # pending/completed/failed
    transaction_id = db.Column(db.String(100))
    subscription_type = db.Column(db.String(20))  # basic/premium
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<Payment {self.amount} {self.method}>'

class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bot_id = db.Column(db.Integer, db.ForeignKey('bot.id'), nullable=False)
    user_telegram_id = db.Column(db.String(50))
    user_instagram_id = db.Column(db.String(50))
    user_whatsapp_number = db.Column(db.String(20))
    # UTF-8 enabled text columns for emoji support
    message = db.Column(Text().with_variant(
        mysql.TEXT(charset='utf8mb4', collation='utf8mb4_unicode_ci'), 'mysql'
    ).with_variant(
        postgresql.TEXT(), 'postgresql'
    ), nullable=True)
    response = db.Column(Text().with_variant(
        mysql.TEXT(charset='utf8mb4', collation='utf8mb4_unicode_ci'), 'mysql'
    ).with_variant(
        postgresql.TEXT(), 'postgresql'
    ), nullable=True)
    language = db.Column(db.String(2), default='uz')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<ChatHistory {self.user_telegram_id}>'

class BroadcastMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message_text = db.Column(Text, nullable=False)
    target_type = db.Column(db.String(20), default='all')  # all/customers/bot_users
    sent_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='pending')  # pending/sending/completed/failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<BroadcastMessage {self.id}>'

class BotCustomer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bot_id = db.Column(db.Integer, db.ForeignKey('bot.id'), nullable=False)
    platform = db.Column(db.String(20), nullable=False)  # telegram/instagram/whatsapp
    platform_user_id = db.Column(db.String(100), nullable=False)  # User ID on the platform
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    username = db.Column(db.String(100))
    phone_number = db.Column(db.String(20))
    language = db.Column(db.String(2), default='uz')
    is_active = db.Column(db.Boolean, default=True)
    last_interaction = db.Column(db.DateTime, default=datetime.utcnow)
    message_count = db.Column(db.Integer, default=0)
    first_interaction = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Constraints to ensure unique customer per bot per platform
    __table_args__ = (db.UniqueConstraint('bot_id', 'platform', 'platform_user_id'),)
    
    def __repr__(self):
        return f'<BotCustomer {self.first_name} {self.last_name} - {self.platform}>'
    
    @property
    def display_name(self):
        """Get display name for customer"""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.username:
            return f"@{self.username}"
        else:
            return f"User {self.platform_user_id}"

class BotMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    bot_id = db.Column(db.Integer, db.ForeignKey('bot.id'), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)  # Bot owner
    message_text = db.Column(Text, nullable=False)
    message_type = db.Column(db.String(20), default='individual')  # individual/broadcast
    target_customers = db.Column(Text)  # JSON list of customer IDs for individual messages
    sent_count = db.Column(db.Integer, default=0)
    status = db.Column(db.String(20), default='pending')  # pending/sending/completed/failed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sent_at = db.Column(db.DateTime)
    
    def __repr__(self):
        return f'<BotMessage {self.id} - {self.message_type}>'


class MiniAppOrder(db.Model):
    """Orders from Telegram Mini App"""
    id = db.Column(db.Integer, primary_key=True)
    bot_id = db.Column(db.Integer, db.ForeignKey('bot.id'), nullable=False)
    customer_name = db.Column(db.String(200), nullable=False)
    customer_phone = db.Column(db.String(50), nullable=False)
    customer_address = db.Column(db.String(500))
    note = db.Column(Text)
    items = db.Column(Text, nullable=False)  # JSON array of items
    total_amount = db.Column(db.Float, default=0)
    telegram_user_id = db.Column(db.String(50))
    status = db.Column(db.String(20), default='pending')  # pending/confirmed/delivered/cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<MiniAppOrder {self.id} - {self.customer_name}>'
