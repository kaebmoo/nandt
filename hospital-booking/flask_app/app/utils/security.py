# flask_app/app/utils/security.py
import hashlib
import time
import os

def generate_booking_token():
    """สร้าง token ที่มีอายุ"""
    timestamp = str(int(time.time()))
    secret = os.environ.get('SECRET_KEY', 'your-secret-key')
    # เพิ่ม random string เพื่อให้ token ไม่ซ้ำ
    import random
    rand = str(random.randint(1000, 9999))
    token_string = f"{timestamp}:{rand}:{secret}"
    hash_value = hashlib.sha256(token_string.encode()).hexdigest()[:16]
    return f"{timestamp}:{rand}:{hash_value}"

def verify_booking_token(token, min_age=5, max_age=3600):
    """
    ตรวจสอบ token
    min_age: อย่างน้อยต้องรอ 5 วินาทีก่อน submit (ป้องกัน bot)
    max_age: token หมดอายุใน 1 ชั่วโมง
    """
    try:
        parts = token.split(':')
        if len(parts) != 3:
            return False, "Invalid token format"
            
        timestamp, rand, hash_value = parts
        timestamp = int(timestamp)
        
        # ตรวจสอบอายุ
        age = time.time() - timestamp
        
        if age < min_age:
            return False, f"กรุณารอสักครู่ (กรอกเร็วเกินไป)"
        
        if age > max_age:
            return False, "หน้านี้หมดอายุ กรุณาเริ่มใหม่"
        
        # ตรวจสอบ hash
        secret = os.environ.get('SECRET_KEY', 'your-secret-key')
        token_string = f"{timestamp}:{rand}:{secret}"
        expected = hashlib.sha256(token_string.encode()).hexdigest()[:16]
        
        if hash_value != expected:
            return False, "Token ไม่ถูกต้อง"
            
        return True, "OK"
        
    except Exception as e:
        return False, f"Token error: {str(e)}"