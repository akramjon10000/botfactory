"""Test gemini-3.1-flash-live-preview - official SDK method"""
import asyncio
from google import genai
from google.genai import types

API_KEY = "AIzaSyClNL-5W3n2pyhXs8PAHGOhR-ZfVhTOTW8"

async def test():
    client = genai.Client(api_key=API_KEY)
    config = {"response_modalities": ["AUDIO"]}
    
    try:
        async with client.aio.live.connect(
            model="gemini-3.1-flash-live-preview",
            config=config,
        ) as session:
            print("Connected!")
            
            # Official method from docs: send_realtime_input
            await session.send_realtime_input(text="Salom! Sen kimsan? 1 gap bilan javob ber.")
            
            total_audio = 0
            transcription = ""
            async for response in session.receive():
                if response.server_content:
                    sc = response.server_content
                    if sc.model_turn:
                        for part in sc.model_turn.parts:
                            if part.inline_data:
                                total_audio += len(part.inline_data.data)
                            if part.text:
                                print(f"Text: {part.text}")
                    if hasattr(sc, 'output_transcription') and sc.output_transcription:
                        transcription += sc.output_transcription.text
                        print(f"Transcription: {sc.output_transcription.text}")
                    if sc.turn_complete:
                        break
            
            print(f"\nRESULT: Audio={total_audio} bytes, Transcription='{transcription}'")
            if total_audio > 0:
                print("SUCCESS! Model is working!")
    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")

asyncio.run(test())
