"""
Test Redis connectivity and user authentication service
Run with: pytest tests/test_redis.py -v
Or manually: python tests/test_redis.py
"""
import pytest
from services.auth import UserAuth
from config import Config
import redis


def test_redis_connection():
    """Test basic Redis connection"""
    try:
        client = redis.from_url(Config.REDIS_URL, decode_responses=True)
        # Test ping
        response = client.ping()
        assert response is True
        print("✅ Redis connection successful")
        return True
    except redis.ConnectionError as e:
        print(f"❌ Redis connection failed: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def test_user_registration():
    """Test user registration in Redis"""
    auth = UserAuth(Config.REDIS_URL)

    try:
        # Register a test user
        test_user = auth.register_user(
            telegram_id=123456789,
            name="Test User",
            phone="0812345678",
            username="test_user"
        )

        assert test_user is not None
        assert test_user['telegram_id'] == 123456789
        assert test_user['name'] == "Test User"
        assert test_user['is_registered'] is True

        print("✅ User registration successful")
        print(f"   User data: {test_user}")
        return True

    except Exception as e:
        print(f"❌ User registration failed: {e}")
        return False


def test_user_retrieval():
    """Test retrieving user from Redis"""
    auth = UserAuth(Config.REDIS_URL)

    try:
        # First register a user
        auth.register_user(
            telegram_id=987654321,
            name="Another Test User",
            phone="0898765432"
        )

        # Then retrieve
        user = auth.get_user(987654321)

        assert user is not None
        assert user['telegram_id'] == 987654321
        assert user['name'] == "Another Test User"

        print("✅ User retrieval successful")
        print(f"   Retrieved: {user}")
        return True

    except Exception as e:
        print(f"❌ User retrieval failed: {e}")
        return False


def test_is_registered():
    """Test checking if user is registered"""
    auth = UserAuth(Config.REDIS_URL)

    try:
        # Register a user
        telegram_id = 111222333
        auth.register_user(
            telegram_id=telegram_id,
            name="Registered User",
            phone="0811112222"
        )

        # Check if registered
        is_reg = auth.is_registered(telegram_id)
        assert is_reg is True

        # Check non-existent user
        is_reg_fake = auth.is_registered(999999999)
        assert is_reg_fake is False

        print("✅ is_registered check successful")
        return True

    except Exception as e:
        print(f"❌ is_registered check failed: {e}")
        return False


def test_session_management():
    """Test session data management"""
    auth = UserAuth(Config.REDIS_URL)

    try:
        telegram_id = 444555666
        session_data = {
            "booking": {
                "service_id": 1,
                "date": "2025-11-25",
                "time": "10:00"
            }
        }

        # Save session
        auth.save_session_data(telegram_id, session_data)

        # Retrieve session
        retrieved = auth.get_session_data(telegram_id)
        assert retrieved is not None
        assert retrieved['booking']['service_id'] == 1

        # Update session
        auth.update_session_data(telegram_id, status="confirmed")
        updated = auth.get_session_data(telegram_id)
        assert updated['status'] == "confirmed"

        # Clear session
        auth.clear_session_data(telegram_id)
        cleared = auth.get_session_data(telegram_id)
        assert cleared is None

        print("✅ Session management successful")
        return True

    except Exception as e:
        print(f"❌ Session management failed: {e}")
        return False


def test_user_update():
    """Test updating user data"""
    auth = UserAuth(Config.REDIS_URL)

    try:
        telegram_id = 777888999

        # Register initial user
        auth.register_user(
            telegram_id=telegram_id,
            name="Initial Name",
            phone="0877778888"
        )

        # Update user
        updated = auth.update_user(
            telegram_id=telegram_id,
            name="Updated Name",
            email="updated@example.com"
        )

        assert updated is not None
        assert updated['name'] == "Updated Name"
        assert updated['email'] == "updated@example.com"

        print("✅ User update successful")
        return True

    except Exception as e:
        print(f"❌ User update failed: {e}")
        return False


# Manual test runner
def run_all_tests():
    """Run all Redis tests manually"""
    print("=" * 60)
    print("🧪 Testing Redis Connection and Auth Service")
    print("=" * 60)

    tests = [
        ("Redis Connection", test_redis_connection),
        ("User Registration", test_user_registration),
        ("User Retrieval", test_user_retrieval),
        ("Is Registered Check", test_is_registered),
        ("Session Management", test_session_management),
        ("User Update", test_user_update),
    ]

    results = []
    for name, test_func in tests:
        print(f"\n{'─' * 60}")
        print(f"Testing: {name}")
        print(f"{'─' * 60}")

        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 60)
    print("📊 Test Summary")
    print("=" * 60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")

    print(f"\nPassed: {passed}/{total}")

    if passed == total:
        print("🎉 All tests passed!")
    else:
        print(f"⚠️  {total - passed} test(s) failed")

    print("=" * 60)


if __name__ == "__main__":
    run_all_tests()
