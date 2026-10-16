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

from app.domains.activities.api import Activity, ActivityDate, publicly_bookable_products
from app.domains.chatbot.models import ChatbotInfo
from app.domains.media.api import MediaAsset

logger = logging.getLogger(__name__)

# --- Allowlist: de enige tools die de bot mag aanroepen ----------------------

TOOL_SPECS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_activities",
            "description": (
                "Geeft activiteiten van Raak Millegem met datum, locatie, "
                "prijs-vanaf, of ze enkel voor leden zijn en of ze geannuleerd is "
                "(cancelled: zeg dat dan). Standaard de komende activiteiten "
                "(when='upcoming'); zet when='past' "
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
                "onderdelen en prijzen, opmerkingen, en of ze geannuleerd is — "
                "cancelled: zeg dat dan). Geef het id terug dat je "
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

# Het veldcontract van de publieke bot (CR-07 §5.1, CR-33 phase 2). De allowlist hierboven zegt
# WELKE tools mogen draaien; dit zegt WELKE VELDEN hun antwoord mag bevatten — want een
# tool-resultaat gaat integraal naar Mistral. Een veld dat aan een serialiser wordt toegevoegd
# zonder dat het hier staat, is een nieuwe export naar een derde partij; die mag geen stille
# wijziging zijn maar een rode build (`test_public_tool_field_contract.py`).
#
# Dit is GEEN tweede lijst naast het register van gegevens: of een veld mag reizen, beslist het
# register. Elk veld noemt hier de sleutel(s) van het register waaruit het komt, en de poort
# `test_public_tool_field_contract.py` eist dat elke genoemde sleutel `publiek` is. Een veld
# dat uit een niet-publiek gegeven komt, kan hier dus niet staan zonder dat het register eerst
# anders beslist heeft. `STRUCTURE` is voor wat geen opgeslagen gegeven is: de vorm van het
# antwoord (een lijst, een uitkomst, een foutmelding) en het nummer van de pagina zelf.
# Sleutels van het contract zijn paden: "" is de wortel, "x[]" is één element van lijst x.
STRUCTURE: tuple[str, ...] = ()
#: The ONLY names a field may carry `STRUCTURE` under: the shape of an answer and the number of
#: the page itself. A field with any other name must name a register entry
#: (`test_public_tool_field_contract.py` refuses it otherwise): `"organiser": STRUCTURE` is no way
#: to skip the register.
STRUCTURAL_NAMES: frozenset[str] = frozenset(
    {"id", "when", "activities", "dates", "components", "products", "error", "ok", "message"}
)

_ACTIVITY = "activities.activity."
_DATE = "activities.activity_date."
_COMPONENT = "activities.activity_sub_registration."
_PRODUCT = "activities.activity_product."
#: The text read from a poster or a regulation (#206): what the person who uploaded it let the
#: bot read — the text as read, the replacement and the addition (Koen's word: it may carry the
#: contact details of the poster).
_INFO_TEXT = (
    "chatbot.chatbot_info.extracted_text",
    "chatbot.chatbot_info.text_override",
    "chatbot.chatbot_info.text_addition",
)
_DATE_FIELDS: dict[str, tuple[str, ...]] = {
    "start_date": (_DATE + "start_date",),
    "end_date": (_DATE + "end_date",),
    "start_time": (_DATE + "start_time",),
    "end_time": (_DATE + "end_time",),
}
_PRICE_FROM = (
    _COMPONENT + "price",
    _PRODUCT + "price",
    _COMPONENT + "is_free",
    _PRODUCT + "is_free",
)

PUBLIC_FIELD_CONTRACT: dict[str, dict[str, dict[str, tuple[str, ...]]]] = {
    "get_activities": {
        "": {"when": STRUCTURE, "activities": STRUCTURE},
        "activities[]": {
            "id": STRUCTURE,
            "name": (_ACTIVITY + "name",),
            "location": (_ACTIVITY + "location",),
            "members_only": (_ACTIVITY + "members_only",),
            "cancelled": (_ACTIVITY + "is_cancelled",),
            "price_from": _PRICE_FROM,
            "dates": STRUCTURE,
        },
        "activities[].dates[]": _DATE_FIELDS,
    },
    "get_activity_detail": {
        # Twee vormen: de gevonden activiteit, of de nette weigering.
        "": {
            "id": STRUCTURE,
            "name": (_ACTIVITY + "name",),
            "location": (_ACTIVITY + "location",),
            "members_only": (_ACTIVITY + "members_only",),
            "cancelled": (_ACTIVITY + "is_cancelled",),
            "description": (_ACTIVITY + "description",),
            "flyer_text": _INFO_TEXT,
            "price_from": _PRICE_FROM,
            "dates": STRUCTURE,
            "components": STRUCTURE,
            "error": STRUCTURE,
        },
        "dates[]": _DATE_FIELDS,
        "components[]": {
            "name": (_COMPONENT + "name",),
            "description": (_COMPONENT + "description",),
            "price": (_COMPONENT + "price", _COMPONENT + "is_free"),
            "member_price": (_COMPONENT + "member_price",),
            "info_text": _INFO_TEXT,
            "products": STRUCTURE,
        },
        "components[].products[]": {
            "name": (_PRODUCT + "name",),
            "price": (_PRODUCT + "price", _PRODUCT + "is_free"),
            "member_price": (_PRODUCT + "member_price",),
        },
    },
    # Bewust geen bezoekersgegevens terug: wat de bezoeker instuurde komt niet in
    # het antwoord, dus het model krijgt naam en e-mail niet nog eens voorgeschoteld.
    "submit_idea": {"": {"ok": STRUCTURE, "message": STRUCTURE, "error": STRUCTURE}},
}


def declared_fields(tool: str, path: str) -> set[str]:
    """The names a tool's answer may carry at `path` (empty when the path is not declared)."""
    return set(PUBLIC_FIELD_CONTRACT.get(tool, {}).get(path, {}))


# --- Helpers -----------------------------------------------------------------


def _fmt_price(value: Optional[Decimal]) -> Optional[str]:
    if value is None:
        return None
    return f"{Decimal(value):.2f}"


def _price_from(activity: Activity) -> Optional[str]:
    """Laagste niet-gratis prijs over onderdelen en producten, of None (gratis).

    #2055: only the products a visitor may pick count — the public form's own
    selection (`publicly_bookable_products`), not a second filter here."""
    prices: list[Decimal] = []
    for sub in activity.sub_registrations:
        if not sub.is_free and sub.price is not None:
            prices.append(Decimal(sub.price))
        for product in publicly_bookable_products(sub):
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
    from app.domains.activities.api import published_only

    # #1428: a draft is not public, so Raakje does not know it either.
    activities = (
        db.query(Activity)
        .filter(
            Activity.id.in_(activity_ids),
            published_only(),
        )
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
                # #2055: as the public list shows it — "Geannuleerd" (Koen, "1a").
                "cancelled": a.is_cancelled,
                "price_from": _price_from(a),
                "dates": _serialise_dates(a),
            }
        )
    # Komend: eerstvolgende eerst. Verleden: meest recent eerst.
    fallback = "0000" if is_past else "9999"
    items.sort(
        key=lambda x: x["dates"][0]["start_date"] if x["dates"] else fallback,
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
    from app.domains.activities.api import published_only

    # #1428: a draft is "not found" for the chatbot, as it is for a visitor.
    a = db.query(Activity).filter(Activity.id == activity_id, published_only()).first()
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
                    # #2055: what the public form offers, nothing the board
                    # keeps for itself (an inactive product is its guest list).
                    for p in publicly_bookable_products(sub)
                ],
            }
        )

    return {
        "id": a.id,
        "name": a.name,
        "location": a.location,
        "members_only": a.members_only,
        # #2055: the public page shows a cancelled activity as "Geannuleerd";
        # the assistant says so too, instead of answering as if it took place.
        "cancelled": a.is_cancelled,
        # #1028: de publieke omschrijving (#1016) — de twee, drie zinnen die ook op
        # de activiteitenpagina staan. Bewust toegevoegd: Raakje beantwoordde
        # "waar gaat dit over?" tot nu met de affichetekst, terwijl de bestuurder
        # net een zin schreef voor precies die vraag. Hier stond `notes`, en dat
        # was een lek: die kolom leest als een interne nota en ging integraal naar
        # het model. Ze is weg (migratie 137).
        "description": _text_or_unspecified(a.description),
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
    # Asked of forms through its port (CR-13 phase 4d, #1251). The chatbot has no
    # form a visitor loaded, so no honeypot and no signed time (#1297): the port's
    # handler trusts the caller, whose own limits (per-IP budget, the tool
    # dispatch) apply.
    from app.kernel.contracts.forms import SubmitMessage
    from app.kernel.ports import call

    # No commit here: forms no longer commits behind its port, and a tool is no
    # door — the chat's door commits (`chatbot/ui.py`), whatever the rest of the
    # conversation does.
    submitted = call(SubmitMessage(name=name, email=email, message=content), db)
    if submitted.submission_id is None:
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

    return [
        copy.deepcopy(spec) for spec in TOOL_SPECS if spec["function"]["name"] in READ_ONLY_TOOLS
    ]


def execute_read_tool(name: str, arguments: dict[str, Any], db: Session) -> str:
    """Een leestool uitvoeren. Weigert alles wat niet enkel leest, bij naam."""
    if name not in READ_ONLY_TOOLS:
        logger.warning("Leestool gevraagd die niet enkel leest: %s", name)
        return json.dumps({"error": f"Niet toegelaten in deze modus: {name}."})
    return execute_tool(name, arguments, db)
