"""Routes package - all Blueprint modules"""
from routes.main import main_bp
from routes.blog import blog_bp
from routes.admin import admin_routes_bp
from routes.bot import bot_bp
from routes.knowledge import knowledge_bp
from routes.webhook import webhook_bp

__all__ = [
    'main_bp',
    'blog_bp',
    'admin_routes_bp',
    'bot_bp',
    'knowledge_bp',
    'webhook_bp',
]
