from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    STRIPE_SECRET_KEY: str
    STRIPE_WEBHOOK_SECRET: str
    CLIENT_ORIGIN_URL: str

    class Config:
        env_file = ".env"

settings = Settings()