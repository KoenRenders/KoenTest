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

    # E-maillog (#328): bewaartermijn in dagen voor de centrale email_log-tabel.
    # Standaard 365 (1 jaar). 0 (of negatief) = niet opschonen, oneindig bewaren.
    # Niet auto-toegevoegd aan de echte .env-bestanden; per host instellen.
    email_log_retention_days: int = 365

    mollie_api_key: Optional[str] = None

    # Chatbot 'Raakje' (#205). LLM-provider zit achter een swapbaar laagje.
    # chat_llm_provider: 'auto' (Mistral zodra er een key staat, anders mock),
    # 'mistral' (forceer), of 'mock' (afhankelijkheidsvrij, CI/lokaal).
    # chat_enabled: hoofdschakelaar. Standaard UIT → de code mag mee naar PROD
    # zonder dat de bot live is; aanzetten zodra key + HDEV-validatie klaar zijn.
    chat_enabled: bool = False
    mistral_api_key: Optional[str] = None
    chat_llm_provider: str = "auto"
    chat_model: str = "mistral-small-latest"  # = Mistral Small 4
    # Vangrails (kosten/misbruik): cap per bericht, geschiedenis en dag.
    chat_max_input_chars: int = 2000
    chat_max_history_messages: int = 20
    chat_daily_char_budget: int = 20000
    chat_max_tool_rounds: int = 4

    # Spraak-naar-tekst (STT) van chatbot Raakje — #282. Twee orthogonale knoppen:
    # de STRATEGIE (STT_MODE) en de server-side PROVIDER (STT_PROVIDER).
    #
    # STT_MODE — wie verwerkt de spraak per browser:
    #   browser_only  : enkel native browser-STT (Web Speech API); browsers zonder
    #                   native krijgen geen mic. = gedrag van vandaag, géén provider.
    #                   Default → dark-launch: de WS-route weigert de handshake en de
    #                   code mag mee naar PROD zonder dat de provider live is.
    #   native_first  : native waar de browser het ondersteunt, anders via de provider.
    #   provider_only : altijd via de provider (bv. EU/GDPR), ook met native beschikbaar.
    stt_mode: str = "browser_only"
    # STT_PROVIDER — de server-side spraak-naar-tekst-bron wanneer de provider wordt
    # gebruikt (native_first/provider_only): 'voxtral' (Mistral, EU). 'mock' is enkel
    # voor CI/dev (afhankelijkheidsvrij, geen netwerk). Hergebruikt MISTRAL_API_KEY.
    stt_provider: str = "voxtral"
    stt_model: str = "voxtral-mini-transcribe-realtime-2602"
    stt_base_url: str = "wss://api.mistral.ai"   # server_url voor de mistralai[realtime]-SDK
    stt_sample_rate: int = 16000                 # Voxtral: pcm_s16le @ 16 kHz mono
    # STT_LANGUAGE — forceer de transcriptietaal i.p.v. autodetectie (#295), zodat
    # Voxtral niet spontaan naar een andere taal overschakelt. ISO-639-1 (bv. 'nl').
    # Defensief meegegeven: accepteert de realtime-SDK de parameter niet, dan valt de
    # adapter terug op autodetectie (geen fout). Leeg = niet meegeven.
    stt_language: str = "nl"
    # Vangrails (kosten/misbruik), defense-in-depth zoals de chat-limiters (#282):
    stt_ws_max_handshakes_per_min: int = 10       # handshake-rate-limit per IP
    stt_idle_timeout_seconds: int = 15            # geen audioframe binnen X s → sluit
    stt_max_session_bytes: int = 8_000_000        # harde audio-cap per sessie (~PCM16)
    stt_daily_audio_budget_bytes: int = 80_000_000  # harde audio-cap per IP per dag

    # Documenttekst-extractie (#206). PDF met tekstlaag → gratis via pypdf; scan/
    # afbeelding → Mistral OCR (zelfde MISTRAL_API_KEY). ocr_enabled uit → enkel
    # de gratis tekstlaag, geen OCR-call. pdf_text_min_chars = drempel waaronder
    # een PDF-tekstlaag als 'onbruikbaar' geldt en we naar OCR vallen.
    ocr_model: str = "mistral-ocr-latest"
    ocr_enabled: bool = True
    pdf_text_min_chars: int = 80

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
    # "text" (leesbaar, default) of "json" (gestructureerd, #395)
    log_format: str = "text"
    # Kernel-jobs scheduler-loop (#396); tests zetten dit uit.
    jobs_enabled: bool = True

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

