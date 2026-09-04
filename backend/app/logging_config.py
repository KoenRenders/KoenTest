import json
import logging
import sys
from app.config import settings


# Extra-velden die in een JSON-logregel mogen belanden (#645). Bewust een
# allowlist en geen vrije dump van `record.__dict__`: een logregel mag nooit per
# ongeluk een e-mailadres, een naam of een querystring meedragen. Wie een veld
# toevoegt, doet dat hier — zichtbaar in de diff.
EXTRA_VELDEN = ("duration_ms", "method", "path", "route", "status", "slow")


class JsonFormatter(logging.Formatter):
    """Gestructureerde logregels (#395): één JSON-object per regel, zodat de
    backend-logs machinaal filterbaar zijn (level, logger, exc) zonder externe
    logging-stack. Aan te zetten met LOG_FORMAT=json (default blijft tekst).

    Sinds #645 dragen toegangslogregels hun duur als **veld** (`duration_ms`)
    i.p.v. in de tekst, zodat je op trage requests kan filteren zonder
    grep-acrobatiek."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for veld in EXTRA_VELDEN:
            waarde = getattr(record, veld, None)
            if waarde is not None:
                entry[veld] = waarde
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
