from decimal import Decimal
from pydantic_settings import BaseSettings
from pydantic import field_validator, model_validator
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

    # Overschrijvings-instructies (#157): rekeningnummer + begunstigde + termijn (dagen).
    payment_iban: Optional[str] = None
    payment_beneficiary: Optional[str] = None
    payment_term_days: int = 7

    frontend_url: str = "http://localhost:3000"
    public_url: str = "http://localhost:8000"
    app_env: str = "prod"  # dev, hdev, uat, prod

    # Versie + korte commit-SHA, gevoed via build-args (zie Dockerfile +
    # deploy-scripts). Fallback 'onbekend' lokaal/zonder build-info.
    app_version: str = "onbekend"
    git_sha: str = "onbekend"

    # Logniveau: DEBUG | INFO | WARNING | ERROR (default INFO)
    log_level: str = "INFO"

    # SQL-echo: logt ALLE queries mét bind-parameters (= mogelijk
    # persoonsgegevens). Staat los van LOG_LEVEL en standaard uit. Enkel voor
    # diepgaande lokale diagnose; geblokkeerd op uat/prod.
    sql_echo: bool = False

    # Sanity-bovengrens op het aantal per inschrijvingsitem. Voorkomt
    # negatieve/absurde aantallen via de API. Overschrijfbaar via .env.
    max_item_quantity: int = 50

    # Maximaal aantal activiteit-inschrijvingen per e-mailadres voor dezelfde
    # activiteit. Gezinnen schrijven soms in meerdere keren in; dit voorkomt
    # onbedoelde dubbels/teveelbetalingen zonder legitiem meermaals inschrijven
    # te blokkeren. Overschrijfbaar via .env.
    max_registrations_per_email: int = 3

    # Lidmaatschapsprijzen en datumgrenzen (MM-DD formaat).
    # Halfprijs: van half_price_start t/m half_price_end (inclusief).
    # Volgende-jaar-dekking: vanaf next_year_from dekt de betaling ook heel
    # het volgende jaar (valid_to = 31 dec volgend jaar i.p.v. dit jaar).
    membership_price_full: Decimal = Decimal("35.00")
    membership_price_half: Decimal = Decimal("17.50")
    membership_half_price_start_md: str = "04-16"   # MM-DD
    membership_half_price_end_md: str = "09-16"     # MM-DD
    membership_next_year_from_md: str = "09-17"     # MM-DD

    # Hernieuwingsdatum (MM-DD). Vanaf deze datum verschijnt de knop "Lidmaatschap
    # vernieuwen" ook voor leden met een nog-geldig lidmaatschap, zodat ze vroeg-
    # tijdig het volgende jaar kunnen afdekken. Als leeg: knop enkel bij verlopen lid.
    membership_renewal_start_md: Optional[str] = None

    class Config:
        env_file = ".env"

    @field_validator(
        "membership_half_price_start_md",
        "membership_half_price_end_md",
        "membership_next_year_from_md",
        "membership_renewal_start_md",
        mode="before",
    )
    @classmethod
    def _strip_md(cls, v):
        """Saneer MM-DD-waarden uit .env: docker-compose neemt álles na '=' als
        waarde, inclusief een eventuele inline `# comment`. Neem enkel het eerste
        token zodat 'MM-DD   # uitleg' correct 'MM-DD' wordt. Lege string → None."""
        if v is None:
            return None
        token = str(v).split()[0] if str(v).strip() else ""
        return token or None

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
            if self.sql_echo:
                raise ValueError(
                    f"SQL_ECHO mag niet aanstaan in APP_ENV={self.app_env}: "
                    "het logt alle queries met bind-parameters "
                    "(persoonsgegevens)."
                )
        return self


settings = Settings()

