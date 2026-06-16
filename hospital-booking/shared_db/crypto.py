"""
Encryption helper สำหรับ token/secret ที่ต้องเข้ารหัสตอนเก็บ (encrypt at rest).

ใช้กับ column `*_enc` ทุกตัวใน messaging_config (LINE secret/token, Telegram token/webhook secret,
PWA VAPID private key).
อยู่ใน shared_db เพื่อให้ทั้ง Flask (5001) และ FastAPI import ได้โดยไม่ต้องลาก Flask app
เข้า FastAPI process (เดิมแผนเสนอ flask_app/app/utils/crypto.py — ย้ายมา shared_db เพราะ
ใช้ร่วมกันสองฝั่งและ shared_db เป็น layer กลางที่ทั้งสอง process import อยู่แล้ว)

เลือก Fernet (symmetric) + MultiFernet:
  - ง่าย, ปลอดภัยพอสำหรับ app-level secret
  - MultiFernet รองรับ key rotation ในตัว (encrypt ด้วย key หน้าสุด, decrypt ได้ทุก key ในลิสต์)

กฎ key management (สำคัญ — ทำผิด = tenant ทุกรายต้อง re-link ใหม่):
  - MESSAGING_ENCRYPTION_KEYS = base64 Fernet keys คั่นด้วย comma
    key ตัวแรก = key ปัจจุบัน (ใช้ encrypt), ที่เหลือไว้ decrypt ตอน rotate
  - เก็บใน env var / secrets manager เท่านั้น — ห้ามอยู่ใน repo/DB, ห้าม hardcode
  - process Flask และ FastAPI ต้องโหลด key ตัวเดียวกัน ไม่งั้น decrypt ข้าม process ไม่ได้
  - backup key ให้ดี — key หาย = decrypt token ทุก tenant ไม่ได้
  - rotation: ใส่ key ใหม่ "หน้าสุด" -> re-encrypt ทุกแถว -> ค่อยถอด key เก่าออก
  - ห้าม log ค่า plaintext ที่ไหนเลย
"""

import os

from cryptography.fernet import Fernet, MultiFernet

ENV_KEY = "MESSAGING_ENCRYPTION_KEYS"


def generate_key() -> str:
    """สร้าง Fernet key ใหม่ (รันครั้งเดียวตอน setup) — ผลลัพธ์เอาไปใส่ env MESSAGING_ENCRYPTION_KEYS"""
    return Fernet.generate_key().decode()


def is_configured() -> bool:
    """มี key ใน env ไหม (ใช้เช็คก่อนเปิดฟีเจอร์ messaging)"""
    return bool(os.environ.get(ENV_KEY, "").strip())


def _cipher() -> MultiFernet:
    raw = os.environ.get(ENV_KEY)
    if not raw or not raw.strip():
        raise RuntimeError(
            f"{ENV_KEY} ไม่ถูกตั้งใน environment — ต้องมี Fernet key อย่างน้อย 1 ตัว "
            f"(สร้างด้วย shared_db.crypto.generate_key())"
        )
    keys = [Fernet(k.strip().encode()) for k in raw.split(",") if k.strip()]
    if not keys:
        raise RuntimeError(f"{ENV_KEY} ว่างหลัง parse — ตรวจรูปแบบ key")
    return MultiFernet(keys)


def encrypt(plaintext: "str | None") -> "str | None":
    """เข้ารหัสด้วย key ปัจจุบัน (key หน้าสุดของ MESSAGING_ENCRYPTION_KEYS). None -> None"""
    if plaintext is None:
        return None
    return _cipher().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: "str | None") -> "str | None":
    """ถอดรหัส (รองรับทุก key ในลิสต์ — ใช้ตอน rotate). None -> None"""
    if ciphertext is None:
        return None
    return _cipher().decrypt(ciphertext.encode()).decode()
