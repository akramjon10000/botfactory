from google import genai
import os

api_key = os.getenv('GOOGLE_API_KEY') or "AIzaSyClNL-5W3n2pyhXs8PAHGOhR-ZfVhTOTW8"
client = genai.Client(api_key=api_key)

print(hasattr(client, 'live'))
print(hasattr(client.aio, 'live'))
