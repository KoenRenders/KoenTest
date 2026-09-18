"""Tools die de bot mag aanroepen — meteen de security-grens van de POC.

Exact drie functies, allemaal publiek: twee lees-acties op activiteiten en het
indienen van een idee. **Geen** ledendata, betalingen of admin. ``execute_tool``
weigert elke naam buiten deze allowlist, zodat een gehallucineerde tool-aanroep
nooit iets anders kan raken.

De structuurvelden (datum/prijs/locatie) komen altijd uit de DB en winnen van
vrije tekst — de bot mag niets verzinnen.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.domains.activities.api import Activity, ActivityDate
from app.domains.media.api import MediaAsset
from app.domains.chatbot.models import ChatbotInfo

logger = logging.getLogger(__name__)

# --- Allowlist: de enige tools die de bot mag aanroepen ----------------------

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_activities",
            "description": (
                "Geeft activiteiten van Raak Millegem met datum, locatie, "
                "prijs-vanaf en of ze enkel voor leden zijn. Standaard de komende, "
                "niet-geannuleerde activiteiten (when='upcoming'); zet when='past' "
                "voor voorbije activiteiten (meest recent eerst). Gebruik dit voor "
                "elke vraag over de agenda, wat er te doen is, of wat er geweest is."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "when": {
                        "type": "string",
                        "enum": ["upcoming", "past"],
                        "description": "'upcoming' (default) voor komende, 'past' voor voorbije activiteiten.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_activity_detail",
            "description": (
                "Geeft de details van één activiteit (datums, locatie, "
                "onderdelen en prijzen, opmerkingen). Geef het id terug dat je "
                "uit get_activities kreeg."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "activity_id": {
                        "type": "integer",
                        "description": "Het id van de activiteit.",
                    }
                },
                "required": ["activity_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_idea",
            "description": (
                "Bezorgt de vraag, opmerking of het idee van de bezoeker via het "
                "contactformulier. Gebruik dit wanneer je een vraag "
                "niet met zekerheid kan beantwoorden, of wanneer de bezoeker "
                "iets wil achterlaten. Vraag ALTIJD eerst zowel de naam ALS het "
                "e-mailadres — beide zijn verplicht, want zonder e-mailadres kan "
                "het bestuur niet antwoorden. Roep deze tool pas aan wanneer je "
                "naam én e-mailadres hebt."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Naam van de bezoeker (verplicht)."},
                    "content": {
                        "type": "string",
                        "description": "De vraag, opmerking of het idee.",
                    },
                    "email": {
                        "type": "string",
                        "description": "E-mailadres van de bezoeker (verplicht, voor het antwoord).",
                    },
                },
                "required": ["name", "content", "email"],
            },
        },
    },
]

ALLOWED_TOOLS = {spec["function"]["name"] for spec in TOOL_SPECS}

# --- Wat een tool-resultaat naar buiten mag dragen --------------------------

# Het veldcontract van de publieke bot (CR-07 §5.1). De allowlist hierboven zegt
# WELKE tools mogen draaien; dit zegt WELKE VELDEN hun antwoord mag bevatten —
# want een tool-resultaat gaat integraal naar Mistral. Een veld dat aan een
# serialiser wordt toegevoegd zonder dat het hier staat, is een nieuwe export naar
# een derde partij; die mag geen stille wijziging zijn maar een rode build
# (`test_public_tool_field_contract.py`).
#
# Waarom hier geen classificatie per veld zoals in het universum (`ai_exposure`)?
# Daar is het object de eenheid en kiest een gebruiker wat hij meeneemt; hier ligt
# de vorm van het antwoord vast in code en reist alles even ver — naar het model.
# Het contract hoeft dus niet te zeggen hoe ver een veld mag, wel dát de lijst
# volledig en bedoeld is. Sleutels zijn paden: "" is de wortel, "x[]" is één
# element van lijst x.
PUBLIC_FIELD_CONTRACT: dict[str, dict[str, set[str]]] = {
    "get_activities": {
        "": {"when", "activities"},
        "activities[]": {
            "id", "name", "location", "members_only", "price_from", "dates",
        },
        "activities[].dates[]": {
            "start_date", "end_date", "start_time", "end_time",
        },
    },
    "get_activity_detail": {
        # Twee vormen: de gevonden activiteit, of de nette weigering.
        "": {
            "id", "name", "location", "members_only", "notes", "flyer_text",
            "price_from", "dates", "components", "error",
        },
        "dates[]": {"start_date", "end_date", "start_time", "end_time"},
        "components[]": {
            "name", "description", "price", "member_price", "info_text",
            "products",
        },
        "components[].products[]": {"name", "price", "member_price"},
    },
    # Bewust geen bezoekersgegevens terug: wat de bezoeker instuurde komt niet in
    # het antwoord, dus het model krijgt naam en e-mail niet nog eens voorgeschoteld.
    "submit_idea": {"": {"ok", "message", "error"}},
}


# --- Helpers -----------------------------------------------------------------

def _fmt_price(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return f"{Decimal(value):.2f}"


def _price_from(activity: Activity) -> Optional[str]:
    """Laagste niet-gratis prijs over onderdelen en producten, of None (gratis)."""
    prices: list[Decimal] = []
    for sub in activity.sub_registrations:
        if not sub.is_free and sub.price is not None:
            prices.append(Decimal(sub.price))
        for product in sub.products:
            if not product.is_free and product.price is not None:
                prices.append(Decimal(product.price))
    return _fmt_price(min(prices)) if prices else None


def _extracted_text(
    db: Session, kind: str, *, activity_id: Optional[int] = None, component_id: Optional[int] = None
) -> Optional[str]:
    """De effectieve poster/reglement-tekst voor de bot (#206), of None.

    De tekst staat in ``chatbot_info`` (gekoppeld aan het media-asset), niet op de
    activiteit — alle chatbot-tekst staat los van de domeintabellen. We nemen de
    effectieve tekst (override/extracted + addition) van een actieve rij."""
    q = db.query(MediaAsset).filter(MediaAsset.kind == kind)
    if activity_id is not None:
        q = q.filter(MediaAsset.activity_id == activity_id)
    if component_id is not None:
        q = q.filter(MediaAsset.component_id == component_id)
    asset = q.first()
    if not asset:
        return None
    ci = (
        db.query(ChatbotInfo)
        .filter(ChatbotInfo.media_asset_id == asset.id, ChatbotInfo.is_active == True)  # noqa: E712
        .first()
    )
    return (ci.effective_text or None) if ci else None


def _serialise_dates(activity: Activity) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for d in sorted(activity.dates, key=lambda x: (x.start_date, x.start_time or x.start_date)):
        out.append(
            {
                "start_date": d.start_date.isoformat() if d.start_date else None,
                "end_date": d.end_date.isoformat() if d.end_date else None,
                "start_time": d.start_time.strftime("%H:%M") if d.start_time else None,
                "end_time": d.end_time.strftime("%H:%M") if d.end_time else None,
            }
        )
    return out


# --- Tool-implementaties -----------------------------------------------------

def get_activities(db: Session, when: str = "upcoming", limit: int = 20) -> dict[str, Any]:
    """Komende of voorbije, niet-geannuleerde activiteiten.

    ``when="upcoming"`` (default): vanaf vandaag, eerstvolgende eerst.
    ``when="past"``: vóór vandaag, meest recent eerst. In beide gevallen max
    ``limit`` (default 20), zodat de prompt niet volloopt en de kost beperkt blijft.
    """
    today = date.today()
    is_past = when == "past"

    date_q = db.query(ActivityDate.activity_id).distinct()
    date_q = date_q.filter(
        ActivityDate.start_date < today if is_past else ActivityDate.start_date >= today
    )
    activity_ids = [row[0] for row in date_q.all()]
    activities = (
        db.query(Activity)
        .filter(Activity.id.in_(activity_ids), Activity.is_cancelled == False)  # noqa: E712
        .all()
    )

    items = []
    for a in activities:
        items.append(
            {
                "id": a.id,
                "name": a.name,
                "location": a.location,
                "members_only": a.members_only,
                "price_from": _price_from(a),
                "dates": _serialise_dates(a),
            }
        )
    # Komend: eerstvolgende eerst. Verleden: meest recent eerst.
    fallback = "0000" if is_past else "9999"
    items.sort(
        key=lambda x: (x["dates"][0]["start_date"] if x["dates"] else fallback),
        reverse=is_past,
    )
    return {"when": "past" if is_past else "upcoming", "activities": items[:limit]}


_UNSPECIFIED = "niet vermeld"


def _text_or_unspecified(value: Optional[str]) -> str:
    """Maak afwezigheid expliciet voor het model (anti-hallucinatie, laag 2):
    een leeg veld wordt 'niet vermeld' i.p.v. weggelaten/None, zodat de bot het
    als feit ziet en niets verzint."""
    return value if (value and value.strip()) else _UNSPECIFIED


def get_activity_detail(db: Session, activity_id: int) -> dict[str, Any]:
    a = db.query(Activity).filter(Activity.id == activity_id).first()
    if not a:
        return {"error": "Activiteit niet gevonden."}

    components = []
    for sub in a.sub_registrations:
        components.append(
            {
                "name": sub.name,
                "description": _text_or_unspecified(sub.description),
                "price": None if sub.is_free else _fmt_price(sub.price),
                "member_price": _fmt_price(sub.member_price),
                # Zachte info uit het reglement/info-document van dit onderdeel (#206).
                "info_text": _text_or_unspecified(
                    _extracted_text(db, "component_info", component_id=sub.id)
                ),
                "products": [
                    {
                        "name": p.name,
                        "price": None if p.is_free else _fmt_price(p.price),
                        "member_price": _fmt_price(p.member_price),
                    }
                    for p in sub.products
                ],
            }
        )

    return {
        "id": a.id,
        "name": a.name,
        "location": a.location,
        "members_only": a.members_only,
        "notes": _text_or_unspecified(a.notes),
        # Zachte info uit de poster (#206); structuurvelden hierboven winnen altijd.
        "flyer_text": _text_or_unspecified(
            _extracted_text(db, "activity_poster", activity_id=a.id)
        ),
        "price_from": _price_from(a),
        "dates": _serialise_dates(a),
        "components": components,
    }


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def submit_idea(
    db: Session, name: str, content: str, email: Optional[str] = None
) -> dict[str, Any]:
    """Hergebruikt exact het berichten-schrijfpad (geen tweede schrijfweg).

    Naam én e-mailadres zijn **verplicht**: zonder e-mail kan het bestuur niet
    antwoorden. We dwingen dat server-side af (niet enkel via de prompt), want het
    LLM kan de tool toch zonder e-mail aanroepen. Bij ontbrekende/ongeldige invoer
    geven we een nette fout terug zodat de bot het ontbrekende gegeven opvraagt —
    er wordt dan géén idee weggeschreven.
    """
    name = (name or "").strip()
    content = (content or "").strip()
    email = (email or "").strip()

    if not name or not email:
        return {
            "ok": False,
            "error": (
                "Zowel naam als e-mailadres zijn verplicht. Vraag de bezoeker "
                "vriendelijk om het ontbrekende gegeven en roep de tool daarna "
                "opnieuw aan."
            ),
        }
    if not _EMAIL_RE.match(email):
        return {
            "ok": False,
            "error": (
                "Dit e-mailadres lijkt ongeldig. Vraag de bezoeker om een geldig "
                "e-mailadres en roep de tool daarna opnieuw aan."
            ),
        }
    if not content:
        return {
            "ok": False,
            "error": "Er is geen vraag of idee opgegeven. Vraag de bezoeker wat hij wil doorgeven.",
        }

    # Eén schrijfpad (#398): bericht-inzending + behartigen-taak (werkbank) +
    # bevestigingsmail — de aparte bestuursmail is vervangen door de taak.
    from app.domains.forms.api import submit_bericht

    submission_id = submit_bericht(db, naam=name, email=email, bericht=content)
    if submission_id is None:
        return {"ok": False, "error": "Berichten zijn tijdelijk niet beschikbaar."}

    return {
        "ok": True,
        "message": "Je bericht is doorgegeven. Je krijgt een bevestiging per e-mail.",
    }


# --- Dispatch (security-grens) ----------------------------------------------

def execute_tool(name: str, arguments: dict[str, Any], db: Session) -> str:
    """Voer een tool uit en geef het resultaat als JSON-string terug.

    Weigert elke naam buiten de allowlist — dat is de harde grens van de bot.
    """
    if name not in ALLOWED_TOOLS:
        logger.warning("Chatbot vroeg niet-toegelaten tool aan: %s", name)
        return json.dumps({"error": f"Onbekende of niet-toegelaten tool: {name}"})

    args = arguments or {}
    try:
        if name == "get_activities":
            result = get_activities(db, when=str(args.get("when") or "upcoming"))
        elif name == "get_activity_detail":
            result = get_activity_detail(db, activity_id=int(args.get("activity_id") or 0))
        elif name == "submit_idea":
            result = submit_idea(
                db,
                name=str(args.get("name", "")),
                content=str(args.get("content", "")),
                email=str(args.get("email", "")),
            )
        else:  # pragma: no cover - door allowlist afgedekt
            result = {"error": "niet-geïmplementeerde tool"}
    except (TypeError, ValueError) as exc:
        return json.dumps({"error": f"Ongeldige parameters: {exc}"})

    return json.dumps(result, ensure_ascii=False, default=str)



# ── De leestools, voor een ander pakket (#975) ───────────────────────────────
#
# De beheer-assistent mag alles lezen wat de publieke bot leest (Koen, 16
# september 2026). Die tools blijven van dit domein — hun implementatie én hun
# veldcontract staan hier — en worden via de facade uitgeleend.
#
# Alleen LEZEN. `submit_idea` maakt een bericht en een werkbanktaak aan; een
# pakket dat dit leent, krijgt hem niet, ook niet per ongeluk. Daarom een eigen
# allowlist en een eigen ingang, en niet `execute_tool`: die kent de schrijftool.
READ_ONLY_TOOLS = frozenset({"get_activities", "get_activity_detail"})


def read_tool_specs() -> list[dict[str, Any]]:
    """De specs van de leestools, als kopie — een lener past ze niet aan in het
    origineel."""
    import copy

    return [copy.deepcopy(spec) for spec in TOOL_SPECS
            if spec["function"]["name"] in READ_ONLY_TOOLS]


def execute_read_tool(name: str, arguments: dict[str, Any], db: Session) -> str:
    """Een leestool uitvoeren. Weigert alles wat niet enkel leest, bij naam."""
    if name not in READ_ONLY_TOOLS:
        logger.warning("Leestool gevraagd die niet enkel leest: %s", name)
        return json.dumps({"error": f"Niet toegelaten in deze modus: {name}."})
    return execute_tool(name, arguments, db)
