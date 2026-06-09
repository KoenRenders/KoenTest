from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    database_url: str = "postgresql://postgres:postgres@localhost:5432/raakmillegem"
    secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    debug: bool = False

    gmail_user: Optional[str] = None
    gmail_app_password: Optional[str] = None
    gmail_from: Optional[str] = None

    mollie_api_key: Optional[str] = None
    frontend_url: str = "http://localhost:3000"
    public_url: str = "http://localhost:8000"

    class Config:
        env_file = ".env"


settings = Settings()
