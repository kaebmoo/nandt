"""
MCP Tools for Hospital Booking
Provides booking-related tools for AI agents
"""
import httpx
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)


class BookingTools:
    """Hospital booking tools for MCP"""

    def __init__(self, base_url: str, subdomain: str):
        """
        Initialize booking tools

        Args:
            base_url: FastAPI base URL
            subdomain: Hospital subdomain
        """
        self.base_url = base_url.rstrip('/')
        self.subdomain = subdomain
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

    def _get_endpoint(self, path: str) -> str:
        """Construct API endpoint URL"""
        path = path.lstrip('/')
        return f"{self.base_url}/api/v1/tenants/{self.subdomain}/{path}"

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request"""
        try:
            response = await self.client.request(method, endpoint, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error: {e.response.status_code} - {e.response.text}")
            raise Exception(f"API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Request error: {str(e)}")
            raise

    # ==================== MCP Tool: check_availability ====================

    async def check_availability(
        self,
        subdomain: str,
        event_type_id: int,
        date: str
    ) -> Dict[str, Any]:
        """
        Check available time slots for booking

        Args:
            subdomain: Hospital subdomain
            event_type_id: Service/event type ID
            date: Date in YYYY-MM-DD format

        Returns:
            Dict with available slots and metadata
        """
        try:
            endpoint = self._get_endpoint(f"booking/availability/{event_type_id}")
            params = {"date": date}
            slots = await self._request("GET", endpoint, params=params)

            return {
                "success": True,
                "date": date,
                "event_type_id": event_type_id,
                "available_slots": len(slots),
                "slots": slots
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to check availability: {str(e)}"
            }

    # ==================== MCP Tool: get_event_types ====================

    async def get_event_types(self, subdomain: str) -> Dict[str, Any]:
        """
        Get all available services/event types

        Args:
            subdomain: Hospital subdomain

        Returns:
            Dict with list of event types
        """
        try:
            endpoint = self._get_endpoint("event-types")
            event_types = await self._request("GET", endpoint)

            return {
                "success": True,
                "count": len(event_types),
                "event_types": event_types
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to get event types: {str(e)}"
            }

    # ==================== MCP Tool: create_booking ====================

    async def create_booking(
        self,
        subdomain: str,
        event_type_id: int,
        date: str,
        time: str,
        guest_name: str,
        guest_phone: Optional[str] = None,
        guest_email: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new appointment booking

        Args:
            subdomain: Hospital subdomain
            event_type_id: Service ID
            date: Date in YYYY-MM-DD
            time: Time in HH:MM
            guest_name: Patient name
            guest_phone: Phone number (optional)
            guest_email: Email (optional)
            notes: Additional notes (optional)

        Returns:
            Dict with booking confirmation
        """
        try:
            endpoint = self._get_endpoint("booking/create")

            data = {
                "event_type_id": event_type_id,
                "date": date,
                "time": time,
                "guest_name": guest_name,
            }

            if guest_phone:
                data["guest_phone"] = guest_phone
            if guest_email:
                data["guest_email"] = guest_email
            if notes:
                data["notes"] = notes

            result = await self._request("POST", endpoint, json=data)

            return {
                "success": True,
                **result
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to create booking: {str(e)}"
            }

    # ==================== MCP Tool: search_appointments ====================

    async def search_appointments(
        self,
        subdomain: str,
        phone: Optional[str] = None,
        email: Optional[str] = None,
        booking_reference: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search appointments by phone, email, or reference

        Args:
            subdomain: Hospital subdomain
            phone: Phone number
            email: Email address
            booking_reference: Booking reference

        Returns:
            Dict with search results
        """
        try:
            endpoint = self._get_endpoint("booking/search")

            data = {}
            if phone:
                data["phone"] = phone
            if email:
                data["email"] = email
            if booking_reference:
                data["booking_reference"] = booking_reference

            result = await self._request("POST", endpoint, json=data)
            appointments = result.get("appointments", [])

            return {
                "success": True,
                "count": len(appointments),
                "appointments": appointments
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to search appointments: {str(e)}"
            }

    # ==================== MCP Tool: cancel_booking ====================

    async def cancel_booking(
        self,
        subdomain: str,
        booking_reference: str,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Cancel an existing appointment

        Args:
            subdomain: Hospital subdomain
            booking_reference: Booking reference number
            reason: Cancellation reason (optional)

        Returns:
            Dict with cancellation result
        """
        try:
            endpoint = self._get_endpoint("booking/cancel")

            data = {"booking_reference": booking_reference}
            if reason:
                data["reason"] = reason

            result = await self._request("POST", endpoint, json=data)

            return {
                "success": True,
                **result
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to cancel booking: {str(e)}"
            }

    # ==================== MCP Tool: reschedule_booking ====================

    async def reschedule_booking(
        self,
        subdomain: str,
        booking_reference: str,
        new_date: str,
        new_time: str,
        reason: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Reschedule an existing appointment

        Args:
            subdomain: Hospital subdomain
            booking_reference: Booking reference
            new_date: New date in YYYY-MM-DD
            new_time: New time in HH:MM
            reason: Reschedule reason (optional)

        Returns:
            Dict with reschedule result
        """
        try:
            endpoint = self._get_endpoint("booking/reschedule")

            data = {
                "booking_reference": booking_reference,
                "new_date": new_date,
                "new_time": new_time,
            }
            if reason:
                data["reason"] = reason

            result = await self._request("POST", endpoint, json=data)

            return {
                "success": True,
                **result
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to reschedule booking: {str(e)}"
            }
