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

from app.models.activity import Activity, ActivityDate
from app.models.asset import MediaAsset
from app.models.chatbot_info import ChatbotInfo
from app.models.idea import Idea
from app.services.email import send_idea_acknowledgement

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
    db: Session, kind: str, *, activity_id: int = None, component_id: int = None
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
    """Hergebruikt exact het IdeaBox-schrijfpad (geen tweede schrijfweg).

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

    idea = Idea(submitter_name=name, submitter_email=email, content=content)
    db.add(idea)
    db.commit()
    db.refresh(idea)

    try:
        send_idea_acknowledgement(to_email=email, name=name, message=content)
    except Exception as exc:  # mail mag de flow nooit breken
        logger.warning("Bevestigingsmail voor idee (chatbot) mislukt: %s", exc)

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
            result = get_activity_detail(db, activity_id=int(args.get("activity_id")))
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
