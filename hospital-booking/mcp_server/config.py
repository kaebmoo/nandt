"""
Configuration for MCP Server
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """MCP Server configuration"""

    # FastAPI Backend
    FASTAPI_BASE_URL = os.getenv("FASTAPI_BASE_URL", "http://localhost:8000")

    # Default Hospital
    DEFAULT_SUBDOMAIN = os.getenv("DEFAULT_SUBDOMAIN", "humnoi")

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


config = Config()
