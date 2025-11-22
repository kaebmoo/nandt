"""
Authentication service for Telegram users
Manages user registration and session data
"""
import redis
import json
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class UserAuth:
    """
    User authentication and session management
    Uses Redis to store user data and session state
    """

    def __init__(self, redis_url: str):
        """
        Initialize auth service

        Args:
            redis_url: Redis connection URL
        """
        self.redis_client = redis.from_url(redis_url, decode_responses=True)

    def _user_key(self, telegram_id: int) -> str:
        """Generate Redis key for user data"""
        return f"telegram_user:{telegram_id}"

    def _session_key(self, telegram_id: int) -> str:
        """Generate Redis key for session data"""
        return f"session:{telegram_id}"

    # ==================== User Management ====================

    def register_user(
        self,
        telegram_id: int,
        name: str,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        username: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Register a new user

        Args:
            telegram_id: Telegram user ID
            name: User's full name
            phone: Phone number
            email: Email address
            username: Telegram username

        Returns:
            User data dictionary
        """
        user_data = {
            "telegram_id": telegram_id,
            "name": name,
            "phone": phone,
            "email": email,
            "username": username,
            "is_registered": True
        }

        key = self._user_key(telegram_id)
        self.redis_client.setex(
            key,
            86400 * 30,  # 30 days expiration
            json.dumps(user_data)
        )

        logger.info(f"User registered: {telegram_id} - {name}")
        return user_data

    def get_user(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """
        Get user data

        Args:
            telegram_id: Telegram user ID

        Returns:
            User data dictionary or None if not found
        """
        key = self._user_key(telegram_id)
        data = self.redis_client.get(key)

        if data:
            return json.loads(data)
        return None

    def is_registered(self, telegram_id: int) -> bool:
        """
        Check if user is registered

        Args:
            telegram_id: Telegram user ID

        Returns:
            True if user is registered
        """
        user = self.get_user(telegram_id)
        return user is not None and user.get("is_registered", False)

    def update_user(self, telegram_id: int, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Update user data

        Args:
            telegram_id: Telegram user ID
            **kwargs: Fields to update

        Returns:
            Updated user data or None if user not found
        """
        user = self.get_user(telegram_id)
        if not user:
            return None

        user.update(kwargs)

        key = self._user_key(telegram_id)
        self.redis_client.setex(
            key,
            86400 * 30,  # 30 days expiration
            json.dumps(user)
        )

        return user

    # ==================== Session Management ====================

    def save_session_data(
        self,
        telegram_id: int,
        data: Dict[str, Any],
        ttl: int = 3600
    ) -> None:
        """
        Save temporary session data

        Args:
            telegram_id: Telegram user ID
            data: Session data to save
            ttl: Time to live in seconds (default 1 hour)
        """
        key = self._session_key(telegram_id)
        self.redis_client.setex(key, ttl, json.dumps(data))

    def get_session_data(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        """
        Get session data

        Args:
            telegram_id: Telegram user ID

        Returns:
            Session data or None if not found
        """
        key = self._session_key(telegram_id)
        data = self.redis_client.get(key)

        if data:
            return json.loads(data)
        return None

    def clear_session_data(self, telegram_id: int) -> None:
        """
        Clear session data

        Args:
            telegram_id: Telegram user ID
        """
        key = self._session_key(telegram_id)
        self.redis_client.delete(key)

    def update_session_data(
        self,
        telegram_id: int,
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Update specific fields in session data

        Args:
            telegram_id: Telegram user ID
            **kwargs: Fields to update

        Returns:
            Updated session data or None if session doesn't exist
        """
        session = self.get_session_data(telegram_id)
        if session is None:
            session = {}

        session.update(kwargs)
        self.save_session_data(telegram_id, session)
        return session
