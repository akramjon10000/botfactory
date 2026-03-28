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
        
        # System instructions from bot's Knowledge Base (barcha turlarni yuklash)
        from ai import process_knowledge_base
        knowledge_text = process_knowledge_base(bot_id)
        
        bot_name = bot.name or "AI Yordamchi"
        
        if knowledge_text:
            system_instruction = f"""Sen {bot_name} nomli AI sotuvchi-konsultantsan. Ovoz orqali mijozlarga yordam berasan.

QOIDALAR:
1. QISQA va ANIQ gapir! Har bir javob 2-3 gapdan iborat bo'lsin.
2. Faqat BILIMLAR BAZASIDAGI ma'lumotlarga tayanib javob ber. Bazada yo'q narsani O'YLAB TOPMA.
3. Bazada ma'lumot topa olmasang: "Aniq ma'lumot uchun menejerimizga murojaat qiling" de.
4. Narx so'ralsa — faqat bazadagi aniq narxni ayt.
5. Yoqimli, do'stona va professional ovozda gapir.

--- BILIMLAR BAZASI ---
{knowledge_text}
-----------------------
Yuqoridagi bazadan foydalanib qisqa va aniq javob ber."""
        else:
            system_instruction = f"""Sen {bot_name} AI yordamchisan. Bilimlar bazasi hali to'ldirilmagan.
Salom bersa — qisqa salomlash. Har qanday savol uchun: "Kechirasiz, hozircha ma'lumotlar bazasi to'ldirilmagan. Menejerimiz bilan bog'laning." de.
Qisqa gapir — 1-2 gap yetarli."""

        async def run_live_session():
            config = types.LiveConnectConfig(
                response_modalities=["AUDIO"],
                system_instruction=types.Content(
                    parts=[types.Part(text=system_instruction)]
                ),
            )
            
            client_connected = True
            reconnect_count = 0
            
            while client_connected:
                try:
                    async with client.aio.live.connect(
                        model="gemini-3.1-flash-live-preview", 
                        config=config
                    ) as session:
                        logger.info(f"[LIVE] Connected to Gemini API (reconnects: {reconnect_count}) for bot {bot_id}")
                        reconnect_count += 1
                        
                        async def send_audio():
                            nonlocal client_connected
                            chunks = 0
                            try:
                                while client_connected:
                                    try:
                                        data = await asyncio.to_thread(ws.receive)
                                        if data is None:
                                            logger.info("[LIVE] send_audio: frontend disconnected (None)")
                                            client_connected = False
                                            break
                                            
                                        if isinstance(data, str):
                                            continue
                                            
                                        if isinstance(data, bytes) and len(data) > 0:
                                            try:
                                                await session.send_realtime_input(
                                                    audio=types.Blob(
                                                        data=data,
                                                        mime_type="audio/pcm;rate=16000"
                                                    )
                                                )
                                                chunks += 1
                                            except Exception as send_err:
                                                # Ignore single chunk errors, log at debug so it doesn't crash the loop!
                                                logger.debug(f"[LIVE] API chunk send error: {send_err}")
                                    except Exception as ws_err:
                                        # Likely simple_websocket.ConnectionClosed from user leaving
                                        logger.info(f"[LIVE] send_audio closed: {ws_err}")
                                        client_connected = False
                                        break
                            finally:
                                logger.info(f"[LIVE] send_audio exit, chunks={chunks}")
                        
                        async def receive_audio():
                            nonlocal client_connected
                            turns = 0
                            try:
                                async for response in session.receive():
                                    if not client_connected:
                                        break
                                        
                                    if response.server_content:
                                        sc = response.server_content
                                        if sc.model_turn and sc.model_turn.parts:
                                            for part in sc.model_turn.parts:
                                                if part.inline_data and part.inline_data.data:
                                                    try:
                                                        await asyncio.to_thread(ws.send, part.inline_data.data)
                                                    except Exception as ws_err:
                                                        logger.error(f"[LIVE] receive_audio ws.send failed: {ws_err}")
                                                        client_connected = False
                                                        return
                                        
                                        if sc.turn_complete:
                                            turns += 1
                                            
                                        if getattr(sc, 'interrupted', False):
                                            logger.info(f"[LIVE] model interrupted")
                            except Exception as e:
                                logger.error(f"[LIVE] receive_audio error: {e}")
                            finally:
                                logger.info(f"[LIVE] receive_audio exit, turns={turns}")

                        send_task = asyncio.create_task(send_audio())
                        receive_task = asyncio.create_task(receive_audio())
                        
                        done, pending = await asyncio.wait(
                            [send_task, receive_task],
                            return_when=asyncio.FIRST_COMPLETED
                        )
                        
                        # Cleanup pending task
                        for task in pending:
                            task.cancel()
                            try:
                                await task
                            except asyncio.CancelledError:
                                pass
                                
                        # Check if user quit
                        if send_task in done:
                            client_connected = False
                            
                        if not client_connected:
                            logger.info("[LIVE] Client disconnected completely, ending loop.")
                            break
                        else:
                            # User is still connected, but Gemini dropped the connection! 
                            # Continue the while loop to instantly reconnect to Gemini.
                            logger.info("[LIVE] Gemini session ended unexpectedly, AUTO-RECONNECTING...")
                            
                except Exception as e:
                    logger.error(f"[LIVE] Gemini connection error, retrying in 1s: {e}")
                    if client_connected:
                        await asyncio.sleep(1)
                    else:
                        break

        asyncio.run(run_live_session())
        
    except Exception as e:
        logger.error(f"[LIVE] WebSocket route error: {e}")
    finally:
        logger.info(f"[LIVE] WebSocket finally closed for bot {bot_id}")
