"""Raakje proposes for an activity: name, location, description, date and time (#1604).

Koen, 5 October 2026: "naam, locatie, omschrijving, datum/uur". Asked from the
Assistent's panel beside the fiche in edit mode; the answer is a proposal for
the form (`ui.form_proposal`, #1562). Nothing here writes to the activity: the
form takes the values on Toepassen and the fiche's one save stores them.

**Sources.** Koen's standing rule for every AI function: a fact without a
source is marked and left out by default. This proposer has two sources — what
the user asked in the panel, and what the record already holds — and three
kinds of field:

- *Name*: language, not a fact. Proposed as the model gives it.
- *Location, date and time*: facts. A location is proposed only when every
  word of it stands in a source. A date is proposed only when the model points
  at the passage it read it from (`date_source`) and that passage literally
  stands in a source: "volgende zaterdag" is a source, and the model resolves
  it against today; a date nobody gave has no passage to point at. What is
  refused is not proposed and is named (`Proposal.left_out`).
- *Description*: written from the name, the dates, the location and the
  components. Two layers mark a sentence, as the newsletter's proposer does
  (CR-05 §3.16): numbers, known names and removed contact details without a
  model, and a separate verification call for what no list can catch. A marked
  sentence is left out of the value unless the user ticks "klopt, behouden".

**The date row.** Dates are rows of the repeating group Datums. The proposal
addresses *the first row of the group* (`{"group": "d_order", "name":
"start_date"}`), never a row key: the first row is what the user sees first,
and a row added in the page has a key the server does not know. With no row at
all, `form-proposal.js` adds one on Toepassen. Other rows are never named, so
they cannot be touched. Each field carries the value the record's first date
held (its base), so a row changed in the meantime is skipped like any field.

**Names never leave.** The request and the record are scrubbed with the same
name list the seam guard scans against; a value that comes back with a
placeholder in it is refused, not proposed. The scrubber is the newsletter's
rule in ten lines (`newsletter.drafting.scrub`); a domain may not import
another domain's internals, so it stands here too until the kernel offers one.

No conversation is kept: one request, one proposal. A table for turns would be
a second thing to build, and the form shows what was taken.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, time
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.domains.activities.models import Activity, ActivityDate
from app.i18n import _, long_date

logger = logging.getLogger(__name__)

# The system prompt is a constant of this module, not stored content, so the
# guard need not scan it for names (CR-07's rule; proven by a test).
SCAN_PROMPT_NAMES = False
NAME_PLACEHOLDER = "[naam]"
#: The repeating group the dates live in — the `name` of `ui.repeating_group`.
DATE_GROUP = "d_order"
NAME_MAX = 255
DESCRIPTION_MAX = 2000
REPLY_MAX = 500
#: A passage shorter than this is no passage ("de", "op").
SOURCE_MIN = 3

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_NUMBER = re.compile(r"\d+(?:[.,:]\d+)*")
_SENTENCE = re.compile(r"[^.!?]*[.!?]+|[^.!?]+$")
_TIME = re.compile(r"^(\d{1,2}):(\d{2})$")

SYSTEM_PROMPT = """Je bent Raakje en je helpt het bestuur van een Vlaamse vereniging een activiteit in te vullen, in het Nederlands (België).

WAT JE DOET
- Je stelt waarden voor vier velden voor: de naam, de locatie, de omschrijving, en de datum met het uur. Je slaat niets op: de gebruiker beslist.
- Je hebt twee BRONNEN: de FICHE (wat er nu staat) en de VRAAG van de gebruiker. Feiten komen uitsluitend daaruit.

VASTE REGELS
- Stel een LOCATIE alleen voor als ze letterlijk in de vraag of in de fiche staat. Verzin geen zaal, straat of gemeente.
- Stel een DATUM of een UUR alleen voor als de vraag of de fiche die geeft. Geef dan in "date_source" het letterlijke stuk tekst waaruit je ze afleidt ("zaterdag 14 november om 14 uur", "volgende vrijdag"). Een datum die niemand gaf, laat je weg.
- Een relatieve datum ("volgende zaterdag") reken je uit tegenover VANDAAG.
- De OMSCHRIJVING is twee à drie zinnen voor bezoekers: warm en helder. Ze zegt alleen wat de vraag of de fiche zegt. Verzin geen programma, gerechten, prijzen, aantallen of namen van personen. Weglaten is altijd beter dan aanvullen.
- [naam] betekent dat er een naam weggehaald is: neem die nooit over en raad nooit wie het was.
- Laat een veld WEG uit je antwoord als je er niets voor hebt of als de gebruiker er niet om vraagt. Zeg in "reply" kort wat je nog nodig hebt.

