"""
MCP Server for Hospital Booking System
Exposes booking tools to AI agents (Claude, etc.)

Usage:
    python server.py
"""
import asyncio
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent
from tools.booking_tools import BookingTools
from config import config

# Configure logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create MCP server
server = Server("hospital-booking")

# Global tools instance
tools: BookingTools = None


@server.list_tools()
async def list_tools() -> list[Tool]:
    """
    List all available tools for AI agents
    """
    return [
        Tool(
            name="check_availability",
            description="Check available time slots for a specific service and date",
            inputSchema={
                "type": "object",
                "properties": {
                    "subdomain": {
                        "type": "string",
                        "description": "Hospital subdomain (e.g., 'humnoi')"
                    },
                    "event_type_id": {
                        "type": "integer",
                        "description": "Service/event type ID"
                    },
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format"
                    }
                },
                "required": ["subdomain", "event_type_id", "date"]
            }
        ),
        Tool(
            name="get_event_types",
            description="Get all available services/event types for booking",
            inputSchema={
                "type": "object",
                "properties": {
                    "subdomain": {
                        "type": "string",
                        "description": "Hospital subdomain (e.g., 'humnoi')"
                    }
                },
                "required": ["subdomain"]
            }
        ),
        Tool(
            name="create_booking",
            description="Create a new appointment booking",
            inputSchema={
                "type": "object",
                "properties": {
                    "subdomain": {
                        "type": "string",
                        "description": "Hospital subdomain"
                    },
                    "event_type_id": {
                        "type": "integer",
                        "description": "Service ID to book"
                    },
                    "date": {
                        "type": "string",
                        "description": "Appointment date in YYYY-MM-DD format"
                    },
                    "time": {
                        "type": "string",
                        "description": "Appointment time in HH:MM format"
                    },
                    "guest_name": {
                        "type": "string",
                        "description": "Patient/guest full name"
                    },
                    "guest_phone": {
                        "type": "string",
                        "description": "Patient phone number (optional)"
                    },
                    "guest_email": {
                        "type": "string",
                        "description": "Patient email (optional)"
                    },
                    "notes": {
                        "type": "string",
                        "description": "Additional notes (optional)"
                    }
                },
                "required": ["subdomain", "event_type_id", "date", "time", "guest_name"]
            }
        ),
        Tool(
            name="search_appointments",
            description="Search appointments by phone, email, or booking reference",
            inputSchema={
                "type": "object",
                "properties": {
                    "subdomain": {
                        "type": "string",
                        "description": "Hospital subdomain"
                    },
                    "phone": {
                        "type": "string",
                        "description": "Phone number to search (optional)"
                    },
                    "email": {
                        "type": "string",
                        "description": "Email to search (optional)"
                    },
                    "booking_reference": {
                        "type": "string",
                        "description": "Booking reference number (optional)"
                    }
                },
                "required": ["subdomain"]
            }
        ),
        Tool(
            name="cancel_booking",
            description="Cancel an existing appointment",
            inputSchema={
                "type": "object",
                "properties": {
                    "subdomain": {
                        "type": "string",
                        "description": "Hospital subdomain"
                    },
                    "booking_reference": {
                        "type": "string",
                        "description": "Booking reference number"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Cancellation reason (optional)"
                    }
                },
                "required": ["subdomain", "booking_reference"]
            }
        ),
        Tool(
            name="reschedule_booking",
            description="Reschedule an existing appointment to a new date/time",
            inputSchema={
                "type": "object",
                "properties": {
                    "subdomain": {
                        "type": "string",
                        "description": "Hospital subdomain"
                    },
                    "booking_reference": {
                        "type": "string",
                        "description": "Booking reference number"
                    },
                    "new_date": {
                        "type": "string",
                        "description": "New date in YYYY-MM-DD format"
                    },
                    "new_time": {
                        "type": "string",
                        "description": "New time in HH:MM format"
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reschedule reason (optional)"
                    }
                },
                "required": ["subdomain", "booking_reference", "new_date", "new_time"]
            }
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """
    Execute a tool and return results
    """
    global tools

    try:
        logger.info(f"Calling tool: {name} with arguments: {arguments}")

        # Route to appropriate tool method
        if name == "check_availability":
            result = await tools.check_availability(
                subdomain=arguments["subdomain"],
                event_type_id=arguments["event_type_id"],
                date=arguments["date"]
            )

        elif name == "get_event_types":
            result = await tools.get_event_types(
                subdomain=arguments["subdomain"]
            )

        elif name == "create_booking":
            result = await tools.create_booking(
                subdomain=arguments["subdomain"],
                event_type_id=arguments["event_type_id"],
                date=arguments["date"],
                time=arguments["time"],
                guest_name=arguments["guest_name"],
                guest_phone=arguments.get("guest_phone"),
                guest_email=arguments.get("guest_email"),
                notes=arguments.get("notes")
            )

        elif name == "search_appointments":
            result = await tools.search_appointments(
                subdomain=arguments["subdomain"],
                phone=arguments.get("phone"),
                email=arguments.get("email"),
                booking_reference=arguments.get("booking_reference")
            )

        elif name == "cancel_booking":
            result = await tools.cancel_booking(
                subdomain=arguments["subdomain"],
                booking_reference=arguments["booking_reference"],
                reason=arguments.get("reason")
            )

        elif name == "reschedule_booking":
            result = await tools.reschedule_booking(
                subdomain=arguments["subdomain"],
                booking_reference=arguments["booking_reference"],
                new_date=arguments["new_date"],
                new_time=arguments["new_time"],
                reason=arguments.get("reason")
            )

        else:
            raise ValueError(f"Unknown tool: {name}")

        logger.info(f"Tool {name} result: {result}")

        # Format result as text
        import json
        result_text = json.dumps(result, indent=2)

        return [TextContent(type="text", text=result_text)]

    except Exception as e:
        logger.error(f"Tool error: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """
    Main entry point - start MCP server
    """
    global tools

    logger.info("Starting Hospital Booking MCP Server...")
    logger.info(f"FastAPI URL: {config.FASTAPI_BASE_URL}")
    logger.info(f"Default Subdomain: {config.DEFAULT_SUBDOMAIN}")

    # Initialize booking tools
    tools = BookingTools(
        base_url=config.FASTAPI_BASE_URL,
        subdomain=config.DEFAULT_SUBDOMAIN
    )

    try:
        # Start server with stdio transport
        async with stdio_server() as (read_stream, write_stream):
            logger.info("MCP Server running on stdio")
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options()
            )
    finally:
        # Cleanup
        await tools.close()
        logger.info("MCP Server stopped")


if __name__ == "__main__":
    asyncio.run(main())
