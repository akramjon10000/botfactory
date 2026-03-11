import requests
from bs4 import BeautifulSoup
import uuid
import random

def test_qa_and_analytics():
    print("Starting deep end-to-end integration test for Q&A Editor and Analytics Dashboard...")
    session = requests.Session()
    base_url = 'http://localhost:5000'
    unique_id = str(uuid.uuid4())[:8]
    test_user = f"u_{unique_id}"
    test_email = f"e_{unique_id}@test.com"
    test_pass = "Password123!"
    # Randomize phone to avoid "Phone already exists" errors
    random_phone = f"+9989{random.randint(0,9)}{random.randint(1000000, 9999999)}"

    # 1. Register a new user
    print(f"Registering new test user: {test_user} with phone: {random_phone}...")
    reg_page = session.get(f'{base_url}/auth/register')
    soup = BeautifulSoup(reg_page.text, 'html.parser')
    csrf_token = soup.find('input', {'name': 'csrf_token'})['value']
    
    reg_data = {
        'username': test_user,
        'email': test_email,
        'phone_number': random_phone,
        'password': test_pass,
        'confirm_password': test_pass,
        'csrf_token': csrf_token
    }
    reg_res = session.post(f'{base_url}/auth/register', data=reg_data)
    print(f"Registration Post -> Status: {reg_res.status_code}, Final URL: {reg_res.url}")
    
    if '/auth/register' in reg_res.url:
        print("REGISTRATION FAILED! Flash messages:")
        soup_reg = BeautifulSoup(reg_res.text, 'html.parser')
        for msg in soup_reg.select('.alert'):
            print(f" - {msg.get_text(strip=True)}")
        return False

    # 2. Perform Login
    print("Logging in...")
    login_page = session.get(f'{base_url}/auth/login')
    soup = BeautifulSoup(login_page.text, 'html.parser')
    csrf_token = soup.find('input', {'name': 'csrf_token'})['value']
    
    login_data = {
        'username': test_user,
        'password': test_pass,
        'csrf_token': csrf_token
    }
    login_res = session.post(f'{base_url}/auth/login', data=login_data)
    print(f"Login Post -> Status: {login_res.status_code}, Final URL: {login_res.url}")
    
    if '/auth/login' in login_res.url:
        print("LOGIN FAILED! Flash messages:")
        soup_login = BeautifulSoup(login_res.text, 'html.parser')
        for msg in soup_login.select('.alert'):
            print(f" - {msg.get_text(strip=True)}")
        return False

    # 3. Create a Bot
    print("Creating a new bot...")
    create_page = session.get(f'{base_url}/bot/create')
    soup = BeautifulSoup(create_page.text, 'html.parser')
    csrf_token = soup.find('input', {'name': 'csrf_token'})['value']
    
    bot_data = {
        'name': f'Bot_{unique_id}',
        'platform': 'Telegram',
        'telegram_token': f'123456:{unique_id}',
        'csrf_token': csrf_token
    }
    create_res = session.post(f'{base_url}/bot/create', data=bot_data)
    print(f"Bot Creation Post -> Status: {create_res.status_code}, Final URL: {create_res.url}")
    
    # 4. Access Dashboard
    print("Fetching dashboard...")
    dash_page = session.get(f'{base_url}/dashboard')
    soup = BeautifulSoup(dash_page.text, 'html.parser')
    
    if f'Bot_{unique_id}' in dash_page.text:
        print(f"SUCCESS! Bot_{unique_id} found on dashboard.")
    else:
        print(f"FAILED! Bot_{unique_id} NOT found on dashboard.")
        return False
    
    # Find bot edit link
    bot_id = None
    for a in soup.find_all('a', href=True):
        if '/edit' in a['href'] and '/bot/' in a['href']:
            bot_id = a['href'].split('/')[2]
            break
            
    if not bot_id:
        print("Failed to find any bot edit ID.")
        return False
    print(f"Found Bot ID: {bot_id}")
    
    # 5. Access Bot Edit Page
    print(f"Fetching bot edit page (/bot/{bot_id}/edit)...")
    edit_page = session.get(f'{base_url}/bot/{bot_id}/edit')
    soup = BeautifulSoup(edit_page.text, 'html.parser')
    csrf_token = soup.find('input', {'name': 'csrf_token'})['value']
    
    # 6. Add a new Q&A Pair
    print("Adding a new Q&A pair...")
    post_url = f'{base_url}/bot/{bot_id}/knowledge/qa'
    test_q = f"Question {unique_id}?"
    test_a = f"Answer {unique_id}!"
    qa_data = {
        'csrf_token': csrf_token,
        'source_name': test_q,
        'content': test_a
    }
    qa_res = session.post(post_url, data=qa_data)
    print(f"QA Add -> Status: {qa_res.status_code}, Final URL: {qa_res.url}")
    
    # Verify
    edit_page_refresh = session.get(f'{base_url}/bot/{bot_id}/edit')
    if test_q in edit_page_refresh.text:
        print("SUCCESS! Q&A Pair saved and rendered.")
    else:
        print("FAILED! Q&A Pair not found in edit page.")
        return False

    # 7. Check Analytics API (requires Admin)
    print("Checking Analytics API (logging in as admin)...")
    admin_session = requests.Session()
    # In a real app, we'd get ADMIN_EMAIL from .env, but for test we can hardcode or read
    # Let's assume the test environment has access to the same .env or we use a known test admin
    admin_email = "admin@botfactory.uz"
    admin_pass = "Hisobot201415"
    
    login_page = admin_session.get(f'{base_url}/auth/login')
    soup = BeautifulSoup(login_page.text, 'html.parser')
    csrf_token = soup.find('input', {'name': 'csrf_token'})['value']
    
    admin_login_res = admin_session.post(f'{base_url}/auth/login', data={
        'username': admin_email,
        'password': admin_pass,
        'csrf_token': csrf_token
    })
    
    if '/dashboard' in admin_login_res.url:
        print("Admin login successful.")
        stats_res = admin_session.get(f'{base_url}/api/admin/stats')
        if stats_res.status_code == 200:
            data = stats_res.json()
            if 'status' in data and data['status'] == 'success':
                print("SUCCESS! Analytics API functional and returned data.")
                return True
    else:
        print("Admin login failed for analytics check.")
    
    return False

if __name__ == "__main__":
    success = test_qa_and_analytics()
    if not success:
        exit(1)
    print("Deep Test Suite Passed Successfully!")
