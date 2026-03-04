import os
import logging
from typing import Optional
from flask import current_app

try:
    import google.generativeai as genai
    # Initialize Gemini client
    genai.configure(api_key=os.environ.get("GOOGLE_API_KEY", "default_key"))
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("Google Generative AI library not available. Install with: pip install google-generativeai")

def get_ai_response(message: str, bot_name: str = "Chatbot Factory AI", user_language: str = "uz", knowledge_base: str = "", chat_history: str = "") -> Optional[str]:
    """
    Generate AI response using Google Gemini with chat history context
    """
    try:
        # Language-specific system prompts with strict domain boundaries
        language_prompts = {
            'uz': f"Sen {bot_name} nomli sun'iy intellekt botisan. Sening YAGONA vazifang – KOMPANIYA ASSISTENTI (Sotuvchi/Konsultant) sifatida xizmat qilish. \n\nQAT'IY QOIDALAR (BUZISH MUMKIN EMAS):\n1. FAQAT BILIMLAR BAZASIDAN (Knowledge Base) foydalan! Agar mijoz so'ragan ma'lumot bilim bazasida YO'Q BO'LSA, o'zingdan hech narsa o'ylab topma (gallutsinatsiya taqiqlanadi). Shunchaki yoz: 'Kechirasiz, menda hozircha bu haqida ma'lumot yo'q.'\n2. Sen psixolog, shifokor yoki do'st emassan! Hissiyotlarga berilma. 'Oh azizim' kabi so'zlarni ishlatma.\n3. Tibbiyot, ob-havo, kayfiyat yoxud kompaniyadan tashqari har qanday savolga faqat quyidagicha rad javobi ber: 'Kechirasiz, men faqat kompaniya mahsulotlari va xizmatlari bo'yicha yordam bera olaman.' va ortiqcha gap yozma.\n4. O'zbek tilida, rasmiy ohangda javob qaytar.\n5. Markdown belgilari (**, *, `) ISHLATISH TAQIQLANADI.\n6. Narx so'ralsa, bilim bazasidan 'Narx:' qatorini izlab, aniq raqamlarni yoz.",
            'ru': f"Ты бот искусственного интеллекта по имени {bot_name}. Твоя ЕДИНСТВЕННАЯ задача — служить АССИСТЕНТОМ КОМПАНИИ. \n\nСТРОГИЕ ПРАВИЛА (НЕ НАУШАТЬ):\n1. ИСПОЛЬЗУЙ ТОЛЬКО БАЗУ ЗНАНИЙ (Knowledge Base)! Если информации нет в базе, ничего не придумывай (галлюцинации запрещены). Просто напиши: 'Извините, у меня пока нет информации об этом.'\n2. Ты не психолог, не врач и не друг! Никаких эмоций и сочувствия.\n3. На вопросы о медицине, погоде, настроении или любые сторонние темы отвечай КРАТКО: 'Извините, я могу помочь только с продуктами и услугами компании.' и больше ничего не добавляй.\n4. Отвечай на русском языке в профессиональном тоне.\n5. ЗАПРЕЩАЕТСЯ использовать символы markdown (**, *, `).\n6. Если спрашивают цену, ищи 'Narx:' в базе знаний и указывай точно.",
            'en': f"You are an AI bot named {bot_name}. Your ONLY role is to serve as a COMPANY ASSISTANT. \n\nSTRICT RULES (DO NOT VIOLATE):\n1. USE ONLY THE KNOWLEDGE BASE! If the requested info is NOT in the knowledge base, do not invent answers (no hallucinations). Simply state: 'I apologize, but I do not have information about this at the moment.'\n2. You are not a psychologist, doctor, or friend! No emotions or empathy.\n3. For questions about medicine, weather, mood, or anything unrelated to the company, reply ONLY WITH: 'I apologize, but I can only assist with the company's products and services.' Add nothing else.\n4. Respond in English, in a professional and formal tone.\n5. FORBIDDEN to use markdown symbols (**, *, `).\n6. If price is requested, search for 'Narx:' in the knowledge base and state it clearly."
        }
        
        system_prompt = language_prompts.get(user_language, language_prompts['uz'])

        # Inject platform contact info so bot can answer contact-related questions precisely
        try:
            support_phone = (current_app.config.get('SUPPORT_PHONE') or '').strip()
            support_tg = (current_app.config.get('SUPPORT_TELEGRAM') or '').strip()
            contact_block = []
            if support_phone:
                contact_block.append(f"Admin telefon raqami: {support_phone}")
            if support_tg:
                contact_block.append(f"Telegram aloqa: {support_tg}")
            if contact_block:
                system_prompt += "\n\nMuhim kontaktlar (ishga tushirilgan platforma sozlamalaridan):\n" + "\n".join(contact_block) + "\n" 
                system_prompt += "\nAgar foydalanuvchi telefon yoki telegram haqida so'rasa, yuqoridagi kontaktlarni aniq ko'rsating."
        except Exception:
            pass
        
        # Base prompt protection
        base_prompt = system_prompt
        
        # Add knowledge base context if available (optimized)
        kb_text = ""
        if knowledge_base:
            kb_limit = 3000  # Increased slightly since we are not merging directly into system_prompt initially
            limited_kb = knowledge_base[:kb_limit]
            kb_text = f"\n\n--- BILIMLAR BAZASI ---\n{limited_kb}\n----------------------\n\nAgar foydalanuvchi ma'lumot so'rasa, yuqoridagi bazadan foydalanib aniq javob bering."
            logging.info(f"DEBUG: Knowledge base length: {len(knowledge_base)}, Limited to: {len(limited_kb)}")
        
        # Add chat history context if available
        history_text = ""
        if chat_history:
            history_text = f"\n\n--- OLDINGI SUHBATLAR (XOTIRA) ---\n{chat_history}\n----------------------------------\n\nSuhbat kontekstini eslab qoling, va foydalanuvchining joriy savoliga oldingi gaplarga asoslanib mantiqiy javob qaytaring."
        
        # Build the final prompt cleanly without truncating the critical persona rules
        full_prompt = f"{base_prompt}{kb_text}{history_text}\n\nFoydalanuvchi joriy xabari: {message}"

        
        # Generate response using Gemini with optimization settings
        if not GEMINI_AVAILABLE:
            return get_fallback_response(user_language)
            
        # Use faster model configuration for quicker responses
        generation_config = genai.types.GenerationConfig(
            temperature=0.7,  # Slightly lower for faster generation
            max_output_tokens=2000,  # Increased to prevent response truncation
            top_p=0.9,
            top_k=40
        )
        
        # Multi-API key and model fallback support
        api_keys = [
            os.environ.get("GOOGLE_API_KEY"),
            os.environ.get("GOOGLE_API_KEY2"),
        ]
        models = [
            'gemini-2.5-flash',
            'gemini-2.5-flash-lite',
        ]
        
        last_error = None
        for api_key in api_keys:
            if not api_key:
                continue
            for model_name in models:
                try:
                    genai.configure(api_key=api_key)
                    model = genai.GenerativeModel(
                        model_name,
                        generation_config=generation_config
                    )
                    response = model.generate_content(full_prompt)
                    
                    if response.text:
                        logging.info(f"AI response success with model: {model_name}")
                        return response.text
                except Exception as model_error:
                    last_error = model_error
                    logging.warning(f"Model {model_name} failed: {str(model_error)[:100]}")
                    continue
        
        # If all attempts failed, raise the last error
        if last_error:
            raise last_error
        return get_fallback_response(user_language)
            
    except Exception as e:
        # Safe error logging to prevent encoding issues  
        try:
            error_msg = str(e)
            unicode_replacements = {
                '\u2019': "'", '\u2018': "'", '\u201c': '"', '\u201d': '"',
                '\u2013': '-', '\u2014': '-', '\u2026': '...', '\u00a0': ' ',
                '\u2010': '-', '\u2011': '-', '\u2012': '-', '\u2015': '-'
            }
            
            for unicode_char, replacement in unicode_replacements.items():
                error_msg = error_msg.replace(unicode_char, replacement)
            
            error_msg = error_msg.encode('ascii', errors='ignore').decode('ascii')
            logging.error(f"AI response error: {error_msg}")
        except:
            logging.error("AI response error: Unicode encoding issue")
        return get_fallback_response(user_language)

