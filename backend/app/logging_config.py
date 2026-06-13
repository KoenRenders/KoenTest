import logging
import sys
from app.config import settings


def configure_logging() -> None:
    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    logging.basicConfig(
        stream=sys.stdout,
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        force=True,
    )

    # Verlaag ruis van drukke third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # SQL-echo loopt via de engine (settings.sql_echo), NIET via LOG_LEVEL.
    # Zo logt LOG_LEVEL=DEBUG wel rijke app-logs, maar geen queries met
    # persoonsgegevens. De engine-logger houden we daarom op WARNING.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
