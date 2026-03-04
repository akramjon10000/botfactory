"""
Professional logging konfiguratsiyasi Chatbot Factory AI uchun
"""

import os
import logging
import logging.config
import copy
from datetime import datetime
from typing import Dict, Any, Optional

def _sanitize_for_legacy_console(text: str) -> str:
    """Replace non-ASCII characters to avoid cp1251/cp1252 console encoding errors."""
    return text.encode('ascii', errors='replace').decode('ascii')

class SafeConsoleHandler(logging.StreamHandler):
    """Console handler that degrades gracefully on legacy Windows encodings."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
            try:
                self.stream.write(message + self.terminator)
            except UnicodeEncodeError:
                safe_record = copy.copy(record)
                safe_record.msg = _sanitize_for_legacy_console(record.getMessage())
                safe_record.args = ()
                safe_message = self.format(safe_record)
                self.stream.write(safe_message + self.terminator)
            self.flush()
        except Exception:
            self.handleError(record)

# Logging konfiguratsiyasi
LOGGING_CONFIG: Dict[str, Any] = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'detailed': {
            'format': '[%(asctime)s] %(levelname)s in %(name)s [%(filename)s:%(lineno)d]: %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'simple': {
            'format': '[%(asctime)s] %(levelname)s: %(message)s',
            'datefmt': '%H:%M:%S'
        },
        'json': {
            'format': '{"timestamp": "%(asctime)s", "level": "%(levelname)s", "module": "%(name)s", "message": "%(message)s"}',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging_config.SafeConsoleHandler',
            'level': 'INFO',
            'formatter': 'simple',
            'stream': 'ext://sys.stdout'
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'DEBUG',
            'formatter': 'detailed',
            'filename': 'logs/chatbot-factory.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 5,
            'encoding': 'utf8'
        },
        'error_file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'level': 'ERROR',
            'formatter': 'detailed', 
            'filename': 'logs/errors.log',
            'maxBytes': 10485760,  # 10MB
            'backupCount': 3,
            'encoding': 'utf8'
        }
    },
    'loggers': {
        '': {  # Root logger
            'level': 'DEBUG',
            'handlers': ['console', 'file', 'error_file']
        },
        'werkzeug': {
            'level': 'WARNING',
            'handlers': ['console'],
            'propagate': False
        },
        'urllib3': {
            'level': 'WARNING', 
            'handlers': ['console'],
            'propagate': False
        },
        'apscheduler': {
            'level': 'INFO',
            'handlers': ['console', 'file'],
            'propagate': False
        }
    }
}

def setup_logging() -> None:
    """Logging tizimini sozlash"""
    try:
        # Logs papkasini yaratish
        os.makedirs('logs', exist_ok=True)
        
        # Logging konfiguratsiyasini qo'llash
        logging.config.dictConfig(LOGGING_CONFIG)
        
        # Test log
        logger = logging.getLogger(__name__)
        logger.info("Chatbot Factory AI logging system initialized successfully")
        
    except Exception as e:
        print(f"Failed to setup logging: {str(e)}")
        # Fallback to basic logging
        logging.basicConfig(
            level=logging.INFO,
            format='[%(asctime)s] %(levelname)s: %(message)s'
        )

class ErrorTracker:
    """Xatolarni kuzatish va hisobot berish"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.error_counts: Dict[str, int] = {}
        self.last_errors: Dict[str, datetime] = {}
    
    def log_error(self, error: Exception, context: str = "", user_id: Optional[int] = None) -> None:
        """Xatoni qayd qilish"""
        try:
            error_key = f"{type(error).__name__}:{str(error)[:100]}"
            
            # Xato sonini oshirish
            self.error_counts[error_key] = self.error_counts.get(error_key, 0) + 1
            self.last_errors[error_key] = datetime.now()
            
            # Detailed log
            self.logger.error(
                f"Error in {context}: {type(error).__name__}: {str(error)}"
                f" | User ID: {user_id} | Count: {self.error_counts[error_key]}",
                exc_info=True
            )
            
            # Critical xatolar uchun alohida log
            if self.error_counts[error_key] > 10:
                self.logger.critical(
                    f"REPEATED ERROR: {error_key} occurred {self.error_counts[error_key]} times"
                )
                
        except Exception as logging_error:
            print(f"Logging error: {logging_error}")
    
    def get_error_summary(self) -> Dict[str, Any]:
        """Xatolar xulosasi"""
        return {
            'total_error_types': len(self.error_counts),
            'most_common_errors': sorted(
                self.error_counts.items(), 
                key=lambda x: x[1], 
                reverse=True
            )[:5],
            'recent_errors': [
                {
                    'error': error,
                    'count': count,
                    'last_occurrence': self.last_errors[error].isoformat()
                }
                for error, count in sorted(
                    self.error_counts.items(),
                    key=lambda x: self.last_errors[x[0]],
                    reverse=True
                )[:3]
            ]
        }

# Global error tracker
error_tracker = ErrorTracker()

def log_function_call(func_name: str, args: Optional[Dict[str, Any]] = None) -> None:
    """Funksiya chaqiruvini log qilish"""
    logger = logging.getLogger(__name__)
    args_str = f" with args: {args}" if args else ""
    logger.debug(f"Calling {func_name}{args_str}")

def log_performance(func_name: str, duration: float, success: bool = True) -> None:
    """Performance logini yozish"""
    logger = logging.getLogger(__name__)
    status = "SUCCESS" if success else "FAILED"
    logger.info(f"PERFORMANCE: {func_name} took {duration:.3f}s - {status}")

class ContextLogger:
    """Context bilan logging"""
    
    def __init__(self, logger_name: str, context: Optional[Dict[str, Any]] = None):
        self.logger = logging.getLogger(logger_name)
        self.context = context or {}
    
    def info(self, message: str) -> None:
        """Info log with context"""
        ctx_str = " | ".join([f"{k}:{v}" for k, v in self.context.items()])
        self.logger.info(f"{message} | Context: {ctx_str}")
    
    def error(self, message: str, error: Optional[Exception] = None) -> None:
        """Error log with context"""
        ctx_str = " | ".join([f"{k}:{v}" for k, v in self.context.items()])
        full_message = f"{message} | Context: {ctx_str}"
        
        if error:
            self.logger.error(full_message, exc_info=True)
            error_tracker.log_error(error, message, self.context.get('user_id'))
        else:
            self.logger.error(full_message)

# Initialization
if __name__ != "__main__":
    setup_logging()