ANTWOORD
Antwoord met één JSON-object en niets anders:
{"reply": "één korte zin voor de gebruiker", "name": "…", "location": "…", "description": "…", "date": {"start_date": "JJJJ-MM-DD", "start_time": "UU:MM", "end_date": "JJJJ-MM-DD", "end_time": "UU:MM"}, "date_source": "letterlijk stuk uit de vraag of de fiche"}
Elke sleutel behalve "reply" is optioneel, ook binnen "date".
"""

VERIFY_PROMPT = """Je controleert een voorgestelde omschrijving van een activiteit tegen de BRONNEN. Je schrijft zelf niets bij.

Zoek elke feitelijke bewering: wat er te doen is, wie wat doet, hoeveel iets kost, hoeveel er zijn, wanneer of waar iets is.
Een bewering is GESTAAFD als een bron ze zegt. Enthousiaste taal ("een avond om niet te missen") is geen feit.

Antwoord met één JSON-object: {"unsupported": [{"sentence": N, "reason": "korte reden in het Nederlands"}]}
Een lege lijst betekent: alles is gestaafd.
"""


class ProposerError(RuntimeError):
    """Raakje could not make a proposal. The message is for the screen."""


@dataclass
class Proposal:
    """What one request produced, ready for `ui.form_proposal`.

    `fields` are the kit's proposed fields; `marks` the sentences of the
    description that have no source (`id`, `sentence`, `reason`); `left_out`
    the lines that say which fact was not proposed and why."""

    reply: str
    fields: list[dict[str, Any]] = field(default_factory=list)
    marks: list[dict[str, Any]] = field(default_factory=list)
    left_out: list[str] = field(default_factory=list)
    unverified: bool = False


# ── Names ────────────────────────────────────────────────────────────────────


def scrub(text: str, names: set[str]) -> str:
    """Contact details and every known name part go before anything leaves."""
    from app.domains.chatbot.api import redact

    text = redact(text or "")
    if not text or not names:
        return text

    def replace(match: re.Match[str]) -> str:
        word = match.group(0)
        return NAME_PLACEHOLDER if len(word) >= 3 and word.lower() in names else word

    return _WORD.sub(replace, text)


def _carries_placeholder(text: str) -> bool:
    from app.domains.chatbot.api import REDACTION_PLACEHOLDERS

    return any(p in text for p in (NAME_PLACEHOLDER, *REDACTION_PLACEHOLDERS))


# ── The record as a source ───────────────────────────────────────────────────


def _hhmm(value: Optional[time]) -> str:
    return value.strftime("%H:%M") if value else ""


def _iso(value: Optional[date]) -> str:
    return value.isoformat() if value else ""


def first_date(activity: Activity) -> Optional[ActivityDate]:
    """The date row the fiche shows first: the earliest (`_aa_detail.html`
    sorts the same way), or None."""
    rows = sorted(activity.dates, key=lambda d: d.start_date)
    return rows[0] if rows else None


def _money(value: Any) -> str:
    return f"€ {value:.2f}".replace(".", ",")


def record_text(activity: Activity) -> str:
    """The activity as the model reads it. The internal note is not in it: it
    is the board's own and never reaches a text for visitors."""
    lines = [
        f"Naam: {activity.name}",
        f"Locatie: {activity.location or '(leeg)'}",
        f"Omschrijving: {activity.description or '(leeg)'}",
    ]
    dates = []
    for d in sorted(activity.dates, key=lambda d: d.start_date):
        text = f"{_iso(d.start_date)} ({long_date(d.start_date)})"
        if d.end_date and d.end_date != d.start_date:
            text += f" tot {_iso(d.end_date)} ({long_date(d.end_date)})"
        if d.start_time:
            text += f", {_hhmm(d.start_time)}"
            if d.end_time:
                text += f"–{_hhmm(d.end_time)}"
        dates.append(text)
    lines.append("Datums: " + ("; ".join(dates) if dates else "(geen)"))
    for component in activity.sub_registrations:
        text = f"Onderdeel: {component.name}"
        if component.description:
            text += f" — {component.description}"
        if component.price:
            text += f" ({_money(component.price)})"
        products = [
            p.name + ("" if p.is_free or p.pay_on_site or not p.price else f" {_money(p.price)}")
            for p in component.products
        ]
        if products:
            text += ": " + ", ".join(products)
        lines.append(text)
    return "\n".join(lines)


# ── What a source holds ──────────────────────────────────────────────────────


def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def _stands_in(passage: str, sources: str) -> bool:
    """Does `passage` literally stand in the sources (case and spacing aside)?"""
    passage = _plain(passage).strip(" .,;:!?\"'“”‘’")
    return len(passage) >= SOURCE_MIN and passage in _plain(sources)


