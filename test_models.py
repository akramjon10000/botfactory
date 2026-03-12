import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
api_key = os.getenv('GOOGLE_API_KEY') or os.getenv('GOOGLE_API_KEY2')
if not api_key:
    print("API Key not found")
else:
    genai.configure(api_key=api_key)
    try:
        models = genai.list_models()
        for m in models:
            if 'audio' in m.name or '2.5' in m.name:
                print(m.name)
    except Exception as e:
        print(f"Error: {e}")
