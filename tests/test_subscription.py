import requests
from bs4 import BeautifulSoup
import os

def test_subscription_page():
    print("Starting automated subscription page test...")
    session = requests.Session()
    
    # 1. Access Login Page to get CSRF Token
    print("Fetching login page...")
    login_page = session.get('http://localhost:5000/auth/login')
    soup = BeautifulSoup(login_page.text, 'html.parser')
    csrf_input = soup.find('input', {'name': 'csrf_token'})
    if not csrf_input:
        print("Failed to find csrf token. Status:", login_page.status_code)
        return
    csrf_token = csrf_input['value']
    
    # 2. Perform Login
    print("Logging in...")
    login_data = {
        'username': 'admin',
        'password': 'Admin123456',
        'csrf_token': csrf_token
    }
    session.post('http://localhost:5000/auth/login', data=login_data)
    
    # 3. Access Subscription Page
    print("Fetching subscription page...")
    sub_page = session.get('http://localhost:5000/subscription')
    
    print(f"Post status code: {sub_page.status_code}")
    if sub_page.status_code == 200:
        print("SUCCESS! The subscription page is accessible.")
        # Check for core elements like payment methods or plans
        if 'Ta' in sub_page.text or "To'lov" in sub_page.text or "Tarif" in sub_page.text:
            print("Page seems to contain subscription plans or payment UI.")
    else:
        print("FAILED to access the subscription page.")

if __name__ == "__main__":
    test_subscription_page()
