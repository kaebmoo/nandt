# flask_app/check_gmail.py
# สคริปต์ทดสอบการล็อกอิน Gmail SMTP ด้วยมือ (manual script — ไม่ใช่ unit test)
# รันเอง: python flask_app/check_gmail.py
# (เดิมชื่อ test_gmail.py -> pytest จะ collect แล้วยิง SMTP login จริงตอน import)
import os

from dotenv import load_dotenv


def main():
    load_dotenv()
    import smtplib

    server, port = 'smtp.gmail.com', 587
    username = os.environ.get('MAIL_USERNAME')
    password = os.environ.get('MAIL_PASSWORD')
    print(f"Testing Gmail:\nUsername: {username}")
    try:
        with smtplib.SMTP(server, port) as smtp:
            smtp.starttls()
            smtp.login(username, password)
            print("✅ Gmail login successful!")
    except Exception as e:  # noqa: BLE001
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    main()
