"""
Async tasks for bot processing using Celery
Handles AI responses, media processing, and notifications
"""
import logging
import time
from celery import current_task
from celery_app import celery
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

@celery.task(bind=True, max_retries=3)
def generate_ai_response(self, message: str, bot_name: str, user_language: str = 'uz', 
                        knowledge_base: str = "", chat_history: str = "", 
                        chat_id: int = 0, user_id: int = 0) -> Dict[str, Any]:
    """
    Generate AI response asynchronously with retry logic
    Returns: {success: bool, response: str, error: str}
    """
    try:
        # Import here to avoid circular imports
        from ai import get_ai_response
        
        logger.info(f"Task {self.request.id}: Generating AI response for chat {chat_id}")
        start_time = time.time()
        
        # Generate AI response
        ai_response = get_ai_response(
            message=message,
            bot_name=bot_name,
            user_language=user_language,
            knowledge_base=knowledge_base,
            chat_history=chat_history
        )
        
        processing_time = time.time() - start_time
        logger.info(f"Task {self.request.id}: AI response generated in {processing_time:.2f}s")
        
        if ai_response:
            # Send response back to Telegram immediately
            if chat_id and chat_id > 0:
                send_telegram_message.apply_async(args=[chat_id, ai_response, user_id])
            
            return {
                'success': True,
                'response': ai_response,
                'processing_time': processing_time,
                'error': None
            }
        else:
            return {
                'success': False,
                'response': None,
                'error': 'AI response generation failed'
            }
            
    except Exception as exc:
        logger.error(f"Task {self.request.id} failed: {exc}")
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            retry_delay = 60 * (2 ** self.request.retries)  # 60s, 120s, 240s
            logger.info(f"Retrying task {self.request.id} in {retry_delay}s")
            raise self.retry(countdown=retry_delay, exc=exc)
        
        return {
            'success': False,
            'response': None,
            'error': str(exc)
        }

@celery.task(bind=True, max_retries=3)
def send_telegram_message(self, chat_id: int, message: str, user_id: int = 0) -> Dict[str, Any]:
    """
    Send Telegram message asynchronously
    """
    try:
        # Import here to avoid circular imports
        import requests
        import os
        
        logger.info(f"Task {self.request.id}: Sending message to chat {chat_id}")
        
        bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        if not bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not configured")
        
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        
        data = {
            'chat_id': chat_id,
            'text': message,
            'parse_mode': 'HTML'
        }
        
        response = requests.post(url, json=data, timeout=30)
        response.raise_for_status()
        
        logger.info(f"Task {self.request.id}: Message sent successfully to chat {chat_id}")
        
        # Save to chat history if user_id provided
        if user_id and user_id > 0:
            save_chat_history.apply_async(args=[user_id, chat_id, message], kwargs={'is_bot_response': True})
        
        return {
            'success': True,
            'message_id': response.json().get('result', {}).get('message_id'),
            'error': None
        }
        
    except Exception as exc:
        logger.error(f"Task {self.request.id} failed: {exc}")
        
        if self.request.retries < self.max_retries:
            retry_delay = 30 * (2 ** self.request.retries)  # 30s, 60s, 120s
            logger.info(f"Retrying task {self.request.id} in {retry_delay}s")
            raise self.retry(countdown=retry_delay, exc=exc)
        
        return {
            'success': False,
            'error': str(exc)
        }

@celery.task(bind=True)
def save_chat_history(self, user_id: int, chat_id: int, message: str, 
                     response: str = None, is_bot_response: bool = False) -> Dict[str, Any]:
    """
    Save chat history to database asynchronously
    """
    try:
        from app import app, db
        from models import ChatHistory, User
        
        with app.app_context():
            # Find bot by user_id
            user = User.query.get(user_id)
            if not user:
                return {'success': False, 'error': 'User not found'}
            
            # Get user's bot (assuming first bot for simplicity)
            if user.bots:
                bot_id = user.bots[0].id
            else:
                return {'success': False, 'error': 'No bot found for user'}
            
            if is_bot_response:
                # This is a bot response, find the latest user message to update
                latest_entry = ChatHistory.query.filter_by(
                    bot_id=bot_id,
                    user_telegram_id=chat_id
                ).order_by(ChatHistory.created_at.desc()).first()
                
                if latest_entry and not latest_entry.response:
                    latest_entry.response = message
                    db.session.commit()
                    return {'success': True, 'updated_existing': True}
            
            # Create new chat history entry
            chat_entry = ChatHistory()
            chat_entry.bot_id = bot_id
            chat_entry.user_telegram_id = chat_id
            chat_entry.message = message
            chat_entry.response = response
            
            db.session.add(chat_entry)
            db.session.commit()
            
            return {'success': True, 'created_new': True}
            
    except Exception as exc:
        logger.error(f"Chat history save failed: {exc}")
        return {'success': False, 'error': str(exc)}

@celery.task(bind=True, max_retries=2)
def process_audio(self, audio_file_path: str, chat_id: int, user_id: int) -> Dict[str, Any]:
    """
    Process audio file asynchronously (transcription, etc.)
    """
    try:
        logger.info(f"Task {self.request.id}: Processing audio file {audio_file_path}")
        
        # Import here to avoid circular imports
        try:
            from audio_processor import transcribe_audio
            # Transcribe audio
            transcript = transcribe_audio(audio_file_path)
        except ImportError:
            # Fallback if audio processing module not available
            transcript = "Audio processing not available"
        
        if transcript and transcript != "Audio processing not available":
            # Process as text message
            generate_ai_response.apply_async(args=[
                transcript,
                "Bot",  # Get from context
                "uz",
                "",
                "",
                chat_id,
                user_id
            ])
            
            return {
                'success': True,
                'transcript': transcript,
                'error': None
            }
        else:
            return {
                'success': False,
                'error': 'Audio transcription failed'
            }
            
    except Exception as exc:
        logger.error(f"Task {self.request.id} failed: {exc}")
        
        if self.request.retries < self.max_retries:
            retry_delay = 60 * (2 ** self.request.retries)
            raise self.retry(countdown=retry_delay, exc=exc)
        
        return {
            'success': False,
            'error': str(exc)
        }

@celery.task
def cleanup_old_tasks():
    """
    Cleanup old task results and temporary files
    """
    try:
        # Cleanup Redis keys older than 1 hour
        import redis
        import os
        
        redis_client = redis.from_url(os.environ.get('REDIS_URL', 'redis://localhost:6379/0'))
        
        # Get all celery result keys
        keys = redis_client.keys('celery-task-meta-*')
        
        # Clean up old keys (older than 1 hour)
        cleaned = 0
        for key in keys:
            ttl = redis_client.ttl(key)
            if ttl == -1:  # No expiration set
                redis_client.expire(key, 3600)  # Set 1 hour expiration
                cleaned += 1
        
        logger.info(f"Cleaned up {cleaned} old task result keys")
        
        return {'success': True, 'cleaned_keys': cleaned}
        
    except Exception as exc:
        logger.error(f"Cleanup task failed: {exc}")
        return {'success': False, 'error': str(exc)}
