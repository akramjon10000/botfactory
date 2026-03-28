import os
import logging
from datetime import datetime
from flask import Flask, request
from flask_wtf import CSRFProtect
from flask_wtf.csrf import generate_csrf
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_migrate import Migrate
from flasgger import Swagger
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import create_engine, text
from werkzeug.middleware.proxy_fix import ProxyFix

# Professional logging tizimini ishga tushirish
try:
    from logging_config import setup_logging, error_tracker, ContextLogger
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("Chatbot Factory AI application starting with professional logging")
except Exception as e:
    # Fallback basic logging for any error
    logging.basicConfig(
        level=logging.INFO,
        format='[%(asctime)s] %(levelname)s: %(message)s'
    )
    logger = logging.getLogger(__name__)
    logger.warning(f"Using fallback logging configuration due to: {e}")

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET")
if not app.secret_key:
    logger.error("SESSION_SECRET environment variable is required!")
    raise ValueError("SESSION_SECRET environment variable must be set for security")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
csrf = CSRFProtect(app)

# Public contact configuration (used in templates)
app.config['SUPPORT_TELEGRAM'] = os.environ.get('SUPPORT_TELEGRAM', 'https://t.me/akramjon0011')
app.config['SUPPORT_PHONE'] = os.environ.get('SUPPORT_PHONE', '+998996448444')


def should_start_bot_manager():
    """Decide whether this process should own Telegram polling."""
    if os.environ.get("TESTING") == "1":
        return False

    start_flag = os.environ.get("START_BOT_MANAGER")
    if start_flag is not None:
        return start_flag == "1"

    # Default to starting polling in the main web service.
    return True

def test_database_connection(database_url, timeout=10):
    """Test database connectivity before Flask-SQLAlchemy initialization"""
    try:
        # Normalize postgres:// to postgresql:// for SQLAlchemy compatibility
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        
        # Create a temporary engine for testing
        test_engine = create_engine(
            database_url,
            pool_pre_ping=True,
            connect_args={"connect_timeout": timeout} if "postgresql" in database_url else {}
        )
        
        # Test the connection
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        
        test_engine.dispose()
        return True, database_url
        
    except Exception as e:
        logger.warning(f"Database connection test failed: {e}")
        return False, str(e)

def get_fallback_sqlite_config():
    """Get SQLite database configuration for fallback"""
    base_dir = os.path.abspath(os.path.dirname(__file__))
    instance_dir = os.path.join(base_dir, 'instance')
    if not os.path.exists(instance_dir):
        os.makedirs(instance_dir, exist_ok=True)
    
    database_path = os.path.join(instance_dir, 'botfactory.db')
    sqlite_url = f"sqlite:///{database_path}"
    
    sqlite_config = {
        "pool_recycle": 300,
        "pool_pre_ping": True,
        "echo": False,
        "connect_args": {"check_same_thread": False}
    }
    
    return sqlite_url, sqlite_config

# Cache control for different environments
@app.after_request
def after_request(response):
    if is_production:
        # Production cache settings for better performance
        if request.path.startswith('/static/'):
            response.headers["Cache-Control"] = "public, max-age=31536000"  # Cache static files for 1 year
        else:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
    else:
        # Always disable cache in development for Replit
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache" 
        response.headers["Expires"] = "0"

        # Dev-only CORS/iframe overrides (must be explicitly enabled)
        if os.environ.get("ALLOW_DEV_CORS") == "1":
            response.headers["X-Frame-Options"] = "ALLOWALL"
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    
    return response

# Preflight Database Configuration - Test connection before initialization
logger.info("рџ”Ќ Starting preflight database selection...")

# Detect production environment (Render.com)
is_production = os.environ.get('RENDER') or os.environ.get('DATABASE_URL', '').startswith('postgres')
database_url = os.environ.get("DATABASE_URL")

