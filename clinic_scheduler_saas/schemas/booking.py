from pydantic import BaseModel

class BookingCreate(BaseModel):
    eventTypeId: int
    start: str # ISO Format e.g., "2025-08-20T10:00:00.000Z"
    end: str
    title: str
    description: str | None = None
    responses: dict # To store custom fields like HN
