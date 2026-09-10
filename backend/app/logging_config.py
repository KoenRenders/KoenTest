from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

from app.config import settings


# Extra-velden die in een JSON-logregel mogen belanden (#645). Bewust een
# allowlist en geen vrije dump van `record.__dict__`: een logregel mag nooit per
# ongeluk een e-mailadres, een naam of een querystring meedragen. Wie een veld
# toevoegt, doet dat hier — zichtbaar in de diff.
EXTRA_VELDEN = ("duration_ms", "method", "path", "route", "status", "slow",
                # #662: wélk van de drie CSRF-gevallen faalde. Nooit de
                # tokenwaarde zelf — dat is een beveiligingstoken en deze logs
                # worden opgehaald met `raak fetch`.
                "csrf_fail")


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


def app_log_file() -> Path | None:
    """The path the application log ALSO goes to, or None (#766).

    None when the directory is not configured or does not exist — locally and in CI no
    volume is mounted, and a missing mount must never block startup. On hdev/uat/prod
    it is supposed to be there, so it is reported instead of silently skipped: an
    application log that quietly lands nowhere is something you find out about only
    when you need it.
    """
    directory = (settings.app_log_dir or "").strip()
    if not directory:
        return None
    path = Path(directory)
    if not path.is_dir() or not os.access(path, os.W_OK):
        if settings.app_env in ("hdev", "uat", "prod"):
            logging.getLogger(__name__).warning(
                "APP_LOG_DIR=%s does not exist or is not writable — the application "
                "log will not survive this deploy (#766).", directory)
        return None
    return path / "app.log"


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

    # #766: the same log, but somewhere that outlives the container. Deliberately ON
    # TOP OF stdout rather than instead of it: `raakctl logs` and `docker compose logs`
    # keep working exactly as they did, and the deploy output does not change.
    #
    # Without rotation, and that is a decision rather than an oversight: measured on
    # PROD (8 September 2026) roughly 1 MB per day against 22 GB free. Rotation AND a
    # retention period come back the moment these logs really start piling up — the
    # disk fills eventually, and personal data sits on disk longer than it needs to.
    # That last part is not theory: `email_log` already carries a retention period.
    log_file = app_log_file()
    if log_file is not None:
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(
            JsonFormatter() if settings.log_format == "json"
            else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s",
                                   datefmt="%Y-%m-%dT%H:%M:%S"))
        logging.getLogger().addHandler(file_handler)

    # Verlaag ruis van drukke third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # SQL-echo loopt via de engine (settings.sql_echo), NIET via LOG_LEVEL.
    # Zo logt LOG_LEVEL=DEBUG wel rijke app-logs, maar geen queries met
    # persoonsgegevens. De engine-logger houden we daarom op WARNING.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
