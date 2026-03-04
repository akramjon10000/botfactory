import os
from datetime import timedelta

from dotenv import load_dotenv
load_dotenv()

class Config:
    # Database
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///botfactory.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
    }
    
    # Security
    SECRET_KEY = os.environ.get('SESSION_SECRET')
    WTF_CSRF_ENABLED = True
    
    # Session
    PERMANENT_SESSION_LIFETIME = timedelta(days=7)
    
    # File uploads
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB
    UPLOAD_FOLDER = 'uploads'
    STATIC_FOLDER = 'static/uploads'
    ALLOWED_EXTENSIONS = {'txt', 'docx', 'csv', 'jpg', 'jpeg', 'png', 'gif', 'webp'}
    
    # AI
    GEMINI_API_KEY = os.environ.get('GOOGLE_API_KEY', '')
    
    # Telegram
    TELEGRAM_API_URL = 'https://api.telegram.org/bot'
    
    # Instagram Bot API
    INSTAGRAM_ACCESS_TOKEN = os.environ.get('INSTAGRAM_ACCESS_TOKEN', '')
    INSTAGRAM_VERIFY_TOKEN = os.environ.get('INSTAGRAM_VERIFY_TOKEN', '')
    
    # WhatsApp Business API
    WHATSAPP_ACCESS_TOKEN = os.environ.get('WHATSAPP_ACCESS_TOKEN', '')
    WHATSAPP_VERIFY_TOKEN = os.environ.get('WHATSAPP_VERIFY_TOKEN', '')
    WHATSAPP_PHONE_NUMBER_ID = os.environ.get('WHATSAPP_PHONE_NUMBER_ID', '')
    
    # Payment
    PAYME_MERCHANT_ID = os.environ.get('PAYME_MERCHANT_ID', '')
    CLICK_MERCHANT_ID = os.environ.get('CLICK_MERCHANT_ID', '')
    UZUM_MERCHANT_ID = os.environ.get('UZUM_MERCHANT_ID', '')
    
    # Cloudinary
    CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', '')
    CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY', '')
    CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', '')
    
    # Subscription prices (in UZS)
    SUBSCRIPTION_PRICES = {
        'starter': 165000,
        'basic': 290000,
        'premium': 590000
    }
    
    # Bot limits
    BOT_LIMITS = {
        'free': 1,
        'starter': 1,
        'basic': 1,
        'premium': 5
    }
    
    # Language restrictions
    LANGUAGE_RESTRICTIONS = {
        'free': ['uz'],
        'starter': ['uz', 'ru', 'en'],
        'basic': ['uz', 'ru', 'en'],
        'premium': ['uz', 'ru', 'en'],
        'admin': ['uz', 'ru', 'en']
    }

class DevelopmentConfig(Config):
    DEBUG = True
    DEVELOPMENT = True

class ProductionConfig(Config):
    DEBUG = False
    DEVELOPMENT = False

# Configuration mapping
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