# Test PostgreSQL connection if available
if database_url and not database_url.startswith('sqlite'):
    logger.info(f"рџ”Њ Testing PostgreSQL connection...")
    connection_success, result = test_database_connection(database_url, timeout=10)
    
    if connection_success:
        # PostgreSQL connection successful - configure for PostgreSQL
        logger.info("вњ… PostgreSQL connection test successful")
        
        if is_production:
            # Production settings for Render.com - optimized for stability
            app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
                "pool_size": 5,           # Smaller pool for production stability
                "max_overflow": 10,       # Limited overflow to prevent resource exhaustion
                "pool_timeout": 10,       # Shorter timeout - fail fast instead of hanging
                "pool_recycle": 1800,     # Recycle connections every 30 minutes
                "pool_pre_ping": True,    # Always verify connections
                "echo": False,
                "connect_args": {
                    "connect_timeout": 10,    # Connection timeout: 10 seconds
                    "application_name": "chatbot_factory_production",
                }
            }
            logger.info("рџђ Using PostgreSQL with production-optimized connection pooling (Render.com)")
        else:
            # Development settings for Replit
            app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
                "pool_size": 10,          # Reasonable pool size for Replit
                "max_overflow": 20,       # Allow extra connections under load
                "pool_timeout": 30,       # Wait up to 30s for connection
                "pool_recycle": 3600,     # Recycle connections every hour
                "pool_pre_ping": True,    # Verify connections before use
                "echo": False
            }
            logger.info("рџђ Using PostgreSQL with development connection pooling (Replit)")
        
        app.config["SQLALCHEMY_DATABASE_URI"] = result
        
    else:
        # PostgreSQL connection failed - fall back to SQLite
        logger.warning(f"вќЊ PostgreSQL connection failed: {result}")
        if is_production:
            logger.error("рџљЁ PRODUCTION: PostgreSQL unavailable - using SQLite fallback")
            logger.error("вљ пёЏ WARNING: SQLite in production may cause data loss on ephemeral storage")
        else:
            logger.info("рџ”„ Development: PostgreSQL unavailable - using SQLite fallback")
        
        sqlite_url, sqlite_config = get_fallback_sqlite_config()
        app.config["SQLALCHEMY_DATABASE_URI"] = sqlite_url
        app.config["SQLALCHEMY_ENGINE_OPTIONS"] = sqlite_config
        logger.info("рџ’ѕ SQLite database configured successfully")
        
else:
    # No PostgreSQL URL provided - use SQLite directly
    logger.info("рџ”§ No PostgreSQL URL provided - using SQLite database")
    sqlite_url, sqlite_config = get_fallback_sqlite_config()
    app.config["SQLALCHEMY_DATABASE_URI"] = sqlite_url
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = sqlite_config
    logger.info("рџ’ѕ SQLite database configured for development")

# Add required Flask-SQLAlchemy configuration
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize extensions
db.init_app(app)
login_manager.init_app(app)
migrate = Migrate(app, db)
from extensions import sock
sock.init_app(app)

from extensions import sock
sock.init_app(app)

