import os
import logging
from typing import Optional

try:
    import google.generativeai as genai
    # Initialize Gemini client
    genai.configure(api_key=os.environ.get("GOOGLE_API_KEY", "default_key"))
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("Google Generative AI library not available. Install with: pip install google-generativeai")

def get_ai_response(message: str, bot_name: str = "Chatbot Factory AI", user_language: str = "uz", knowledge_base: str = "", chat_history: str = "", owner_contact_info: str = "", subscription_tier: str = "free") -> Optional[str]:
    """
    Generate AI response using Google Gemini with chat history context
    """
    try:
        # Language-specific system prompts — CONCISE SALES AI
        language_prompts = {
            'uz': f"""Sen {bot_name} nomli AI sotuvchi-konsultantsan.

QOIDALAR:
1. QISQA va ANIQ yoz! Har bir javob 2-3 gapdan iborat bo'lsin. Uzun matnlar YOZMA.
2. Faqat BILIMLAR BAZASIDAGI ma'lumotlarga tayangan holda javob ber. Bazada yo'q narsani O'YLAB TOPMA.
3. Bazada ma'lumot topa olmasang: "Aniq ma'lumot uchun menejerimizga murojaat qiling" de.
4. Narx so'ralsa — faqat bazadagi aniq narxni yoz.
5. Markdown (**, *, `) ISHLATMA.
6. Kompaniyaga aloqasi yo'q savolga: "Kechirasiz, men faqat kompaniya mahsulotlari bo'yicha yordam beraman." de.""",

            'ru': f"""Ты AI продавец-консультант {bot_name}.

ПРАВИЛА:
1. Пиши КРАТКО и ТОЧНО! Каждый ответ — 2-3 предложения максимум.
2. Отвечай ТОЛЬКО на основе БАЗЫ ЗНАНИЙ. Не выдумывай то, чего нет в базе.
3. Если нет информации: "Для точной информации свяжитесь с менеджером."
4. Без markdown (**, *, `).
5. На нерелевантное: "Извините, я помогаю только по продуктам компании." """,

            'en': f"""You are {bot_name} AI sales consultant.

RULES:
1. Keep responses SHORT — 2-3 sentences max. No long texts.
2. Answer ONLY from KNOWLEDGE BASE. Never fabricate info.
3. If info missing: "Please contact our manager for details."
4. No markdown (**, *, `).
5. Off-topic: "Sorry, I can only help with company products." """
        }
        
        system_prompt = language_prompts.get(user_language, language_prompts['uz'])

        # Add knowledge base context if available
        kb_text = ""
        if knowledge_base:
            kb_limit = 3000
            limited_kb = knowledge_base[:kb_limit]
            kb_text = f"\n\n--- BILIMLAR BAZASI ---\n{limited_kb}\n----------------------\nYuqoridagi bazadan foydalanib qisqa va aniq javob ber."
            logging.info(f"DEBUG: Knowledge base length: {len(knowledge_base)}, Limited to: {len(limited_kb)}")
            
            base_prompt = system_prompt
        else:
            # CRITICAL: KB is empty — use strict no-hallucination prompt
            empty_kb_prompts = {
                'uz': f"""Sen {bot_name} AI yordamchisan. Bilimlar bazasi HALI TO'LDIRILMAGAN.

QATIY QOIDALAR:
1. Hech qanday mahsulot, narx, xizmat haqida ma'lumot YO'Q. O'YLAB TOPMA.
2. Salom bersa — qisqa salomlash va "Hozircha bazamiz to'ldirilmagan" de.
3. Har qanday savol uchun: "Kechirasiz, hozircha ma'lumotlar bazasi to'ldirilmagan. Menejerimiz bilan bog'laning." de.
4. QISQA yoz — 1-2 gap yetarli. Markdown ISHLATMA.""",
                'ru': f"""Ты AI помощник {bot_name}. База знаний НЕ ЗАПОЛНЕНА.

СТРОГИЕ ПРАВИЛА:
1. НЕТ информации о товарах, ценах, услугах. НЕ ВЫДУМЫВАЙ.
2. На любой вопрос: "Извините, база данных ещё не заполнена. Свяжитесь с менеджером."
3. Пиши кратко — 1-2 предложения. Без markdown.""",
                'en': f"""You are {bot_name} AI assistant. Knowledge base is NOT FILLED.

STRICT RULES:
1. NO product, price, or service info exists. DO NOT FABRICATE.
2. For any question: "Sorry, the database isn't set up yet. Please contact the manager."
3. Keep answers to 1-2 sentences. No markdown."""
            }
            base_prompt = empty_kb_prompts.get(user_language, empty_kb_prompts['uz'])
            kb_text = ""
            logging.info(f"DEBUG: KB EMPTY for bot '{bot_name}', using no-hallucination prompt")
        
        # Inject owner contact info ONLY if bot owner actually set their details
        if owner_contact_info and 'Mavjud emas' not in owner_contact_info:
            base_prompt += f"\n\nKontaktlar:\n{owner_contact_info}"
        
        # Chat history context
        history_text = ""
        if chat_history:
            history_text = f"\n\nOldingi suhbat:\n{chat_history}\n\nKontekstni hisobga olib javob ber."
        
        full_prompt = f"{base_prompt}{kb_text}{history_text}\n\nMijoz xabari: {message}"

        
        # Generate response using Gemini with optimization settings
        if not GEMINI_AVAILABLE:
            return get_fallback_response(user_language)
            
        # Use faster model configuration for quicker responses
        generation_config = genai.types.GenerationConfig(
            temperature=0.7,
            max_output_tokens=500,  # Enforce shorter responses (approx 350-400 words)
            top_p=0.9,
            top_k=40
        )
        
        # Multi-API key and model fallback support
        api_keys = [
            os.environ.get("GOOGLE_API_KEY"),
            os.environ.get("GOOGLE_API_KEY3"),
            os.environ.get("GOOGLE_API_KEY2"),
        ]
        models = [
            'gemini-3.1-flash-lite-preview',
            'gemini-3.1-flash-lite-preview',
        ]
        # Premium/Admin users get access to best models
        # NOTE: gemini-3.1-flash-live-preview faqat Live API (streaming) bilan ishlaydi,
        # generate_content() bilan emas. Text javoblar uchun quyidagi modellar ishlatiladi.
        if subscription_tier in ('premium', 'admin'):
            models = [
                'gemini-2.5-flash-preview-native-audio',
                'gemini-3.1-flash-lite-preview',
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
        except Exception:
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

def _format_entry(entry):
    """Helper to format a single knowledge base entry"""
    if entry.content_type == 'product':
        return f"=== MAHSULOT ===\nNomi: {entry.source_name}\nTavsif: {entry.content}\n================"
    elif entry.content_type == 'image':
        info = f"Rasm: {entry.filename or 'Yuklangan rasm'}"
        if entry.source_name:
            info += f" ({entry.source_name})"
        return info + f" - bu mahsulot/xizmat haqidagi vizual ma'lumot."
    else:
        # Prefix file name if it's a file
        if entry.content_type == 'file' and entry.source_name:
            return f"[{entry.source_name} hujjatidan]:\n{entry.content}"
        return entry.content

def get_relevant_knowledge(entries, user_message: str, max_chars=3000) -> str:
    """Score knowledge base entries against user message for RAG"""
    if not user_message:
        combined = ""
        for e in entries:
            combined += _format_entry(e) + "\n\n"
        return combined[:max_chars]
        
    # Extract keywords from user message
    user_words = set(word.strip().lower() for word in user_message.split() if len(word.strip()) > 2)
    
    scored_entries = []
    for entry in entries:
        content = entry.content or ""
        source_name = entry.source_name or ""
        content_words = set(word.strip().lower() for word in (content + " " + source_name).split())
        
        # Calculate overlap
        overlap = len(user_words.intersection(content_words))
        
        # Boost for exact matches and multiple occurrences
        score = overlap * 2
        content_lower = content.lower()
        source_lower = source_name.lower()
        for word in user_words:
            if word in source_lower:
                score += 5 # high boost for title matching
            score += content_lower.count(word)
            
        scored_entries.append((score, entry))
        
    # Sort by score highest first
    scored_entries.sort(key=lambda x: x[0], reverse=True)
    
    # Priority debugging
    top_sources = [f"{e[1].source_name} (score: {e[0]})" for e in scored_entries[:3]]
    logging.info(f"RAG Top Matches: {', '.join(top_sources)}")
    
    # Take top entries until we hit max_chars
    combined = ""
    for score, entry in scored_entries:
        entry_text = _format_entry(entry)
        
        if len(combined) + len(entry_text) > max_chars:
            if not combined: # at least add one even if it truncates
                combined = entry_text[:max_chars]
            break
        combined += entry_text + "\n\n"
        
    return combined.strip()

def process_knowledge_base(bot_id: int, user_message: str = None) -> str:
    """
    Process and retrieve relevant knowledge base content for a bot using basic RAG.
    """
    from models import KnowledgeBase
    
    try:
        knowledge_entries = KnowledgeBase.query.filter_by(bot_id=bot_id).all()
        if not knowledge_entries:
            return ""
            
        logging.info(f"DEBUG: Processing {len(knowledge_entries)} knowledge entries for bot {bot_id}...")
        
        # Use RAG retrieval if message is provided
        combined_knowledge = get_relevant_knowledge(knowledge_entries, user_message)
        
        logging.info(f"DEBUG: Combined knowledge length: {len(combined_knowledge)} characters")
        return combined_knowledge
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
