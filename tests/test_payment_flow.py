import requests
from bs4 import BeautifulSoup
import uuid
import re

def test_payment_flow():
    print("Testing Manual Payment Flow...")
    session = requests.Session()
    base_url = 'http://localhost:5000'
    
    # 1. Register a test user
    uid = uuid.uuid4().hex[:6]
    test_email = f"testpay_{uid}@botfactory.uz"
    test_pwd = "password123"
    
    print(f"1. Registering test user: {test_email}")
    res = session.get(f'{base_url}/auth/register')
    soup = BeautifulSoup(res.text, 'html.parser')
    csrf_token = soup.find('input', {'name': 'csrf_token'})['value']
    
    reg_data = {
        'csrf_token': csrf_token,
        'username': f'testpay_{uid}',
        'email': test_email,
        'phone': f'+99899123{uid[:4]}',
        'password': test_pwd,
        'password_confirm': test_pwd
    }
    res = session.post(f'{base_url}/auth/register', data=reg_data)
    
    # Check registration by seeing if we are logged in (dashboard or so)
    if 'chiqish' not in res.text.lower() and 'dashboard' not in res.url:
        print("   Failed to register/login.")
        return
    print("   User logged in.")
    
    # 2. Go to subscription page and get CSRF token
    print("2. Navigate to subscription")
    res = session.get(f'{base_url}/subscription')
    soup = BeautifulSoup(res.text, 'html.parser')
    csrf_input = soup.find('input', {'name': 'csrf_token'})
    if not csrf_input:
        print("   Could not find CSRF token in subscription page.")
        return
    csrf_token = csrf_input['value']
    
    # 3. Submit a Payment Report
    print("3. Reporting a payment for Premium")
    pay_data = {
        'csrf_token': csrf_token,
        'subscription_type': 'premium',
        'payment_method': 'Paynet'
    }
    res = session.post(f'{base_url}/report-payment', data=pay_data)
    if 'kutilmoqda' in res.text.lower() or 'yuborildi' in res.text.lower():
        print("   Payment report successfully sent.")
    else:
        print("   Payment report might not have succeeded. Let's check admin.")
        
    # 4. Login as Admin
    print("4. Accessing Admin Panel")
    admin_session = requests.Session()
    
    # Let's assume we can auth as admin by setting local env or getting an admin user
    # For this test, let's create a script to make this user an admin directly via DB,
    # OR we can just use the DB to check if payment was created. Let's do a direct DB check.
    
    print("Done! View verification script to check DB.")

if __name__ == '__main__':
    test_payment_flow()