# Configure Swagger for API Documentation
swagger_config = {
    "headers": [],
    "specs": [
        {
            "endpoint": 'apispec_1',
            "route": '/apispec_1.json',
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/api/docs",
    "openapi": "3.0.0"
}
app.config['SWAGGER'] = {
    'title': 'BotFactory AI API',
    'uiversion': 3,
    'description': 'BotFactory AI platformining ochiq API hujjatlari. Ushbu darchada tizimga ulanish va u bilan integratsiya qilish yo\'riqnomalari mavjud.',
    'version': '1.0.0'
}
swagger = Swagger(app, config=swagger_config)
login_manager.login_view = 'auth.login'  # type: ignore
login_manager.login_message = 'Iltimos, tizimga kiring.'
login_manager.login_message_category = 'info'

# Make datetime available in templates
app.jinja_env.globals['datetime'] = datetime
app.jinja_env.globals['csrf_token'] = generate_csrf
app.jinja_env.globals['config'] = app.config

# Import routes after app creation to avoid circular imports
# from routes import main_bp, blog_bp, admin_routes_bp, bot_bp, knowledge_bp, webhook_bp
from routes import main_bp, admin_routes_bp, bot_bp, knowledge_bp, webhook_bp
from auth import auth_bp
from payments import payment_bp
from instagram_bot import instagram_bp
from whatsapp_bot import whatsapp_bp
from marketing import marketing_bp
from bot_status import bot_status_bp
from miniapp_api import miniapp_bp
from routes.orders import orders_bp
from routes.crm import crm_bp
import routes.live_audio

import routes.live_audio

app.register_blueprint(main_bp)
# app.register_blueprint(blog_bp)
app.register_blueprint(admin_routes_bp)
app.register_blueprint(bot_bp)
app.register_blueprint(knowledge_bp)
app.register_blueprint(webhook_bp)
app.register_blueprint(auth_bp, url_prefix='/auth')
app.register_blueprint(payment_bp, url_prefix='/payment')
app.register_blueprint(instagram_bp, url_prefix='/instagram')
app.register_blueprint(whatsapp_bp, url_prefix='/whatsapp')
app.register_blueprint(marketing_bp, url_prefix='/marketing')
app.register_blueprint(bot_status_bp, url_prefix='/admin')
app.register_blueprint(miniapp_bp, url_prefix='/api/miniapp')
app.register_blueprint(orders_bp, url_prefix='/api/orders')
app.register_blueprint(crm_bp, url_prefix='/api/crm')
csrf.exempt(miniapp_bp)  # MiniApp API is called from Telegram WebApp, no CSRF tokens

@login_manager.user_loader
def load_user(user_id):
    from models import User
    return User.query.get(int(user_id))

with app.app_context():
    # Import models to ensure tables are created
    import models
    
    # Create tables with better error handling for production
    try:
        if is_production:
            # Production: Use shorter timeout for database operations
            logger.info("Production environment detected - using optimized database settings")
            # Check required environment variables
            required_env_vars = ['SESSION_SECRET', 'DATABASE_URL']
            missing_vars = [var for var in required_env_vars if not os.environ.get(var)]
            if missing_vars:
                logger.error(f"Missing required environment variables: {missing_vars}")
                raise ValueError(f"Production deployment requires: {', '.join(missing_vars)}")
        
        db.create_all()
        logger.info("Database schema up to date")
        
        # Auto-migrate new User columns if missing
        try:
            from sqlalchemy import text
            with db.engine.connect() as conn:
                if 'postgresql' in str(db.engine.url):
                    # For PostgreSQL
                    user_cols = [
                        ("admin_chat_id", "VARCHAR(50)"),
                        ("notification_channel", "VARCHAR(100)"),
                        ("notifications_enabled", "BOOLEAN DEFAULT false")
                    ]
                    for col_name, col_def in user_cols:
                        try:
                            conn.execute(text(f"ALTER TABLE \"user\" ADD COLUMN IF NOT EXISTS {col_name} {col_def}"))
                            conn.commit()
                        except Exception as e:
                            # Rolling back in case of error to keep transaction viable
                            conn.execute(text("ROLLBACK"))
                            pass
                else:
                    # For SQLite
                    user_cols = [
                        ("admin_chat_id", "VARCHAR(50)", "ALTER TABLE user ADD COLUMN admin_chat_id VARCHAR(50)"),
                        ("notification_channel", "VARCHAR(100)", "ALTER TABLE user ADD COLUMN notification_channel VARCHAR(100)"),
                        ("notifications_enabled", "BOOLEAN", "ALTER TABLE user ADD COLUMN notifications_enabled BOOLEAN DEFAULT 0")
                    ]
                    for col_name, col_type, query in user_cols:
                        try:
                            # Avoid throwing hard error if exists
                            conn.execute(text(query))
                            conn.commit()
                        except Exception:
                            pass
        except Exception as e:
            logger.warning(f"User table migration skipped: {e}")

        # Auto-migrate Mini App columns if missing (for existing databases)
        try:
            from sqlalchemy import text
            with db.engine.connect() as conn:
                # Check if business_type column exists
                if 'postgresql' in str(db.engine.url):
                    # PostgreSQL migration
                    columns_to_add = [
                        ("business_type", "VARCHAR(20) DEFAULT 'product'"),
                        ("business_description", "VARCHAR(500)"),
                        ("business_logo", "VARCHAR(500)"),
                        ("working_hours", "VARCHAR(100)"),
                        ("miniapp_enabled", "BOOLEAN DEFAULT true"),
                        ("description", "VARCHAR(500)"),
                        ("miniapp_theme_color", "VARCHAR(20) DEFAULT '#00d4aa'"),
                        ("miniapp_bg_color", "VARCHAR(20) DEFAULT '#0f0f0f'"),
                        ("miniapp_card_color", "VARCHAR(20) DEFAULT '#252525'"),
                        ("miniapp_welcome_text", "VARCHAR(300) DEFAULT ''"),
                        ("miniapp_currency", "VARCHAR(20) DEFAULT 'so''m'"),
                        ("custom_welcome_message", "TEXT DEFAULT ''"),
                    ]
                    for col_name, col_def in columns_to_add:
                        try:
                            conn.execute(text(f"ALTER TABLE bot ADD COLUMN IF NOT EXISTS {col_name} {col_def}"))
                        except Exception:
                            pass
                    
                    # Create mini_app_order table if not exists
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS mini_app_order (
                            id SERIAL PRIMARY KEY,
                            bot_id INTEGER NOT NULL REFERENCES bot(id),
                            customer_name VARCHAR(200) NOT NULL,
                            customer_phone VARCHAR(50) NOT NULL,
                            customer_address VARCHAR(500),
                            note TEXT,
                            items TEXT NOT NULL,
                            total_amount FLOAT DEFAULT 0,
                            telegram_user_id VARCHAR(50),
                            status VARCHAR(20) DEFAULT 'pending',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """))
                    
                    # Create bot_customer table if not exists
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS bot_customer (
                            id SERIAL PRIMARY KEY,
                            bot_id INTEGER NOT NULL REFERENCES bot(id),
                            platform VARCHAR(20) DEFAULT 'telegram',
                            platform_user_id VARCHAR(100) NOT NULL,
                            first_name VARCHAR(100),
                            last_name VARCHAR(100),
                            username VARCHAR(100),
                            phone_number VARCHAR(20),
                            language VARCHAR(2) DEFAULT 'uz',
                            is_active BOOLEAN DEFAULT true,
                            last_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            message_count INTEGER DEFAULT 0,
                            first_interaction TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            UNIQUE (bot_id, platform, platform_user_id)
                        )
                    """))
                    
                    # Create bot_message table if not exists
                    conn.execute(text("""
                        CREATE TABLE IF NOT EXISTS bot_message (
                            id SERIAL PRIMARY KEY,
                            bot_id INTEGER NOT NULL REFERENCES bot(id),
                            sender_id INTEGER NOT NULL REFERENCES "user"(id),
                            message_text TEXT NOT NULL,
                            message_type VARCHAR(20) DEFAULT 'individual',
                            target_customers TEXT,
                            sent_count INTEGER DEFAULT 0,
                            status VARCHAR(20) DEFAULT 'pending',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            sent_at TIMESTAMP
                        )
                    """))
                    
                    conn.commit()
                    logger.info("Database migration completed (Bot columns + tables)")
        except Exception as migration_error:
            logger.warning(f"Mini App migration skipped: {migration_error}")
        
        # Create admin user only if environment variables are provided (for initial setup)
        admin_email = os.environ.get("ADMIN_EMAIL")
        admin_password = os.environ.get("ADMIN_PASSWORD")
        
        if admin_email and admin_password:
            from models import User
            from werkzeug.security import generate_password_hash, check_password_hash
            
            admin = User.query.filter_by(email=admin_email).first()
            if not admin:
                admin = User()
                admin.username = admin_email.split('@')[0]  # Use email prefix as username
                admin.email = admin_email
                admin.password_hash = generate_password_hash(admin_password)
                admin.language = 'uz'
                admin.subscription_type = 'admin'
                admin.is_admin = True
                db.session.add(admin)
                db.session.commit()
                logging.info(f"Admin user created successfully for {admin_email}")
            else:
                # Sync password from env in case it was changed
                new_hash = generate_password_hash(admin_password)
                if not check_password_hash(admin.password_hash, admin_password):
                    admin.password_hash = new_hash
                    admin.is_admin = True
                    admin.subscription_type = 'admin'
                    db.session.commit()
                    logging.info(f"Admin password synced from env for {admin_email}")
                else:
                    logging.info(f"Admin user already exists for {admin_email} (password unchanged)")
        else:
            logging.info("No admin credentials provided via ADMIN_EMAIL/ADMIN_PASSWORD - skipping admin user creation")
            
    except Exception as e:
        # Database operations failed after successful preflight test - this should be rare
        logger.error(f"рџ’Ґ Database operations failed after successful connection test: {e}")
        
        if is_production:
            logger.error("рџљЁ PRODUCTION CRITICAL: Database operations failed after preflight success")
            logger.error("рџ’Ў Check: Table creation permissions, Storage space, Connection limits")
            # In production, fail fast - don't attempt runtime fallback after preflight success
            raise
        else:
            logger.warning("вљ пёЏ DEVELOPMENT: Database operations failed - attempting emergency fallback")
            # In development only, try a simple retry
            try:
                db.create_all()
                logger.info("вњ… Database operations retry successful")
            except Exception as retry_error:
                logger.error(f"вќЊ Emergency fallback also failed: {retry_error}")
                raise
    
    # Initialize Bot Manager - Start all active bots polling in background
    if not should_start_bot_manager():
        if os.environ.get("TESTING") == "1":
            logger.info("TESTING=1 detected, skipping bot manager initialization")
        else:
            logger.info("Bot manager startup disabled for this process")
    else:
        try:
            logger.info("🤖 Initializing BotFactory AI Bot Manager...")
            from bot_manager import initialize_bot_manager

            if is_production:
                # Production: Check API keys before initializing bot manager
                api_keys_present = {
                    'GOOGLE_API_KEY': bool(os.environ.get('GOOGLE_API_KEY')),
                    'TELEGRAM_BOT_TOKEN': bool(os.environ.get('TELEGRAM_BOT_TOKEN'))
                }
                missing_apis = [k for k, v in api_keys_present.items() if not v]
                if missing_apis:
                    logger.warning(f"⚠️ Missing API keys in production: {missing_apis}")
                    logger.warning("⚠️ Bot functionality will be limited until API keys are added to Render.com")

            global_bot_manager = initialize_bot_manager()

            if global_bot_manager:
                logger.info("✅ Bot manager successfully initialized - all active bots will start polling!")
            else:
                logger.warning("⚠️ Bot manager initialization failed - bots will not auto-start")

        except Exception as bot_manager_error:
            logger.error(f"❌ Critical error initializing bot manager: {bot_manager_error}")
            if is_production:
                logger.error("🔥 PRODUCTION: Bot manager failed - check Render.com logs and environment variables")
            logger.warning("⚠️ Application will continue without bot polling - bots will not respond to messages!")
