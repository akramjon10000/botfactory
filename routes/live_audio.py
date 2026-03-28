import os
import asyncio
import logging
import traceback
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
            config = types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                system_instruction=types.Content(
                    parts=[types.Part(text=system_instruction)]
                ),
            )
            
            try:
                async with client.aio.live.connect(
                    model="gemini-3.1-flash-live-preview", 
                    config=config
                ) as session:
                    logger.info(f"[LIVE] Connected to Gemini Live API for bot {bot_id}")
                    
                    async def send_audio():
                        """Frontenddan audio olib Gemini ga yuboradi"""
                        chunks = 0
                        try:
                            while True:
                                data = await asyncio.to_thread(ws.receive)
                                if data is None:
                                    logger.info("[LIVE] send_audio: frontend disconnected (None)")
                                    break
                                
                                if isinstance(data, str):
                                    logger.debug(f"[LIVE] send_audio: text msg ignored: {data[:30]}")
                                    continue
                                
                                if isinstance(data, bytes) and len(data) > 0:
                                    await session.send_realtime_input(
                                        audio=types.Blob(
                                            data=data,
                                            mime_type="audio/pcm;rate=16000"
                                        )
                                    )
                                    chunks += 1
                                    if chunks % 100 == 0:
                                        logger.info(f"[LIVE] send_audio: {chunks} chunks sent")
                        except Exception as e:
                            logger.error(f"[LIVE] send_audio error after {chunks} chunks: {e}")
                    
                    async def receive_audio():
                        """Geminidan javob olib frontendga yuboradi"""
                        turns = 0
                        audio_chunks = 0
                        try:
                            # session.receive() butun sessiya davomida iterate qilinadi
                            # BU FAQAT BIR MARTA CHAQIRILADI!
                            async for response in session.receive():
                                # server_content bor-yo'qligini tekshirish
                                if response.server_content:
                                    sc = response.server_content
                                    
                                    # Model audio javob bermoqda
                                    if sc.model_turn and sc.model_turn.parts:
                                        for part in sc.model_turn.parts:
                                            if part.inline_data and part.inline_data.data:
                                                try:
                                                    await asyncio.to_thread(ws.send, part.inline_data.data)
                                                    audio_chunks += 1
                                                except Exception as e:
                                                    logger.error(f"[LIVE] receive_audio: ws.send failed: {e}")
                                                    return
                                    
                                    # Turn tugadi — davom etamiz, sessiya yopilmaydi!
                                    if sc.turn_complete:
                                        turns += 1
                                        logger.info(f"[LIVE] receive_audio: turn #{turns} complete, total audio chunks: {audio_chunks}")
                                        # DAVOM ETAMIZ - keyingi turn ni kutamiz
                                        
                                    # Interrupted - model gapirayotganda foydalanuvchi gapirib yubordi
                                    interrupted = getattr(sc, 'interrupted', False)
                                    if interrupted:
                                        logger.info(f"[LIVE] receive_audio: model interrupted by user")
                                        
                        except Exception as e:
                            logger.error(f"[LIVE] receive_audio error: {e}")
                            logger.error(f"[LIVE] receive_audio traceback: {traceback.format_exc()}")
                        finally:
                            logger.info(f"[LIVE] receive_audio ended: turns={turns}, audio_chunks={audio_chunks}")

                    # Ikkala taskni parallel ishga tushirish
                    logger.info(f"[LIVE] Starting parallel tasks for bot {bot_id}")
                    
                    send_task = asyncio.create_task(send_audio())
                    receive_task = asyncio.create_task(receive_audio())
                    
                    # Birinchi tugagan task — ikkinchisini ham to'xtatamiz
                    done, pending = await asyncio.wait(
                        [send_task, receive_task],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    # Qolgan taskni cancel qilamiz
                    for task in pending:
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
                    
                    # Xatolarni tekshirish
                    for task in done:
                        if task.exception():
                            logger.error(f"[LIVE] Task exception: {task.exception()}")
                    
                    logger.info(f"[LIVE] Session ended for bot {bot_id}")

            except Exception as e:
                logger.error(f"[LIVE] Session connection error: {e}")
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