def get_fallback_response(language: str = "uz") -> str:
    """
    Fallback responses when AI fails
    """
    fallback_responses = {
        'uz': "Salom! Men BotFactory AI botiman. Hozir AI xizmat sozlanmoqda. Tez orada sizga yordam bera olaman! 🤖 Savollaringizni yuboring, men eslab qolaman.",
        'ru': "Привет! Я BotFactory AI бот. Сейчас настраивается AI сервис. Скоро смогу помочь вам! 🤖 Присылайте вопросы, я их запомню.",
        'en': "Hello! I'm BotFactory AI bot. AI service is being configured now. I'll be able to help you soon! 🤖 Send your questions, I'll remember them."
    }
    return fallback_responses.get(language, fallback_responses['uz'])

def process_knowledge_base(bot_id: int) -> str:
    """
    Process and combine knowledge base content for a bot
    """
    from models import KnowledgeBase
    
    try:
        knowledge_entries = KnowledgeBase.query.filter_by(bot_id=bot_id).all()
        combined_knowledge = ""
        
        # Debug: log bilim bazasi mavjudligi
        logging.info(f"DEBUG: Bot {bot_id} uchun {len(knowledge_entries)} ta bilim bazasi yozuvi topildi")
        
        for entry in knowledge_entries:
            logging.info(f"DEBUG: Processing entry - Type: {entry.content_type}, Source: {entry.source_name}")
            
            if entry.content_type == 'product':
                # For products, format them clearly for AI with detailed structure
                product_text = f"=== MAHSULOT MA'LUMOTI ===\n{entry.content}\n=== MAHSULOT OXIRI ===\n"
                combined_knowledge += product_text + "\n"
                logging.info(f"DEBUG: Product added to knowledge: {entry.source_name}")
            elif entry.content_type == 'image':
                # For images, add description about the image
                image_info = f"Rasm: {entry.filename or 'Yuklangan rasm'}"
                if entry.source_name:
                    image_info += f" ({entry.source_name})"
                image_info += f" - bu mahsulot/xizmat haqidagi vizual ma'lumot. Foydalanuvchi ushbu rasm haqida so'rasa, unga rasm haqida ma'lumot bering."
                combined_knowledge += f"{image_info}\n\n"
                logging.info(f"DEBUG: Image added to knowledge: {entry.source_name or entry.filename}")
            else:
                # For text and file content
                combined_knowledge += f"{entry.content}\n\n"
                logging.info(f"DEBUG: File content added to knowledge: {entry.filename}")
        
        logging.info(f"DEBUG: Combined knowledge length: {len(combined_knowledge)} characters")
        if combined_knowledge:
            logging.info(f"DEBUG: First 200 chars of knowledge: {combined_knowledge[:200]}...")
        
        return combined_knowledge.strip()
    except Exception as e:
        logging.error(f"Knowledge base processing error: {str(e)}")
        return ""

