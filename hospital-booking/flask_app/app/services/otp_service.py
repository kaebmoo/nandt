# flask_app/app/services/otp_service.py

import base64
import hashlib
import pyotp
import time
import os
from .redis_connection import redis_manager 

class OTPService:
    def __init__(self):
        self.redis = redis_manager.connection
        self.MAX_ATTEMPTS = 3
    
    def generate_otp(self, identifier, expiration=300):  # 5 minutes default
        """Generate OTP using pyotp"""
        # Create unique key for identifier (email/phone)
        hex_key = self._get_hex_key_for_identifier(identifier)
        byte_key = bytes.fromhex(hex_key)
        base32_key = base64.b32encode(byte_key).decode('utf-8')

        # Store the base32 key and reset attempts in Redis
        # Use a pipeline for atomic operations
        pipe = self.redis.pipeline()
        pipe.set(f"otp:key:{identifier}", base32_key, ex=expiration)
        pipe.set(f"otp:attempts:{identifier}", 0, ex=expiration)
        pipe.execute()

        # Create TOTP object with 6 digits
        totp = pyotp.TOTP(base32_key, digits=6, interval=expiration)
        otp = totp.now()
        
        return otp
    
    def verify_otp(self, identifier, otp_input):
        """Verify OTP with attempt limiting"""
        base32_key = self.redis.get(f"otp:key:{identifier}")
        attempts_raw = self.redis.get(f"otp:attempts:{identifier}")

        if not base32_key or attempts_raw is None:
            return False, "OTP หมดอายุหรือไม่พบ"
        
        attempts = int(attempts_raw)

        # Check attempts
        if attempts >= self.MAX_ATTEMPTS:
            # Clean up immediately on too many attempts
            self.redis.delete(f"otp:key:{identifier}", f"otp:attempts:{identifier}")
            return False, "พยายามมากเกินไป กรุณาเริ่มใหม่"
        
        # Create TOTP object from stored key
        # The interval here is just for object creation, verification depends on `valid_window`
        totp = pyotp.TOTP(base32_key.decode('utf-8'), digits=6, interval=300)
        
        # Verify OTP
        # valid_window=1 allows for a bit of clock skew between generation and verification
        if totp.verify(otp_input, valid_window=1):
            # Clean up on success
            self.redis.delete(f"otp:key:{identifier}", f"otp:attempts:{identifier}")
            return True, "สำเร็จ"
        else:
            # Increment attempts on failure
            new_attempts = self.redis.incr(f"otp:attempts:{identifier}")
            remaining = self.MAX_ATTEMPTS - new_attempts
            return False, f"OTP ไม่ถูกต้อง (เหลือ {remaining} ครั้ง)"
    
    def get_time_remaining(self, identifier):
        """Get remaining time for OTP"""
        # Use Redis TTL (Time To Live) command
        ttl = self.redis.ttl(f"otp:key:{identifier}")
        return ttl if ttl > 0 else 0
    
    def _get_hex_key_for_identifier(self, identifier):
        """Generate unique key using SHA-256"""
        # Add app secret for extra security
        # This now safely uses os.environ, which works everywhere
        secret = os.environ.get('SECRET_KEY', 'default-secret')
        combined = f"{identifier}:{secret}"
        hash_object = hashlib.sha256(combined.encode())
        return hash_object.hexdigest()

# Singleton instance
otp_service = OTPService()