def _every_word_stands_in(value: str, sources: str) -> bool:
    known = set(_TOKEN.findall(_plain(sources)))
    words = _TOKEN.findall(_plain(value))
    return bool(words) and all(word in known for word in words)


def _parse_json(text: str) -> dict[str, Any]:
    start, end = (text or "").find("{"), (text or "").rfind("}")
    unusable = _("Raakje gaf geen bruikbaar voorstel. Probeer het opnieuw.")
    if start < 0 or end <= start:
        raise ProposerError(unusable)
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ProposerError(unusable) from exc
    if not isinstance(data, dict):
        raise ProposerError(unusable)
    return data


def _text(data: dict[str, Any], key: str, limit: int) -> str:
    value = data.get(key)
    return value.strip()[:limit] if isinstance(value, str) else ""


def _date(raw: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(raw).strip()) if raw else None
    except ValueError:
        return None


def _time(raw: Any) -> Optional[time]:
    match = _TIME.match(str(raw).strip()) if raw else None
    if not match:
        return None
    hour, minute = int(match.group(1)), int(match.group(2))
    return time(hour, minute) if hour < 24 and minute < 60 else None


# ── The fields ───────────────────────────────────────────────────────────────


def _field(name: str, label: str, value: str, base: str, **more: Any) -> dict[str, Any]:
    """One proposed field of the kit, plus `shown`: how the panel reads the
    value to the user before Toepassen (a date in words, not as the control
    stores it)."""
    return {"name": name, "label": label, "value": value, "base": base, "shown": value, **more}


def _date_fields(
    data: dict[str, Any], activity: Activity, sources: str, left_out: list[str]
) -> tuple[list[dict[str, Any]], str]:
    """The proposed fields of the first date row, and the accepted date as text
    (a source for the description's numbers)."""
    asked = data.get("date")
    if not isinstance(asked, dict) or not any(asked.values()):
        return [], ""
    if not _stands_in(str(data.get("date_source") or ""), sources):
        left_out.append(
            _("Datum en uur: niet voorgesteld — ze staan niet in je vraag en niet in de fiche.")
        )
        return [], ""
    row = first_date(activity)
    start, end = _date(asked.get("start_date")), _date(asked.get("end_date"))
    begins, ends = _time(asked.get("start_time")), _time(asked.get("end_time"))
    if start is None and row is None:
        left_out.append(_("Datum en uur: niet voorgesteld — een uur zonder dag is geen datum."))
        return [], ""
    day = start or (row.start_date if row else None)
    if end is not None and day is not None and end < day:
        end = None
    wanted = (
        ("start_date", _("Datum"), _iso(start), _iso(row.start_date) if row else ""),
        ("start_time", _("Van"), _hhmm(begins), _hhmm(row.start_time) if row else ""),
        ("end_date", _("Einddatum"), _iso(end), _iso(row.end_date) if row else ""),
        ("end_time", _("Tot"), _hhmm(ends), _hhmm(row.end_time) if row else ""),
    )
    words = {_iso(start): long_date(start), _iso(end): long_date(end)}
    fields = [
        _field(name, label, value, base, group=DATE_GROUP) | {"shown": words.get(value, value)}
        for name, label, value, base in wanted
        if value and value != base
    ]
    accepted = " ".join(
        part for value in (start, end) if value for part in (_iso(value), long_date(value))
    )
    for value in (begins, ends):
        if value:
            accepted += f" {_hhmm(value)} {value.hour} {value.minute:02d} {value.hour}u{value.minute:02d} {value.hour}.{value.minute:02d}"
    return fields, accepted


def _own_marks(sentence: str, facts: str, names: set[str]) -> str:
    """Why this sentence has no source, without a model; "" when it has."""
    known = set(_NUMBER.findall(facts))
    for number in _NUMBER.findall(sentence):
        if number not in known:
            return _("dit getal staat in geen enkele bron")
    for word in _WORD.findall(sentence):
        if len(word) >= 3 and word.lower() in names:
            return _("dit is een naam uit de ledenadministratie")
    if _carries_placeholder(sentence):
        return _("hier stond een weggehaalde naam of een weggehaald contactgegeven")
    return ""


