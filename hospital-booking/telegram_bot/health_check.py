#!/usr/bin/env python
"""
Health Check Script for Telegram Bot
Verifies all dependencies before starting the bot

Usage:
    python health_check.py
"""
import sys
import asyncio
from typing import Tuple, List


def check_env_file() -> Tuple[bool, str]:
    """Check if .env file exists and has required variables"""
    import os
    from pathlib import Path

    env_path = Path(".env")

    if not env_path.exists():
        return False, ".env file not found. Copy .env.example and configure it."

    # Check for required variables
    required_vars = [
        "TELEGRAM_BOT_TOKEN",
        "FASTAPI_BASE_URL",
        "DEFAULT_SUBDOMAIN",
        "REDIS_URL"
    ]

    from dotenv import load_dotenv
    load_dotenv()

    missing = []
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)

    if missing:
        return False, f"Missing environment variables: {', '.join(missing)}"

    return True, "Environment variables configured ✓"


def check_redis_connection() -> Tuple[bool, str]:
    """Check Redis connectivity"""
    try:
        import redis
        from config import Config

        client = redis.from_url(Config.REDIS_URL, decode_responses=True, socket_timeout=5)
        client.ping()
        return True, f"Redis connected at {Config.REDIS_URL} ✓"

    except redis.ConnectionError:
        return False, f"Cannot connect to Redis at {Config.REDIS_URL}"
    except Exception as e:
        return False, f"Redis error: {str(e)}"


async def check_fastapi_connection() -> Tuple[bool, str]:
    """Check FastAPI backend connectivity"""
    try:
        from services.api_client import HospitalBookingAPI, APIException
        from config import Config

        api = HospitalBookingAPI(
            base_url=Config.FASTAPI_BASE_URL,
            subdomain=Config.DEFAULT_SUBDOMAIN
        )

        try:
            event_types = await api.get_event_types()
            count = len(event_types)
            return True, f"FastAPI connected ({count} event types found) ✓"
        except APIException as e:
            return False, f"FastAPI error: {str(e)}"
        finally:
            await api.close()

    except Exception as e:
        return False, f"Unexpected error: {str(e)}"


def check_telegram_token() -> Tuple[bool, str]:
    """Verify Telegram bot token format"""
    import os
    from config import Config

    token = Config.TELEGRAM_BOT_TOKEN

    if not token:
        return False, "Telegram bot token not configured"

    # Basic token format check (should be like 123456:ABC-DEF...)
    if ":" not in token or len(token) < 20:
        return False, "Telegram bot token format looks invalid"

    return True, "Telegram bot token configured ✓"


def check_python_version() -> Tuple[bool, str]:
    """Check Python version"""
    if sys.version_info < (3, 8):
        return False, f"Python 3.8+ required, found {sys.version_info.major}.{sys.version_info.minor}"

    return True, f"Python {sys.version_info.major}.{sys.version_info.minor} ✓"


def check_dependencies() -> Tuple[bool, str]:
    """Check if required packages are installed"""
    required_packages = [
        "telegram",
        "httpx",
        "redis",
        "dotenv"
    ]

    missing = []
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)

    if missing:
        return False, f"Missing packages: {', '.join(missing)}. Run: pip install -r requirements.txt"

    return True, "All dependencies installed ✓"


async def run_health_check():
    """Run all health checks"""
    print("=" * 70)
    print("🏥 Hospital Booking Telegram Bot - Health Check")
    print("=" * 70)
    print()

    checks = [
        ("Python Version", check_python_version, False),
        ("Dependencies", check_dependencies, False),
        ("Environment File", check_env_file, False),
        ("Telegram Token", check_telegram_token, False),
        ("Redis Connection", check_redis_connection, False),
        ("FastAPI Backend", check_fastapi_connection, True),  # Async
    ]

    results: List[Tuple[str, bool, str]] = []
    all_passed = True

    for name, check_func, is_async in checks:
        print(f"🔍 Checking {name}...", end=" ", flush=True)

        try:
            if is_async:
                success, message = await check_func()
            else:
                success, message = check_func()

            results.append((name, success, message))

            if success:
                print(f"✅ {message}")
            else:
                print(f"❌ {message}")
                all_passed = False

        except Exception as e:
            error_msg = f"Check failed: {str(e)}"
            results.append((name, False, error_msg))
            print(f"❌ {error_msg}")
            all_passed = False

    # Summary
    print()
    print("=" * 70)
    print("📊 Health Check Summary")
    print("=" * 70)

    passed = sum(1 for _, success, _ in results if success)
    total = len(results)

    for name, success, message in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} - {name}")
        if not success:
            print(f"       └─> {message}")

    print()
    print(f"Passed: {passed}/{total}")

    if all_passed:
        print()
        print("🎉 All checks passed! Bot is ready to run.")
        print()
        print("To start the bot:")
        print("    python bot.py")
        print()
        return 0
    else:
        print()
        print("⚠️  Some checks failed. Please fix the issues above before running the bot.")
        print()
        return 1


def main():
    """Main entry point"""
    exit_code = asyncio.run(run_health_check())
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
