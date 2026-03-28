import os
import asyncio
import logging
from flask import request
from extensions import sock
from google import genai

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
            
            try:
                # Disable SSL verification issues if any, or just connect
                async with client.aio.live.connect(model="gemini-3.1-flash-live-preview", config=config) as session:
                    logger.info(f"Connected to Gemini Live API for bot {bot_id}")
                    
                    # Task 1: Receive from Frontend and send to Gemini
                    async def ws_to_gemini():
                        try:
                            while True:
                                # Blocking receive executed in a thread
                                data = await asyncio.to_thread(ws.receive)
                                if data is None:
                                    break
                                
                                # Ignore text messages for now (like initial handshakes)
                                if isinstance(data, str):
                                    if data == "END_OF_TURN":
                                        await session.send(end_of_turn=True)
                                    continue
                                
                                if isinstance(data, bytes):
                                    await session.send(input={"data": data, "mime_type": "audio/pcm;rate=16000"})
                        except Exception as e:
                            logger.info(f"WebSocket receive error or closed: {e}")
                    
                    # Task 2: Receive from Gemini and send to Frontend
                    async def gemini_to_ws():
                        try:
                            async for response in session.receive():
                                server_content = response.server_content
                                if server_content and server_content.model_turn:
                                    for part in server_content.model_turn.parts:
                                        # Check if it has audio data
                                        if hasattr(part, 'inline_data') and part.inline_data and part.inline_data.data: # type: ignore
                                            # Send binary audio chunk to frontend
                                            await asyncio.to_thread(ws.send, part.inline_data.data) # type: ignore
                        except Exception as e:
                            logger.error(f"Gemini receive error: {e}")

                    # Run both tasks concurrently
                    await asyncio.gather(ws_to_gemini(), gemini_to_ws())

            except Exception as e:
                logger.error(f"Gemini Live session error: {e}")
                # Inform frontend of closure
                try:
                    await asyncio.to_thread(ws.send, "Error: Connection failed")
                except:
                    pass

        # Execute the asyncio event loop
        asyncio.run(run_live_session())
        
    except Exception as e:
        logger.error(f"WebSocket route error: {e}")
    finally:
        logger.info(f"WebSocket closed for bot {bot_id}")
