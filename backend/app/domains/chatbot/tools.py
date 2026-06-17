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
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.activity import Activity, ActivityDate
from app.models.asset import MediaAsset
from app.models.idea import Idea
from app.services.email import send_idea_acknowledgement

logger = logging.getLogger(__name__)

# --- Allowlist: de enige tools die de bot mag aanroepen ----------------------

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_upcoming_activities",
            "description": (
                "Geeft de komende, niet-geannuleerde activiteiten van Raak "
                "Millegem met datum, locatie, prijs-vanaf en of ze enkel voor "
                "leden zijn. Gebruik dit voor elke vraag over de agenda of "
                "wat er te doen is."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_activity_detail",
            "description": (
                "Geeft de details van één activiteit (datums, locatie, "
                "onderdelen en prijzen, opmerkingen). Geef het id terug dat je "
                "uit get_upcoming_activities kreeg."
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
                "Geeft de vraag, opmerking of het idee van de bezoeker door aan "
                "het bestuur via de IdeaBox. Gebruik dit wanneer je een vraag "
                "niet met zekerheid kan beantwoorden, of wanneer de bezoeker "
                "iets wil achterlaten. Vraag eerst naam (en optioneel e-mail "
                "voor een bevestiging)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Naam van de bezoeker."},
                    "content": {
                        "type": "string",
                        "description": "De vraag, opmerking of het idee.",
                    },
                    "email": {
                        "type": "string",
                        "description": "Optioneel e-mailadres voor een bevestiging.",
                    },
                },
                "required": ["name", "content"],
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
    """De uit een poster/reglement gelezen tekst (#206), of None.

    De tekst staat op het media-record (``media_assets.extracted_text``), niet op
    de activiteit — daar hoort ze thuis en het generaliseert naar reglementen."""
    q = db.query(MediaAsset).filter(MediaAsset.kind == kind)
    if activity_id is not None:
        q = q.filter(MediaAsset.activity_id == activity_id)
    if component_id is not None:
        q = q.filter(MediaAsset.component_id == component_id)
    asset = q.first()
    return asset.extracted_text if asset else None


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

def get_upcoming_activities(db: Session, limit: int = 20) -> dict[str, Any]:
    today = date.today()
    activity_ids = [
        row[0]
        for row in db.query(ActivityDate.activity_id)
        .filter(ActivityDate.start_date >= today)
        .distinct()
        .all()
    ]
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
    # Sorteer op eerstvolgende datum.
    items.sort(key=lambda x: (x["dates"][0]["start_date"] if x["dates"] else "9999"))
    return {"activities": items[:limit]}


def get_activity_detail(db: Session, activity_id: int) -> dict[str, Any]:
    a = db.query(Activity).filter(Activity.id == activity_id).first()
    if not a:
        return {"error": "Activiteit niet gevonden."}

    components = []
    for sub in a.sub_registrations:
        components.append(
            {
                "name": sub.name,
                "description": sub.description,
                "price": None if sub.is_free else _fmt_price(sub.price),
                "member_price": _fmt_price(sub.member_price),
                # Zachte info uit het reglement/info-document van dit onderdeel (#206).
                "info_text": _extracted_text(db, "component_info", component_id=sub.id),
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
        "notes": a.notes,
        # Zachte info uit de poster (#206); structuurvelden hierboven winnen altijd.
        "flyer_text": _extracted_text(db, "activity_poster", activity_id=a.id),
        "price_from": _price_from(a),
        "dates": _serialise_dates(a),
        "components": components,
    }


def submit_idea(
    db: Session, name: str, content: str, email: Optional[str] = None
) -> dict[str, Any]:
    """Hergebruikt exact het IdeaBox-schrijfpad (geen tweede schrijfweg)."""
    idea = Idea(submitter_name=name, submitter_email=email or None, content=content)
    db.add(idea)
    db.commit()
    db.refresh(idea)

    if email:
        try:
            send_idea_acknowledgement(to_email=email, name=name, message=content)
        except Exception as exc:  # mail mag de flow nooit breken
            logger.warning("Bevestigingsmail voor idee (chatbot) mislukt: %s", exc)

    return {
        "ok": True,
        "message": (
            "Je bericht is doorgegeven aan het bestuur."
            + (" Je krijgt een bevestiging per e-mail." if email else "")
        ),
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
        if name == "get_upcoming_activities":
            result = get_upcoming_activities(db)
        elif name == "get_activity_detail":
            result = get_activity_detail(db, activity_id=int(args.get("activity_id")))
        elif name == "submit_idea":
            result = submit_idea(
                db,
                name=str(args.get("name", "")).strip() or "Anoniem",
                content=str(args.get("content", "")).strip(),
                email=(args.get("email") or None),
            )
        else:  # pragma: no cover - door allowlist afgedekt
            result = {"error": "niet-geïmplementeerde tool"}
    except (TypeError, ValueError) as exc:
        return json.dumps({"error": f"Ongeldige parameters: {exc}"})

    return json.dumps(result, ensure_ascii=False, default=str)
