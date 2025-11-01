# flask_app/test_gmail.py
import os
from dotenv import load_dotenv
load_dotenv()

import smtplib

server = 'smtp.gmail.com'
port = 587
username = os.environ.get('MAIL_USERNAME')
password = os.environ.get('MAIL_PASSWORD')

print(f"Testing Gmail:")
print(f"Username: {username}")

try:
    with smtplib.SMTP(server, port) as smtp:
        smtp.starttls()
        smtp.login(username, password)
        print("✅ Gmail login successful!")
except Exception as e:
    print(f"❌ Error: {e}")