def _verify(provider: Any, sentences: list[str], sources: str, names: set[str]) -> dict[int, str]:
    """The verification call: which sentences state something no source holds.
    Raises on a failed call — the caller says the proposal was not checked."""
    listing = "\n".join(f"{i}. {scrub(s, names)}" for i, s in enumerate(sentences, 1))
    reply = provider.complete(
        [
            {"role": "system", "content": VERIFY_PROMPT},
            {
                "role": "user",
                "content": f"BRONNEN\n{sources}\n\nOMSCHRIJVING (zinnen genummerd)\n{listing}",
            },
        ],
        tools=None,
    )
    found: dict[int, str] = {}
    for item in _parse_json(reply.content or "").get("unsupported") or []:
        if not isinstance(item, dict):
            continue
        try:
            index = int(str(item.get("sentence"))) - 1
        except (TypeError, ValueError):
            continue
        if 0 <= index < len(sentences):
            found[index] = str(item.get("reason") or _("staat in geen enkele bron"))[:200]
    return found


def _provider(db: Session, actor: str) -> Any:
    from app.config import settings
    from app.domains.chatbot.api import (
        AiCapability,
        GuardedProvider,
        admin_rules,
        get_provider,
        sink_for,
    )
    from app.domains.mdm.api import person_name_parts

    # A code of its own (migration 197), so the cost screen shows what the
    # proposer costs and not a larger newsletter. Imported here: the chatbot's
    # tools import this domain's facade, so the module level would be a circle.
    return GuardedProvider(
        get_provider(settings.admin_chat_model),
        admin_rules(
            lambda: person_name_parts(db),
            capability=AiCapability.ACTIVITY_DRAFTING,
            scan_prompt_names=SCAN_PROMPT_NAMES,
        ),
        sink_for(actor),
    )


def propose(
    db: Session, activity: Activity, *, request: str, actor: str, today: Optional[date] = None
) -> Proposal:
    """One request to Raakje about this activity.

    Raises `ProposerError` for an answer that cannot be used, and lets the
    kernel's `SeamBlocked` through for the screen."""
    from app.domains.chatbot.api import SeamBlocked
    from app.domains.mdm.api import person_name_parts

    request = (request or "").strip()
    if not request:
        raise ProposerError(_("Zeg wat Raakje moet voorstellen."))
    names = person_name_parts(db)
    today = today or date.today()
    asked = scrub(request, names)
    record = scrub(record_text(activity), names)
    sources = f"FICHE\n{record}\n\nVRAAG\n{asked}"
    provider = _provider(db, actor)
    answer = provider.complete(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"VANDAAG: {today.isoformat()} ({long_date(today)})\n\n{sources}",
            },
        ],
        tools=None,
    )
    data = _parse_json(answer.content or "")
    proposal = Proposal(reply=_text(data, "reply", REPLY_MAX))

    name = _text(data, "name", NAME_MAX)
    if name and _carries_placeholder(name):
        proposal.left_out.append(_("Naam: niet voorgesteld — er stond een weggehaalde naam in."))
    elif name and name != (activity.name or ""):
        proposal.fields.append(_field("name", _("Naam"), name, activity.name or ""))

    location = _text(data, "location", 255)
    if location and location != (activity.location or ""):
        if _carries_placeholder(location) or not _every_word_stands_in(location, sources):
            proposal.left_out.append(
                _("Locatie: niet voorgesteld — ze staat niet in je vraag en niet in de fiche.")
            )
        else:
            proposal.fields.append(
                _field("location", _("Locatie"), location, activity.location or "")
            )

    date_fields, accepted = _date_fields(data, activity, sources, proposal.left_out)

    description = _text(data, "description", DESCRIPTION_MAX)
    if description and description != (activity.description or ""):
        sentences = [s.strip() for s in _SENTENCE.findall(description) if s.strip()]
        facts = f"{sources} {accepted}"
        reasons = {i: why for i, s in enumerate(sentences) if (why := _own_marks(s, facts, names))}
        try:
            for index, why in _verify(provider, sentences, f"{sources}\n{accepted}", names).items():
                reasons.setdefault(index, why)
        except SeamBlocked:
            raise
        except Exception as exc:  # noqa: BLE001 — an unchecked proposal must say so
            logger.warning("Verification of the activity proposal failed: %s", exc)
            proposal.unverified = True
        parts = [
            {"text": s, "mark": (i + 1 if i in reasons else None)} for i, s in enumerate(sentences)
        ]
        kept = " ".join(p["text"] for p in parts if p["mark"] is None)
        proposal.marks = [
            {"id": i + 1, "sentence": sentences[i], "reason": reasons[i]} for i in sorted(reasons)
        ]
        if kept:
            more = {"parts": parts} if proposal.marks else {}
            proposal.fields.append(
                _field("description", _("Omschrijving"), kept, activity.description or "", **more)
            )
        else:
            # Nothing of it has a source: no field, and no tick — a proposal
            # must not empty a description that is there.
            proposal.marks = []
            proposal.left_out.append(
                _("Omschrijving: niet voorgesteld — geen enkele zin heeft een bron.")
            )
    proposal.fields.extend(date_fields)
    return proposal
