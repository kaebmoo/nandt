from pydantic import BaseModel

class ApiKeyUpdate(BaseModel):
    api_key: str