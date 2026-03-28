import os
import asyncio
import logging
import traceback
from flask import request
from extensions import sock
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

@sock.route('/api/miniapp/live-stream/<int:bot_id>')
def live_audio_ws(ws, bot_id):
    """
    WebSocket endpoint for Gemini Live API audio streaming.
    Receives 16kHz PCM audio from frontend, sends to Gemini, and returns 24kHz PCM to frontend.
    """
    try:
        from models import Bot
        bot = Bot.query.get(bot_id)
        if not bot:
            ws.send("Error: Bot topilmadi")
            ws.close()
            return
            
        api_key = os.environ.get('GOOGLE_API_KEY') or os.environ.get('GOOGLE_API_KEY2')
        if not api_key:
            ws.send("Error: API Key topilmadi")
            ws.close()
            return

        client = genai.Client(api_key=api_key)
        
        # System instructions from bot's Knowledge Base
        system_instruction = ""
        from models import KnowledgeBase
        kb_entries = KnowledgeBase.query.filter_by(bot_id=bot_id).all()
        if kb_entries:
            for kb in kb_entries:
                if kb.content_type == 'text':
                    system_instruction += f"{kb.content}\n\n"
        
        if not system_instruction:
            system_instruction = "Sen foydali yordamchisan. Mijozlarga qisqa, aniq va yoqimli ovozda javob ber."

        async def run_live_session():
            config = {
                "response_modalities": ["AUDIO"],
                "system_instruction": {"parts": [{"text": system_instruction}]}
            }
            
            # Sessiya tugashini boshqarish uchun event
            session_active = asyncio.Event()
            session_active.set()
            
            try:
                async with client.aio.live.connect(model="gemini-3.1-flash-live-preview", config=config) as session:
                    logger.info(f"[LIVE] Connected to Gemini Live API for bot {bot_id}")
                    
                    # Task 1: Receive from Frontend and send to Gemini
                    async def ws_to_gemini():
                        chunks_sent = 0
                        try:
                            while session_active.is_set():
                                data = await asyncio.to_thread(ws.receive)
                                if data is None:
                                    logger.info(f"[LIVE] ws_to_gemini: received None, frontend disconnected")
                                    session_active.clear()
                                    break
                                
                                # Matn kelsa — e'tibor bermaymiz (VAD avtomatik boshqaradi)
                                if isinstance(data, str):
                                    logger.debug(f"[LIVE] ws_to_gemini: got text message: {data[:50]}")
                                    continue
                                
                                # Audio bytes kelsa — types.Blob orqali yuboramiz
                                if isinstance(data, bytes) and len(data) > 0:
                                    try:
                                        await session.send_realtime_input(
                                            audio=types.Blob(
                                                data=data,
                                                mime_type="audio/pcm;rate=16000"
                                            )
                                        )
                                        chunks_sent += 1
                                        if chunks_sent % 50 == 0:
                                            logger.info(f"[LIVE] ws_to_gemini: sent {chunks_sent} audio chunks to Gemini")
                                    except Exception as send_err:
                                        logger.error(f"[LIVE] ws_to_gemini: send_realtime_input error: {send_err}")
                                        # Bitta chunk xatosi butun sessiyani tugatmasin
                                        continue
                                        
                        except Exception as e:
                            logger.info(f"[LIVE] ws_to_gemini ended after {chunks_sent} chunks: {e}")
                        finally:
                            session_active.clear()
                            logger.info(f"[LIVE] ws_to_gemini: total chunks sent = {chunks_sent}")
                    
                    # Task 2: Receive from Gemini and send to Frontend
                    async def gemini_to_ws():
                        responses_received = 0
                        audio_chunks_received = 0
                        try:
                            while session_active.is_set():
                                # Har bir responseni alohida qabul qilish
                                async for response in session.receive():
                                    if not session_active.is_set():
                                        break
                                    
                                    responses_received += 1
                                    
                                    # Audio javoblarni tekshirish
                                    server_content = getattr(response, 'server_content', None)
                                    if server_content:
                                        # Turn complete signalini tekshirish
                                        turn_complete = getattr(server_content, 'turn_complete', False)
                                        if turn_complete:
                                            logger.info(f"[LIVE] gemini_to_ws: turn complete (response #{responses_received}, audio chunks: {audio_chunks_received})")
                                            # Turn tugadi, lekin sessiya davom etadi!
                                            continue
                                        
                                        model_turn = getattr(server_content, 'model_turn', None)
                                        if model_turn and model_turn.parts:
                                            for part in model_turn.parts:
                                                inline_data = getattr(part, 'inline_data', None)
                                                if inline_data and inline_data.data:
                                                    try:
                                                        await asyncio.to_thread(ws.send, inline_data.data)
                                                        audio_chunks_received += 1
                                                    except Exception as ws_err:
                                                        logger.error(f"[LIVE] gemini_to_ws: ws.send error: {ws_err}")
                                                        session_active.clear()
                                                        return
                                    
                                    # Boshqa turdagi javoblarni log qilish
                                    data_obj = getattr(response, 'data', None)
                                    if data_obj:
                                        logger.info(f"[LIVE] gemini_to_ws: got data response type")
                                
                                # async for loop tugadi — bu oddiy holat, Gemini sessiyani yopdi
                                logger.info(f"[LIVE] gemini_to_ws: session.receive() iterator ended")
                                break
                                
                        except Exception as e:
                            logger.error(f"[LIVE] gemini_to_ws ended: {e}")
                            logger.error(f"[LIVE] gemini_to_ws traceback: {traceback.format_exc()}")
                        finally:
                            session_active.clear()
                            logger.info(f"[LIVE] gemini_to_ws: total responses={responses_received}, audio_chunks={audio_chunks_received}")

                    # Ikkala taskni parallel ishga tushirish
                    logger.info(f"[LIVE] Starting gather for bot {bot_id}")
                    results = await asyncio.gather(
                        ws_to_gemini(), 
                        gemini_to_ws(),
                        return_exceptions=True
                    )
                    
                    # Xatolarni log qilish
                    for i, result in enumerate(results):
                        if isinstance(result, Exception):
                            logger.error(f"[LIVE] Task {i} raised exception: {result}")
                    
                    logger.info(f"[LIVE] Both tasks completed for bot {bot_id}")

            except Exception as e:
                logger.error(f"[LIVE] Gemini Live session error: {e}")
                logger.error(f"[LIVE] Session traceback: {traceback.format_exc()}")
                try:
                    await asyncio.to_thread(ws.send, "Error: Connection failed")
                except:
                    pass

        asyncio.run(run_live_session())
        
    except Exception as e:
        logger.error(f"[LIVE] WebSocket route error: {e}")
    finally:
        logger.info(f"[LIVE] WebSocket closed for bot {bot_id}")
