import json
import urllib.request
from urllib.error import URLError

try:
    req = urllib.request.Request('http://127.0.0.1:9222/json')
    with urllib.request.urlopen(req) as response:
        pages = json.loads(response.read().decode('utf-8'))
        
    for page in pages:
        if 'title' in page and 'Render' in page['title']:
            print(f"Found Render page: {page['url']}")
            # We would use a CDP driver here, but I can ask the user instead
            break
except URLError as e:
    print(f"Debugger not active or reachable: {e}")
