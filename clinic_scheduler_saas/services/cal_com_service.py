# services/cal_com_service.py
import httpx

BASE_URL = "https://api.cal.com/v1"

async def get_event_types(api_key: str):
    params = {"apiKey": api_key}
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/event-types", params=params)
        if response.status_code == 200:
            return True, response.json().get("event_types", [])
        return False, response.json()

async def create_booking(api_key: str, booking_data: dict):
    params = {"apiKey": api_key}
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{BASE_URL}/bookings", params=params, json=booking_data)
        if response.status_code in [200, 201]:
            return True, response.json().get("booking", {})
        return False, response.json()

async def get_bookings(api_key: str):
    params = {"apiKey": api_key}
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{BASE_URL}/bookings", params=params)
        if response.status_code == 200:
            return True, response.json().get("bookings", [])
        return False, response.json()