import cloudinary
import cloudinary.uploader
import os
from dotenv import load_dotenv

load_dotenv()

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

try:
    # Use one of the existing test images in the workspace
    test_image = r'C:\Users\user\.gemini\antigravity\brain\018164f2-9797-4d97-a480-5076383a82b9\bot_image_url_test_1772255668065.png'
    
    print(f"Uploading {test_image} to Cloudinary...")
    result = cloudinary.uploader.upload(
        test_image,
        folder='botfactory/test'
    )
    print('SUCCESS: ' + result.get('secure_url'))
except Exception as e:
    print('ERROR: ' + str(e))
