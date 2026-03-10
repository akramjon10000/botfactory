import os
import io
import logging
import tempfile
import requests
from pathlib import Path
import google.generativeai as genai
from google.cloud import speech
from ai import get_ai_response

logger = logging.getLogger(__name__)

class AudioProcessor:
    """Audio xabarlarni matnga o'girish va AI javob berish"""
    
    def __init__(self):
        # Google Cloud Speech-to-Text konfiguratsiyasi
        self.credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if self.credentials_path and os.path.exists(self.credentials_path):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = self.credentials_path
        
        self.supported_formats = ['.ogg', '.mp3', '.wav', '.m4a', '.aac']
        
    def process_audio_message(self, audio_file_path, user_id, language='uz'):
        """
        Audio faylni matnga o'girish va AI javob berish
        
        Args:
            audio_file_path (str): Audio fayl yo'li
            user_id (str): Foydalanuvchi ID
            language (str): Til kodi (uz, ru, en)
        
        Returns:
            str: AI tomonidan yaratilgan javob
        """
        try:
            logger.info(f"Audio xabarni qayta ishlash boshlandi: {audio_file_path}")
            
            # 1. Audio faylni matnga o'girish
            text_from_audio = self.transcribe_audio(audio_file_path, language)
            
            if not text_from_audio:
                return "❌ Audio faylni tushunib bo'lmadi. Iltimos, aniqroq gapiring yoki boshqa formatda yuboring!"
            
            logger.info(f"Audio matn: {text_from_audio}")
            
            # 2. AI javob olish
            ai_response = get_ai_response(
                message=text_from_audio,
                user_language=language
            )
            
            return f"🎤 Sizning xabaringiz: \"{text_from_audio}\"\n\n{ai_response}"
            
        except Exception as e:
            logger.error(f"Audio processingda xato: {str(e)}")
            return "❌ Audio xabarni qayta ishlashda xatolik yuz berdi! Iltimos, qaytadan urinib ko'ring."

    def transcribe_audio(self, audio_file_path, language='uz'):
        """
        Audio faylni matnga o'girish (Google Speech-to-Text)
        
        Args:
            audio_file_path (str): Audio fayl yo'li
            language (str): Til kodi
        
        Returns:
            str: Transkripsiya qilingan matn
        """
        try:
            # Google Speech client yaratish
            client = speech.SpeechClient()
            
            # Audio faylni o'qish
            with io.open(audio_file_path, "rb") as audio_file:
                content = audio_file.read()
            
            audio = speech.RecognitionAudio(content=content)
            
            # Til kodini aniqlash
            language_codes = {
                'uz': 'uz-UZ',
                'ru': 'ru-RU', 
                'en': 'en-US'
            }
            
            primary_language = language_codes.get(language, 'uz-UZ')
            alternative_languages = [code for code in language_codes.values() if code != primary_language]
            
            # Konfiguratsiya
            config = speech.RecognitionConfig(
                encoding=speech.RecognitionConfig.AudioEncoding.OGG_OPUS,
                sample_rate_hertz=16000,
                language_code=primary_language,
                alternative_language_codes=alternative_languages[:2],  # Maksimal 3 ta til
                enable_automatic_punctuation=True,
                use_enhanced=True,
                model='latest_long'
            )
            
            # Transkripsiya
            response = client.recognize(config=config, audio=audio)
            
            if response.results:
                transcript = response.results[0].alternatives[0].transcript
                confidence = response.results[0].alternatives[0].confidence
                
                logger.info(f"Transkripsiya muvaffaqiyatli: {transcript} (confidence: {confidence})")
                return transcript.strip()
            else:
                logger.warning("Transkripsiya natijasi topilmadi")
                return None
                
        except Exception as e:
            logger.error(f"Audio transkripsiyada xato: {str(e)}")
            return None
    
    def download_audio_from_url(self, audio_url, file_extension='.ogg'):
        """
        URL dan audio faylni yuklash
        
        Args:
            audio_url (str): Audio fayl URL
            file_extension (str): Fayl kengaytmasi
        
        Returns:
            str: Yuklangan fayl yo'li
        """
        try:
            response = requests.get(audio_url, timeout=30)
            response.raise_for_status()
            
            # Vaqtincha fayl yaratish
            with tempfile.NamedTemporaryFile(suffix=file_extension, delete=False) as temp_file:
                temp_file.write(response.content)
                return temp_file.name
                
        except Exception as e:
            logger.error(f"Audio yuklab olishda xato: {str(e)}")
            return None
    
    def cleanup_temp_file(self, file_path):
        """Vaqtincha faylni o'chirish"""
        try:
            if os.path.exists(file_path):
                os.unlink(file_path)
                logger.info(f"Vaqtincha fayl o'chirildi: {file_path}")
        except Exception as e:
            logger.error(f"Faylni o'chirishda xato: {str(e)}")

# Global audio processor instance
audio_processor = AudioProcessor()

def process_audio_message(audio_file_path, user_id, language='uz'):
    """Audio xabarni qayta ishlash (wrapper function)"""
    return audio_processor.process_audio_message(audio_file_path, user_id, language)

def download_and_process_audio(audio_url, user_id, language='uz', file_extension='.ogg'):
    """
    Audio URL dan yuklab olib qayta ishlash
    
    Args:
        audio_url (str): Audio fayl URL
        user_id (str): Foydalanuvchi ID
        language (str): Til kodi
        file_extension (str): Fayl kengaytmasi
    
    Returns:
        str: AI javob
    """
    temp_file_path = None
    try:
        # Audio faylni yuklash
        temp_file_path = audio_processor.download_audio_from_url(audio_url, file_extension)
        
        if not temp_file_path:
            return "❌ Audio faylni yuklab olishda xatolik yuz berdi!"
        
        # Audio faylni qayta ishlash
        result = audio_processor.process_audio_message(temp_file_path, user_id, language)
        
        return result
        
    finally:
        # Vaqtincha faylni o'chirish
        if temp_file_path:
            audio_processor.cleanup_temp_file(temp_file_path)