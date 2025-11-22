"""
API Client for Hospital Booking FastAPI
Provides async methods to interact with the booking system
"""
import httpx
from typing import List, Dict, Optional, Any
from datetime import date
import logging

logger = logging.getLogger(__name__)


class APIException(Exception):
    """Custom exception for API errors"""
    pass


class HospitalBookingAPI:
    """
    API Client for Hospital Booking System
    Wraps FastAPI endpoints with async methods
    """

    def __init__(self, base_url: str, subdomain: str):
        """
        Initialize API client

        Args:
            base_url: Base URL of FastAPI server (e.g., http://localhost:8000)
            subdomain: Hospital subdomain (e.g., humnoi)
        """
        self.base_url = base_url.rstrip('/')
        self.subdomain = subdomain
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close the HTTP client"""
        await self.client.aclose()

    def _get_endpoint(self, path: str) -> str:
        """
        Construct full endpoint URL

        Args:
            path: API path (e.g., /event-types)

        Returns:
            Full URL with subdomain
        """
        # Remove leading slash if present
        path = path.lstrip('/')
        return f"{self.base_url}/api/v1/tenants/{self.subdomain}/{path}"

    async def _request(
        self,
        method: str,
        endpoint: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make HTTP request and handle errors

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: Full endpoint URL
            **kwargs: Additional arguments for httpx request

        Returns:
            JSON response as dict

        Raises:
            APIException: If request fails
        """
        try:
            response = await self.client.request(method, endpoint, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
            raise APIException(f"API request failed: {e.response.status_code}")
        except httpx.RequestError as e:
            logger.error(f"Request error: {str(e)}")
            raise APIException(f"Failed to connect to API: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            raise APIException(f"Unexpected error: {str(e)}")

    # ==================== Event Types ====================

    async def get_event_types(self) -> List[Dict[str, Any]]:
        """
        Get all available event types/services

        Returns:
            List of event types with details
        """
        endpoint = self._get_endpoint("event-types")
        return await self._request("GET", endpoint)

    async def get_event_type(self, event_type_id: int) -> Dict[str, Any]:
        """
        Get single event type details

        Args:
            event_type_id: Event type ID

        Returns:
            Event type details
        """
        endpoint = self._get_endpoint(f"event-types/{event_type_id}")
        return await self._request("GET", endpoint)

    # ==================== Availability ====================

    async def get_availability(
        self,
        event_type_id: int,
        date_str: str
    ) -> List[Dict[str, Any]]:
        """
        Get available time slots for a specific event type and date

        Args:
            event_type_id: Event type ID
            date_str: Date in YYYY-MM-DD format

        Returns:
            List of available time slots with provider info
        """
        endpoint = self._get_endpoint(f"booking/availability/{event_type_id}")
        params = {"date": date_str}
        return await self._request("GET", endpoint, params=params)

    # ==================== Booking ====================

    async def create_booking(
        self,
        event_type_id: int,
        date_str: str,
        time_str: str,
        guest_name: str,
        guest_phone: Optional[str] = None,
        guest_email: Optional[str] = None,
        provider_id: Optional[int] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new appointment booking

        Args:
            event_type_id: Event type ID
            date_str: Date in YYYY-MM-DD format
            time_str: Time in HH:MM format
            guest_name: Guest name
            guest_phone: Guest phone number (optional)
            guest_email: Guest email (optional)
            provider_id: Preferred provider ID (optional)
            notes: Additional notes (optional)

        Returns:
            Booking confirmation with reference number

        Note:
            Either guest_phone or guest_email must be provided
        """
        endpoint = self._get_endpoint("booking/create")

        data = {
            "event_type_id": event_type_id,
            "date": date_str,
            "time": time_str,
            "guest_name": guest_name,
        }

        if guest_phone:
            data["guest_phone"] = guest_phone
        if guest_email:
            data["guest_email"] = guest_email
        if provider_id:
            data["provider_id"] = provider_id
        if notes:
            data["notes"] = notes

        return await self._request("POST", endpoint, json=data)

    async def search_booking(
        self,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        booking_reference: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search appointments by phone, email, or reference

        Args:
            phone: Phone number
            email: Email address
            booking_reference: Booking reference number

        Returns:
            List of matching appointments

        Note:
            At least one search parameter must be provided
        """
        endpoint = self._get_endpoint("booking/search")

        data = {}
        if phone:
            data["phone"] = phone
        if email:
            data["email"] = email
        if booking_reference:
            data["booking_reference"] = booking_reference

        response = await self._request("POST", endpoint, json=data)
        return response.get("appointments", [])

    async def get_booking(self, booking_reference: str) -> Dict[str, Any]:
        """
        Get booking details by reference number

        Args:
            booking_reference: Booking reference number

        Returns:
            Booking details
        """
        endpoint = self._get_endpoint(f"booking/{booking_reference}")
        return await self._request("GET", endpoint)

    async def cancel_booking(
        self,
        booking_reference: str,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel an existing booking

        Args:
            booking_reference: Booking reference number
            reason: Cancellation reason (optional)

        Returns:
            Cancellation confirmation
        """
        endpoint = self._get_endpoint("booking/cancel")

        data = {"booking_reference": booking_reference}
        if reason:
            data["reason"] = reason

        return await self._request("POST", endpoint, json=data)

    async def reschedule_booking(
        self,
        booking_reference: str,
        new_date: str,
        new_time: str,
        provider_id: Optional[int] = None,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Reschedule an existing booking

        Args:
            booking_reference: Booking reference number
            new_date: New date in YYYY-MM-DD format
            new_time: New time in HH:MM format
            provider_id: New provider ID (optional)
            reason: Reschedule reason (optional)

        Returns:
            Updated booking confirmation
        """
        endpoint = self._get_endpoint("booking/reschedule")

        data = {
            "booking_reference": booking_reference,
            "new_date": new_date,
            "new_time": new_time,
        }
        if provider_id:
            data["provider_id"] = provider_id
        if reason:
            data["reason"] = reason

        return await self._request("POST", endpoint, json=data)

    # ==================== Helper Methods ====================

    async def get_active_event_types(self) -> List[Dict[str, Any]]:
        """
        Get only active event types

        Returns:
            List of active event types
        """
        all_types = await self.get_event_types()
        return [et for et in all_types if et.get("is_active", True)]
