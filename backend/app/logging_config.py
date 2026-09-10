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


def app_logbestand() -> Path | None:
    """Het pad waar het applicatielog óók naartoe gaat, of None (#766).

    None wanneer de map niet ingesteld is of niet bestaat — lokaal en in CI is er
    geen volume gemonteerd, en een ontbrekende mount mag de start nooit blokkeren.
    Op hdev/uat/prod hoort ze er wél te zijn, dus daar wordt het gemeld in plaats
    van stil overgeslagen: een applicatielog dat stilletjes nergens landt, ontdek
    je pas wanneer je het nodig hebt.
    """
    map_ = (settings.app_log_dir or "").strip()
    if not map_:
        return None
    pad = Path(map_)
    if not pad.is_dir() or not os.access(pad, os.W_OK):
        if settings.app_env in ("hdev", "uat", "prod"):
            logging.getLogger(__name__).warning(
                "APP_LOG_DIR=%s bestaat niet of is niet schrijfbaar — het "
                "applicatielog overleeft deze deploy niet (#766).", map_)
        return None
    return pad / "app.log"


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

    # #766: hetzelfde log, maar dan op een plek die de container overleeft. Bewust
    # BOVENOP stdout en niet in plaats daarvan: `raakctl logs` en `docker compose
    # logs` blijven werken zoals ze werkten, en de deploy-uitvoer verandert niet.
    #
    # Zonder rotatie, en dat is een besliste keuze en geen vergetelheid: gemeten op
    # PROD (8 september 2026) ruwweg 1 MB per dag tegen 22 GB vrij. Rotatie én een
    # bewaartermijn komen terug zodra deze logs echt lang blijven staan — de schijf
    # loopt ooit vol, en er staan persoonsgegevens langer op schijf dan nodig. Dat
    # laatste is geen theorie: op `email_log` staat niet voor niets al een termijn.
    bestand = app_logbestand()
    if bestand is not None:
        bestandshandler = logging.FileHandler(bestand, encoding="utf-8")
        bestandshandler.setLevel(level)
        bestandshandler.setFormatter(
            JsonFormatter() if settings.log_format == "json"
            else logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s",
                                   datefmt="%Y-%m-%dT%H:%M:%S"))
        logging.getLogger().addHandler(bestandshandler)

    # Verlaag ruis van drukke third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # SQL-echo loopt via de engine (settings.sql_echo), NIET via LOG_LEVEL.
    # Zo logt LOG_LEVEL=DEBUG wel rijke app-logs, maar geen queries met
    # persoonsgegevens. De engine-logger houden we daarom op WARNING.
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
