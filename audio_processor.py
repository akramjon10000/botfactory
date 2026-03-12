import os
import io
import logging
import tempfile
import requests
from google import genai
from ai import get_ai_response

logger = logging.getLogger(__name__)

class AudioProcessor:
    """Audio xabarlarni matnga o'girish va AI javob berish"""
    
    def __init__(self):
        self.supported_formats = ['.ogg', '.mp3', '.wav', '.m4a', '.aac']
        # Configure new google-genai client
        api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GOOGLE_API_KEY2')
        self.client = None
        if api_key:
            self.client = genai.Client(api_key=api_key)
        
    def process_audio_message(self, audio_file_path, language='uz'):
        """
        Audio faylni matnga o'girish va AI javob berish
        
        Args:
            audio_file_path (str): Audio fayl yo'li
            language (str): Til kodi (uz, ru, en)
        
        Returns:
            str: AI tomonidan yaratilgan javob yoki None agar xato bo'lsa
        """
        try:
            logger.info(f"Audio xabarni qayta ishlash boshlandi: {audio_file_path}")
            
            # 1. Audio faylni matnga o'girish (Gemini bilan)
            text_from_audio = self.transcribe_audio_gemini(audio_file_path, language)
            
            if not text_from_audio:
                return None  # Return None so caller can handle
            
            logger.info(f"Audio matn: {text_from_audio}")
            return text_from_audio
            
        except Exception as e:
            logger.error(f"Audio processingda xato: {str(e)}")
            return None

    def transcribe_audio_gemini(self, audio_file_path, language='uz'):
        """
        Audio faylni Gemini Native Audio API orqali matnga o'girish
        
        Args:
            audio_file_path (str): Audio fayl yo'li
            language (str): Til kodi
        
        Returns:
            str: Transkripsiya qilingan matn
        """
        try:
            if not self.client:
                api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GOOGLE_API_KEY2')
                if not api_key:
                    logger.error("Google API kalit topilmadi")
                    return None
                self.client = genai.Client(api_key=api_key)

            # Upload the audio file to Gemini
            logger.info(f"Gemini Native Audio orqali transkripsiya: {audio_file_path}")
            
            # Upload audio file using new SDK
            audio_file = self.client.files.upload(file=audio_file_path)
            
            # Language names for the prompt
            lang_names = {
                'uz': "o'zbek",
                'ru': 'rus',
                'en': 'ingliz'
            }
            lang_name = lang_names.get(language, "o'zbek")
            
            prompt = f"""Bu audio xabardagi nutqni aniq matn shaklida yoz. 
Faqat gapirilgan so'zlarni yoz, boshqa hech narsa qo'shma.
Audio {lang_name} tilida bo'lishi mumkin, lekin boshqa tilda ham bo'lishi mumkin.
Agar audio bo'sh yoki tushunarsiz bo'lsa, bo'sh string qaytar."""
            
            # Use native audio model via new SDK
            response = self.client.models.generate_content(
                model='gemini-2.5-flash-native-audio-preview-12-2025',
                contents=[prompt, audio_file]
            )
            
            # Clean up uploaded file
            try:
                self.client.files.delete(name=audio_file.name)
            except Exception:
                pass
            
            if response and response.text:
                transcript = response.text.strip()
                if transcript and len(transcript) > 0:
                    logger.info(f"Gemini transkripsiya muvaffaqiyatli: {transcript}")
                    return transcript
            
            logger.warning("Gemini transkripsiya natijasi topilmadi")
            return None
                
        except Exception as e:
            logger.error(f"Gemini audio transkripsiyada xato: {str(e)}")
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
            if file_path and os.path.exists(file_path):
                os.unlink(file_path)
                logger.info(f"Vaqtincha fayl o'chirildi: {file_path}")
        except Exception as e:
            logger.error(f"Faylni o'chirishda xato: {str(e)}")

# Global audio processor instance
audio_processor = AudioProcessor()

def transcribe_audio_from_url(audio_url, language='uz', file_extension='.ogg'):
    """
    Audio URL dan yuklab olib matnga o'girish (faqat transkripsiya)
    
    Args:
        audio_url (str): Audio fayl URL
        language (str): Til kodi
        file_extension (str): Fayl kengaytmasi
    
    Returns:
        str: Transkripsiya qilingan matn yoki None
    """
    temp_file_path = None
    try:
        # Audio faylni yuklash
        temp_file_path = audio_processor.download_audio_from_url(audio_url, file_extension)
        
        if not temp_file_path:
            return None
        
        # Audio faylni matnga o'girish
        result = audio_processor.process_audio_message(temp_file_path, language)
        
        return result
        
    finally:
        # Vaqtincha faylni o'chirish
        if temp_file_path:
            audio_processor.cleanup_temp_file(temp_file_path)