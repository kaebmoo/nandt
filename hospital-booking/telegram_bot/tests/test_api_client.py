"""
Test API client connectivity and endpoints
Run with: pytest tests/test_api_client.py -v
Or manually: python tests/test_api_client.py
"""
import asyncio
import pytest
from services.api_client import HospitalBookingAPI, APIException
from config import Config


@pytest.mark.asyncio
async def test_api_connection():
    """Test basic API connection"""
    api = HospitalBookingAPI(
        base_url=Config.FASTAPI_BASE_URL,
        subdomain=Config.DEFAULT_SUBDOMAIN
    )

    try:
        # Test get event types (should work without auth)
        event_types = await api.get_event_types()
        assert isinstance(event_types, list)
        print(f"✅ API Connection OK - Found {len(event_types)} event types")
        return True
    except APIException as e:
        print(f"❌ API Connection Failed: {e}")
        return False
    finally:
        await api.close()


@pytest.mark.asyncio
async def test_get_event_types():
    """Test fetching event types"""
    api = HospitalBookingAPI(
        base_url=Config.FASTAPI_BASE_URL,
        subdomain=Config.DEFAULT_SUBDOMAIN
    )

    try:
        event_types = await api.get_event_types()
        assert isinstance(event_types, list)

        if event_types:
            print(f"\n📋 Event Types ({len(event_types)}):")
            for et in event_types[:5]:  # Show first 5
                print(f"  - {et.get('name')} (ID: {et.get('id')})")

        return True
    except APIException as e:
        print(f"❌ Failed to fetch event types: {e}")
        return False
    finally:
        await api.close()


@pytest.mark.asyncio
async def test_get_availability():
    """Test fetching availability"""
    api = HospitalBookingAPI(
        base_url=Config.FASTAPI_BASE_URL,
        subdomain=Config.DEFAULT_SUBDOMAIN
    )

    try:
        # First get an event type
        event_types = await api.get_event_types()
        if not event_types:
            print("⚠️ No event types found, skipping availability test")
            return True

        event_type_id = event_types[0]['id']
        test_date = "2025-11-25"  # Use a future date

        # Test get availability
        slots = await api.get_availability(event_type_id, test_date)
        print(f"\n🕐 Availability for {test_date}:")
        print(f"  Found {len(slots)} available slots")

        if slots:
            for slot in slots[:3]:  # Show first 3
                time = slot.get('time', slot.get('start_time', 'N/A'))
                provider = slot.get('provider_name', 'N/A')
                print(f"  - {time} ({provider})")

        return True
    except APIException as e:
        print(f"❌ Failed to fetch availability: {e}")
        return False
    finally:
        await api.close()


@pytest.mark.asyncio
async def test_search_booking():
    """Test searching bookings"""
    api = HospitalBookingAPI(
        base_url=Config.FASTAPI_BASE_URL,
        subdomain=Config.DEFAULT_SUBDOMAIN
    )

    try:
        # Search with a test phone number
        test_phone = "0812345678"
        bookings = await api.search_booking(phone=test_phone)

        print(f"\n🔍 Search results for {test_phone}:")
        print(f"  Found {len(bookings)} bookings")

        if bookings:
            for booking in bookings[:3]:  # Show first 3
                ref = booking.get('booking_reference', 'N/A')
                date = booking.get('date', 'N/A')
                print(f"  - {ref} on {date}")

        return True
    except APIException as e:
        print(f"❌ Failed to search bookings: {e}")
        return False
    finally:
        await api.close()


# Manual test runner
async def run_all_tests():
    """Run all API tests manually"""
    print("=" * 60)
    print("🧪 Testing FastAPI Endpoints")
    print("=" * 60)

    tests = [
        ("API Connection", test_api_connection),
        ("Get Event Types", test_get_event_types),
        ("Get Availability", test_get_availability),
        ("Search Booking", test_search_booking),
    ]

    results = []
    for name, test_func in tests:
        print(f"\n{'─' * 60}")
        print(f"Testing: {name}")
        print(f"{'─' * 60}")

        try:
            success = await test_func()
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
    print("=" * 60)


if __name__ == "__main__":
    # Run tests manually
    asyncio.run(run_all_tests())
