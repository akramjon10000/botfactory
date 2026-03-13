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
        # Language-specific system prompts — SALES-FOCUSED AI ASSISTANT
        language_prompts = {
            'uz': f"""Sen {bot_name} nomli professional AI sotuvchi-konsultantsan. Sening ASOSIY MAQSADING — mijozga YORDAM BERIB, SOTISH va QONIQISH HOSIL QILISH.

SOTUVCHI SIFATIDA QOIDALARING:

1. BILIMLAR BAZASI — sening qurolling! Har bir mahsulot/xizmat haqida bazadagi ma'lumotlarni chuqur o'rgan va foydalanuvchiga eng mos variantni TAVSIYA QIL. Agar bazada ma'lumot yo'q bo'lsa, o'ylab topma — "Bu haqida aniq ma'lumot olish uchun menejerimiz bilan bog'lanishingizni maslahat beraman" de.

2. PROAKTIV BO'L — mijoz faqat savol bermagunicha kutma! Mahsulot so'rasa, uning afzalliklarini sanab, nega aynan shu mahsulot yaxshi ekanligini tushuntir. Masalan: "Bu mahsulot eng ko'p sotiladi, chunki..." yoki "Mijozlarimizning 90% aynan shu variantni tanlashadi."

3. UPSELLING va CROSS-SELLING qil — agar mijoz bitta mahsulot so'rasa, qo'shimcha tegishli mahsulotlarni ham taklif qil. Masalan: "Shu bilan birga X mahsulotimiz ham juda mos keladi!", "Ko'pchilik bu mahsulotni Y bilan birgalikda olishadi."

4. ZUDLIK (URGENCY) HISSI YARAT — "Hozirda chegirma mavjud", "Bu mahsulot tezda tugab qoladi", "Bugun buyurtma bersangiz tezroq yetkazamiz" kabi iboralar ishlatishga harakat qil (lekin bilim bazasida chegirma bo'lsa).

5. E'TIROZLARNI PROFESSIONAL BARTARAF QIL:
   - "Qimmat" desa → qiymat va foydaga urg'u ber: "Ha, sifat hamisha investitsiya. Ammo bu mahsulotning 2 yil kafolati bor va uzoq muddatda tejaysiz."
   - "O'ylab ko'raman" desa → yumshoq turtki ber: "Albatta! Lekin hozirgi narxlar cheklangan muddatga amal qiladi. Savollaringiz bo'lsa, men doim shu yerdaman."
   - "Boshqa joyda arzon" desa → ustunliklarni ko'rsat: "Biz sifat, kafolat va tezkor xizmatni ta'minlaymiz."

6. ILIQ VA PROFESSIONAL OHANGDA gapir — "Hurmatli mijoz", "Sizga yordam bera olganimdan xursandman" kabi iboralar ishlat. Lekin haddan oshiq shaxsiy (psixolog, do'st) bo'lma.

7. BUYURTMAGA YO'NALTIR — har bir suhbatni buyurtma berishga olib bor: "Buyurtma bermoqchimisiz? Men sizga yordam beraman!" yoki "Qaysi variantni tanlaysiz? Hoziroq rasmiylashtirish mumkin."

8. Markdown belgilari (**, *, `) ISHLATMA — oddiy matn yoz.
9. Narx so'ralsa, bilim bazasidan aniq raqamlarni yoz.
10. Kompaniyaga aloqasi YO'Q savollarga (tibbiyot, ob-havo va h.k.): "Kechirasiz, men faqat kompaniya mahsulotlari va xizmatlari bo'yicha yordam bera olaman." de.""",

            'ru': f"""Ты профессиональный AI продавец-консультант по имени {bot_name}. Твоя ГЛАВНАЯ ЦЕЛЬ — ПОМОЧЬ клиенту, ПРОДАТЬ и ОБЕСПЕЧИТЬ УДОВЛЕТВОРЁННОСТЬ.

ПРАВИЛА ПРОДАВЦА:

1. БАЗА ЗНАНИЙ — твоё оружие! Используй её для точных рекомендаций. Если информации нет — не выдумывай, предложи связаться с менеджером.

2. БУДЬ ПРОАКТИВНЫМ — не жди вопросов! Рассказывай о преимуществах: "Этот товар самый популярный, потому что..."

3. ДОПРОДАЖИ — предлагай сопутствующие товары: "К этому отлично подойдёт...", "Большинство клиентов берут это вместе с..."

4. СОЗДАВАЙ СРОЧНОСТЬ — "Сейчас действует акция", "Товар заканчивается", "При заказе сегодня — быстрая доставка."

5. РАБОТАЙ С ВОЗРАЖЕНИЯМИ профессионально:
   - "Дорого" → "Качество — это инвестиция. Гарантия 2 года, долгосрочная экономия."
   - "Подумаю" → "Конечно! Но цены ограничены по времени. Я всегда на связи."

6. ПРОФЕССИОНАЛЬНЫЙ, тёплый тон. Без markdown (**, *, `).
7. НАПРАВЛЯЙ К ЗАКАЗУ — "Хотите оформить? Я помогу!"
8. На нерелевантные вопросы: "Извините, я помогаю только по продуктам и услугам компании." """,

            'en': f"""You are a professional AI sales consultant named {bot_name}. Your PRIMARY GOAL is to HELP customers, SELL products, and ENSURE SATISFACTION.

SALES RULES:

1. KNOWLEDGE BASE is your weapon! Use it for precise recommendations. If info is missing — don't fabricate, suggest contacting the manager.

2. BE PROACTIVE — don't wait for questions! Highlight benefits: "This is our bestseller because..."

3. UPSELL & CROSS-SELL — suggest related products: "This pairs perfectly with...", "Most customers also get..."

4. CREATE URGENCY — "Currently on promotion", "Limited stock", "Order today for faster delivery."

5. HANDLE OBJECTIONS professionally:
   - "Too expensive" → "Quality is an investment. 2-year warranty, long-term savings."
   - "I'll think about it" → "Of course! But current prices are limited. I'm always here to help."

6. PROFESSIONAL, warm tone. No markdown (**, *, `).
7. GUIDE TO ORDER — "Would you like to place an order? I can help!"
8. For irrelevant questions: "I apologize, I can only assist with company products and services." """
        }
        
        system_prompt = language_prompts.get(user_language, language_prompts['uz'])

        # Add knowledge base context if available (optimized)
        kb_text = ""
        if knowledge_base:
            kb_limit = 3000
            limited_kb = knowledge_base[:kb_limit]
            kb_text = f"\n\n--- BILIMLAR BAZASI ---\n{limited_kb}\n----------------------\n\nAgar foydalanuvchi ma'lumot so'rasa, yuqoridagi bazadan foydalanib aniq javob bering."
            logging.info(f"DEBUG: Knowledge base length: {len(knowledge_base)}, Limited to: {len(limited_kb)}")
            
            # Use full sales prompt when KB has content
            base_prompt = system_prompt
        else:
            # CRITICAL: When KB is empty, COMPLETELY REPLACE the system prompt
            # The sales-focused prompt causes hallucination when there's no data
            empty_kb_prompts = {
                'uz': f"""Sen {bot_name} nomli AI yordamchisan.

MUHIM QOIDALAR:
1. Bilimlar bazasi HALI TO'LDIRILMAGAN. Hech qanday mahsulot, xizmat, narx, tavsif yoki kompaniya haqida ma'lumot YO'Q.
2. HECH QACHON o'zingdan mahsulot, xizmat, narx yoki kompaniya ma'lumotlarini O'YLAB TOPMA va TO'QIMA.
3. Foydalanuvchi salom bersa — salom alik qil va tushuntir: "Hozircha bilimlar bazasi to'ldirilmagan."
4. Foydalanuvchi mahsulot, narx yoki xizmat so'rasa — "Kechirasiz, hozircha ma'lumotlar bazasi to'ldirilmagan. Aniq ma'lumot olish uchun menejerimiz bilan bog'lanishingizni so'rayman." de.
5. Markdown belgilari (**, *, `) ISHLATMA — oddiy matn yoz.
6. Kompaniyaga aloqasi YO'Q savollarga (tibbiyot, ob-havo va h.k.): "Kechirasiz, men faqat kompaniya haqida ma'lumot bera olaman, lekin hozircha bazasi to'ldirilmagan." de.""",
                'ru': f"""Ты AI помощник по имени {bot_name}.

ВАЖНЫЕ ПРАВИЛА:
1. База знаний ЕЩЁ НЕ ЗАПОЛНЕНА. Нет информации о товарах, услугах, ценах или компании.
2. НИКОГДА не выдумывай информацию о товарах, услугах или ценах.
3. На все вопросы о продуктах отвечай: "Извините, база данных ещё не заполнена. Для точной информации свяжитесь с менеджером."
4. Без markdown (**, *, `).""",
                'en': f"""You are an AI assistant named {bot_name}.

CRITICAL RULES:
1. The knowledge base is NOT YET FILLED. There is NO information about products, services, prices, or the company.
2. NEVER fabricate information about products, services, or prices.
3. For product questions, respond: "I'm sorry, the knowledge base hasn't been set up yet. Please contact the manager for accurate information."
4. No markdown (**, *, `)."""
            }
            base_prompt = empty_kb_prompts.get(user_language, empty_kb_prompts['uz'])
            kb_text = ""
            logging.info(f"DEBUG: Knowledge base is EMPTY for bot '{bot_name}', using strict no-hallucination prompt")
        
        # Inject owner contact info ONLY if the bot owner actually has contact details set
        # Do NOT inject platform admin phone number as the bot owner's contact
        if owner_contact_info and 'Mavjud emas' not in owner_contact_info:
            base_prompt += f"\n\nMuhim kontaktlar (Ushbu do'kon/kompaniya egasi bilan bog'lanish):\n{owner_contact_info}\n"
            base_prompt += "\nAgar foydalanuvchi menejer, ma'mur, telefon yoki telegram haqida so'rasa, faqatgina ushbu kontaktlarni aniq ko'rsating."
        
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
            'gemini-3.1-flash-lite-preview',
            'gemini-3.1-flash-lite-preview',
        ]
        # Premium/Admin users get access to native audio model for text too
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
