from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import Optional


# Waarden die nooit als echte SECRET_KEY mogen dienen in uat/prod.
WEAK_SECRET_KEYS = {
    "",
    "change-me",
    "change-me-in-production",
    "change-me-in-production-use-random-string",
    "build-time-check",
    "secret",
}


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
    app_env: str = "prod"  # dev, hdev, uat, prod

    class Config:
        env_file = ".env"

    @model_validator(mode="after")
    def _enforce_secure_config(self):
        # Strenge controles enkel in de echte omgevingen (uat/prod).
        # dev/hdev/build mogen losser zijn voor lokaal werk en build-checks.
        if self.app_env in ("uat", "prod"):
            if self.secret_key in WEAK_SECRET_KEYS or len(self.secret_key) < 32:
                raise ValueError(
                    "SECRET_KEY is zwak of niet gezet voor "
                    f"APP_ENV={self.app_env}. Genereer een sterke sleutel met "
                    "python3 -c \"import secrets; print(secrets.token_hex(32))\" "
                    "en zet die in .env."
                )
            if self.debug:
                raise ValueError(
                    f"DEBUG mag niet aanstaan in APP_ENV={self.app_env}."
                )
        return self


settings = Settings()

