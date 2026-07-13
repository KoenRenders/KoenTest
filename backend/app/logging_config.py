import json
import logging
import sys
from app.config import settings


class JsonFormatter(logging.Formatter):
    """Gestructureerde logregels (#395): één JSON-object per regel, zodat de
    backend-logs machinaal filterbaar zijn (level, logger, exc) zonder externe
    logging-stack. Aan te zetten met LOG_FORMAT=json (default blijft tekst)."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        stream=sys.stdout,
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        force=True,
    )
    if settings.log_format == "json":
        for handler in logging.getLogger().handlers:
            handler.setFormatter(JsonFormatter())

    # Verlaag ruis van drukke third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # SQL-echo loopt via de engine (settings.sql_echo), NIET via LOG_LEVEL.
    # Zo logt LOG_LEVEL=DEBUG wel rijke app-logs, maar geen queries met
    # persoonsgegevens. De engine-logger houden we daarom op WARNING.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
