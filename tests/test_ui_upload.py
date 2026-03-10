import requests
from bs4 import BeautifulSoup
import os

def test_cloudinary_upload():
    print("Starting automated upload test...")
    session = requests.Session()
    
    # 1. Access Login Page to get CSRF Token
    login_page = session.get('http://localhost:5000/auth/login')
    soup = BeautifulSoup(login_page.text, 'html.parser')
    csrf_input = soup.find('input', {'name': 'csrf_token'})
    if not csrf_input:
        print("Failed to find csrf token. Status:", login_page.status_code)
        print("HTML Snippet:", login_page.text[:500])
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
    
    # 3. Access Bot Edit Page to get new CSRF Token
    print("Fetching bot edit page...")
    edit_page = session.get('http://localhost:5000/bot/5/edit')
    soup = BeautifulSoup(edit_page.text, 'html.parser')
    
    # Find the correct CSRF token for the product form
    # The page might have multiple forms, but they all use the same CSRF session token.
    csrf_token = soup.find('input', {'name': 'csrf_token'})['value']
    
    # 4. Submit the Product Form with an Image
    print("Submitting product with image upload...")
    test_image_path = r'C:\Users\user\.gemini\antigravity\brain\018164f2-9797-4d97-a480-5076383a82b9\bot_image_url_test_1772255668065.png'
    
    with open(test_image_path, 'rb') as f:
        files = {
            'product_image_file': ('test_image.png', f, 'image/png')
        }
        data = {
            'csrf_token': csrf_token,
            'product_name': 'Automated Test AI Product',
            'product_price': '99,000 UZS',
            'product_description': 'This product was added via automated test to prove the web interface UI and Cloudinary integration work perfectly!'
        }
        
        res = session.post('http://localhost:5000/bot/5/knowledge/product', data=data, files=files)
        
    print(f"Post status code: {res.status_code}")
    
    # 5. Verify the product is loaded in the dashboard HTML
    print("Verifying if the product appears in the knowledge base...")
    final_page = session.get('http://localhost:5000/bot/5/edit')
    
    if 'Automated Test AI Product' in final_page.text and 'res.cloudinary.com' in final_page.text:
        print("SUCCESS! The product was successfully uploaded and inserted into the UI with a Cloudinary link.")
        
        # Let's extract the actual inserted Cloudinary URL to show the user
        soup = BeautifulSoup(final_page.text, 'html.parser')
        image_tags = soup.find_all('img')
        for img in image_tags:
            src = img.get('src', '')
            if 'res.cloudinary.com' in src:
                print(f"Found Cloudinary URL in UI: {src}")
    else:
        print("FAILED to find the uploaded product in the UI HTML.")

if __name__ == "__main__":
    test_cloudinary_upload()
