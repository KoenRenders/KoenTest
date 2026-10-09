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
EXTRA_VELDEN = (
    "duration_ms",
    "method",
    "path",
    "route",
    "status",
    "slow",
    # #662: wélk van de drie CSRF-gevallen faalde. Nooit de
    # tokenwaarde zelf — dat is een beveiligingstoken en deze logs
    # worden opgehaald met `raak fetch`.
    "csrf_fail",
)


#: The application's own loggers: every module logs as `app.…` (`getLogger(__name__)`).
OWN_LOGGER = "app"

#: The level of every logger that is not the application's own (#1828). A library's
#: DEBUG and INFO are its wire talk — what it sends and receives, line by line — and
#: that does not belong in an application log, whatever `LOG_LEVEL` says.
LIBRARY_LEVEL = logging.WARNING

#: The libraries that get a level of their own, each with the reason. This is the one
#: place: a library that must be heard at INFO is a line here, and none may go below
#: INFO (`configure_logging` refuses it) — no setting of an environment reaches a
#: library.
LIBRARY_LEVELS: dict[str, tuple[int, str]] = {
    "uvicorn": (
        logging.INFO,
        "its start-up line 'Uvicorn running' is what the deploy's clean-start check "
        "reads; uvicorn writes it on a handler of its own, not on the application's",
    ),
    "uvicorn.access": (
        logging.WARNING,
        "uvicorn puts it at INFO itself, on a handler of its own; the application "
        "writes its own access line with the duration (#645)",
    ),
    "sqlalchemy.engine": (
        logging.WARNING,
        "SQL echo goes through the engine (`settings.sql_echo`), never through "
        "LOG_LEVEL: a query carries bind parameters, which may be personal data",
    ),
}


def is_own(name: str) -> bool:
    """Whether a logger is the application's own."""
    return name == OWN_LOGGER or name.startswith(OWN_LOGGER + ".")


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
                "log will not survive this deploy (#766).",
                directory,
            )
        return None
    return path / "app.log"


def configure_logging() -> None:
    """Handlers on the root logger, and the levels — all of them, here (#1828).

    `LOG_LEVEL` is the level of the application's own loggers and of nothing else.
    The root logger stands at `LIBRARY_LEVEL`, so every other logger — one that
    exists now, or one a library makes when it first connects — inherits WARNING.
    Before, the root carried `LOG_LEVEL` and every library inherited that: a process
    started with `LOG_LEVEL=DEBUG` wrote each library's wire talk into the log.

    The handlers carry no level of their own: stdout and the file hold the same
    lines, and what reaches them is decided by the loggers alone.
    """
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    too_low = sorted(
        name for name, (lowest, _why) in LIBRARY_LEVELS.items() if lowest < logging.INFO
    )
    if too_low:
        raise ValueError(f"A library never logs below INFO (#1828): {', '.join(too_low)}")

    logging.basicConfig(
        stream=sys.stdout,
        level=LIBRARY_LEVEL,
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
        file_handler.setFormatter(
            JsonFormatter()
            if settings.log_format == "json"
            else logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s: %(message)s", datefmt="%Y-%m-%dT%H:%M:%S"
            )
        )
        logging.getLogger().addHandler(file_handler)

    # A level somebody else gave a library's logger — the library itself at import,
    # a config file read earlier in the process — is taken back: this is the one
    # place. Loggers made later inherit the root.
    for name, logger in logging.root.manager.loggerDict.items():
        if isinstance(logger, logging.Logger) and not is_own(name):
            logger.setLevel(logging.NOTSET)
    logging.getLogger(OWN_LOGGER).setLevel(level)
    for name, (lowest, _why) in LIBRARY_LEVELS.items():
        logging.getLogger(name).setLevel(lowest)
