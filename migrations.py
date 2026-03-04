"""
Database migrations and performance indices
Adds critical indices for high-load performance
"""
import logging
from app import app, db
from sqlalchemy import text, Index

logger = logging.getLogger(__name__)

def add_performance_indices():
    """
    Add database indices for high-performance queries
    Critical for handling high load scenarios
    """
    with app.app_context():
        try:
            # User table indices
            indices_to_create = [
                # User lookups
                "CREATE INDEX IF NOT EXISTS idx_user_telegram_id ON user(telegram_id)",
                "CREATE INDEX IF NOT EXISTS idx_user_username ON user(username)",
                "CREATE INDEX IF NOT EXISTS idx_user_email ON user(email)",
                "CREATE INDEX IF NOT EXISTS idx_user_subscription ON user(subscription_type, subscription_end_date)",
                
                # Bot table indices
                "CREATE INDEX IF NOT EXISTS idx_bot_user_id ON bot(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_bot_telegram_token ON bot(telegram_token)",
                "CREATE INDEX IF NOT EXISTS idx_bot_instagram_token ON bot(instagram_token)",
                "CREATE INDEX IF NOT EXISTS idx_bot_whatsapp_token ON bot(whatsapp_token)",
                "CREATE INDEX IF NOT EXISTS idx_bot_active ON bot(is_active)",
                
                # Chat history indices (most critical for performance)
                "CREATE INDEX IF NOT EXISTS idx_chat_bot_user ON chat_history(bot_id, user_telegram_id)",
                "CREATE INDEX IF NOT EXISTS idx_chat_created_desc ON chat_history(created_at DESC)",
                "CREATE INDEX IF NOT EXISTS idx_chat_bot_created ON chat_history(bot_id, created_at DESC)",
                
                # Knowledge base indices
                "CREATE INDEX IF NOT EXISTS idx_kb_bot_id ON knowledge_base(bot_id)",
                "CREATE INDEX IF NOT EXISTS idx_kb_content_type ON knowledge_base(content_type)",
                "CREATE INDEX IF NOT EXISTS idx_kb_bot_type ON knowledge_base(bot_id, content_type)",
                
                # Payment indices
                "CREATE INDEX IF NOT EXISTS idx_payment_user ON payment(user_id)",
                "CREATE INDEX IF NOT EXISTS idx_payment_status ON payment(status)",
                "CREATE INDEX IF NOT EXISTS idx_payment_created ON payment(created_at DESC)",
                
                # Composite indices for common queries
                "CREATE INDEX IF NOT EXISTS idx_user_subscription_active ON user(subscription_type, subscription_end_date, is_active)",
                "CREATE INDEX IF NOT EXISTS idx_chat_recent_history ON chat_history(bot_id, user_telegram_id, created_at DESC)",
            ]
            
            for index_sql in indices_to_create:
                try:
                    db.session.execute(text(index_sql))
                    logger.info(f"Created index: {index_sql.split()[-1]}")
                except Exception as e:
                    if "already exists" not in str(e).lower():
                        logger.error(f"Index creation failed: {e}")
            
            db.session.commit()
            logger.info("Performance indices created successfully")
            
        except Exception as e:
            logger.error(f"Index creation failed: {e}")
            db.session.rollback()

def optimize_database_settings():
    """
    Apply database-specific optimizations
    """
    with app.app_context():
        try:
            # PostgreSQL-specific optimizations
            optimizations = [
                # Connection settings
                "SET shared_preload_libraries = 'pg_stat_statements'",
                
                # Query optimization
                "SET random_page_cost = 1.1",  # For SSD storage
                "SET effective_cache_size = '256MB'",
                "SET work_mem = '8MB'",
                
                # Checkpoint settings for write performance
                "SET checkpoint_completion_target = 0.9",
                "SET wal_buffers = '16MB'",
                
                # Logging for performance monitoring
                "SET log_min_duration_statement = 1000",  # Log slow queries
                "SET log_checkpoints = on",
            ]
            
            for optimization in optimizations:
                try:
                    db.session.execute(text(optimization))
                    logger.info(f"Applied optimization: {optimization.split('=')[0].strip()}")
                except Exception as e:
                    logger.warning(f"Optimization skipped: {e}")
            
            db.session.commit()
            logger.info("Database optimizations applied")
            
        except Exception as e:
            logger.error(f"Database optimization failed: {e}")
            db.session.rollback()

def analyze_database_performance():
    """
    Analyze current database performance and suggest improvements
    """
    with app.app_context():
        try:
            # Get table sizes
            result = db.session.execute(text("""
                SELECT 
                    schemaname,
                    tablename,
                    attname,
                    n_distinct,
                    correlation
                FROM pg_stats 
                WHERE schemaname = 'public'
                ORDER BY tablename, attname
            """))
            
            stats = result.fetchall()
            logger.info(f"Database statistics collected for {len(stats)} columns")
            
            # Check for missing indices on large tables
            result = db.session.execute(text("""
                SELECT 
                    t.relname as table_name,
                    t.n_tup_ins as inserts,
                    t.n_tup_upd as updates,
                    t.n_tup_del as deletes,
                    pg_size_pretty(pg_total_relation_size(t.relid)) as size
                FROM pg_stat_user_tables t
                ORDER BY pg_total_relation_size(t.relid) DESC
            """))
            
            table_stats = result.fetchall()
            for stat in table_stats:
                logger.info(f"Table {stat[0]}: Size {stat[4]}, Inserts: {stat[1]}")
            
            return {
                'column_stats': len(stats),
                'table_stats': len(table_stats)
            }
            
        except Exception as e:
            logger.error(f"Performance analysis failed: {e}")
            return {'error': str(e)}

if __name__ == "__main__":
    # Run migrations
    add_performance_indices()
    optimize_database_settings()
    analyze_database_performance()