def find_relevant_product_images(bot_id: int, user_message: str) -> list:
    """
    Find the most relevant product image based on user's message
    Returns only the best matching product, not all products
    """
    from models import KnowledgeBase
    
    try:
        # Get products that match user's message
        products = KnowledgeBase.query.filter_by(bot_id=bot_id, content_type='product').all()
        
        if not products:
            return []
        
        user_message_lower = user_message.lower()
        user_words = [word.strip() for word in user_message_lower.split() if len(word.strip()) > 2]
        
        best_match = None
        best_score = 0
        
        for product in products:
            product_content = product.content.lower()
            product_name = (product.source_name or "").lower()
            
            # Calculate relevance score
            score = 0
            
            # Extract product name from content
            lines = product.content.split('\n')
            actual_product_name = ""
            for line in lines:
                if line.startswith('Mahsulot:'):
                    actual_product_name = line.replace('Mahsulot:', '').strip().lower()
                    break
            
            # High score for exact product name match
            if actual_product_name:
                for user_word in user_words:
                    if user_word in actual_product_name:
                        score += 10
                        
            # Medium score for source name match
            if product_name:
                for user_word in user_words:
                    if user_word in product_name:
                        score += 5
                        
            # Low score for content match (but avoid generic words)
            generic_words = ['mahsulot', 'narx', 'som', 'dollar', 'paket', 'zip', 'rasm', 'tavsif', 'haqida']
            for user_word in user_words:
                if user_word not in generic_words and user_word in product_content:
                    score += 1
            
            # Only consider products with images
            has_image = False
            image_url = ""
            for line in lines:
                if line.startswith('Rasm:') and 'http' in line:
                    image_url = line.replace('Rasm:', '').strip()
                    has_image = True
                    break
            
            # Update best match if this product scores higher and has an image
            if has_image and score > best_score:
                best_score = score
                best_match = {
                    'url': image_url,
                    'product_name': product.source_name or actual_product_name or 'Mahsulot',
                    'caption': f"📦 {product.source_name or actual_product_name or 'Mahsulot'}"
                }
        
        # Return only the best match, or empty list if no good match found
        if best_match and best_score >= 3:  # Minimum score threshold
            return [best_match]
        else:
            return []
            
    except Exception as e:
        logging.error(f"Error finding product images: {str(e)}")
        return []

def validate_ai_response(response: Optional[str], max_length: int = 4000) -> Optional[str]:
    """
    Validate and clean AI response
    """
    if not response:
        return None
    
    # Remove markdown formatting
    response = response.replace('**', '').replace('*', '').replace('`', '')
    
    # Limit response length
    if len(response) > max_length:
        response = response[:max_length] + "..."
    
    return response.strip()
