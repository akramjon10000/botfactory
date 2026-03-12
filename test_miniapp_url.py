import requests
try:
    url = "https://chatbotfactory.onrender.com/static/miniapp/index.html"
    r = requests.get(url)
    print(f"Status Code: {r.status_code}")
    print(f"Headers: {r.headers}")
    print(f"Snippet: {r.text[:200]}")
except Exception as e:
    print(f"Error: {e}")
