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
- *Location, day and hour*: facts, each grounded on its own (#1650). A
  location is proposed only when every word of it stands in a source. A day is
  proposed only when the model points at the passage it read it from
  (`date_source`), that passage says a day and its words stand in a source:
  "volgende zaterdag" is a source, and the model resolves it against today. An
  hour is proposed when its number stands in a source, spoken or written
  ("10 uur in de voormiddag", "half drie", "14u") — with or without a day.
  What is refused is not proposed and is named, part by part
  (`Proposal.left_out`).
- *Description*: written from the name, the dates, the location and the
  components. Two layers mark a sentence, as the newsletter's proposer does
  (CR-05 §3.16): numbers, known names and removed contact details without a
  model, and a separate verification call for what no list can catch. A marked
  sentence is left out of the value unless the user ticks "klopt, behouden".
  **The request is a source here too** (#1653): the verification's verdict
  holds only when the sentence carries a word or a number nobody gave, so a
  sentence that only rewords what the user gave is never marked. What counts
  as given is bounded (`given_facts`): not the part of the request that tells
  Raakje what to write.

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
- Een DAG en een UUR zijn twee aparte feiten. Geeft de vraag alleen een uur ("van 10 tot 12", "10 uur in de voormiddag", "12 uur 's middags", "half drie", "14u"), geef dan alleen "start_time" en/of "end_time" en laat "start_date" weg: het uur komt bij de datum die er al staat. "van X tot Y" is start_time X en end_time Y; "tot Y" alleen is end_time. Geeft de vraag alleen een dag, geef dan alleen "start_date".
- Vraagt de gebruiker iets over de datum of het uur, antwoord dan in "reply" daarover; begin niet over de naam of de omschrijving.
- Stel een DATUM of een UUR alleen voor als de vraag of de fiche die geeft. Geef voor een DAG in "date_source" het letterlijke stuk tekst waaruit je hem afleidt ("zaterdag 14 november", "volgende vrijdag"). Een dag of een uur dat niemand gaf, laat je weg.
- Een relatieve datum ("volgende zaterdag") reken je uit tegenover VANDAAG.
- De OMSCHRIJVING is twee à drie zinnen voor bezoekers: warm en helder. Schrijf ze EERST uit de feiten die de vraag of de fiche geeft — wat er te doen is, waar, wanneer, van waar en hoe laat je vertrekt — in je eigen woorden. Ze zegt alleen wat de vraag of de fiche zegt. Verzin geen programma, gerechten, prijzen, aantallen of namen van personen. Weglaten is altijd beter dan aanvullen.
- [naam] betekent dat er een naam weggehaald is: neem die nooit over en raad nooit wie het was.
- Laat een veld WEG uit je antwoord als je er niets voor hebt of als de gebruiker er niet om vraagt. Zeg in "reply" kort wat je nog nodig hebt.

ANTWOORD
Antwoord met één JSON-object en niets anders:
{"reply": "één korte zin voor de gebruiker", "name": "…", "location": "…", "description": "…", "date": {"start_date": "JJJJ-MM-DD", "start_time": "UU:MM", "end_date": "JJJJ-MM-DD", "end_time": "UU:MM"}, "date_source": "letterlijk stuk uit de vraag of de fiche"}
Elke sleutel behalve "reply" is optioneel, ook binnen "date".
"""

VERIFY_PROMPT = """Je controleert een voorgestelde omschrijving van een activiteit tegen de BRONNEN. Je schrijft zelf niets bij.

Er zijn TWEE bronnen, en ze tellen allebei: DE FICHE (wat er al staat) en WAT DE GEBRUIKER SCHREEF. Ook wat de gebruiker in zijn bericht schreef is een bron, ook als de fiche leeg is.

Zoek elke feitelijke bewering: wat er te doen is, wie wat doet, hoeveel iets kost, hoeveel er zijn, wanneer of waar iets is.
Een bewering is GESTAAFD als een van de twee bronnen ze zegt — ook in andere woorden of in een andere volgorde. "We vertrekken om 9 uur aan het plein" is gestaafd door "vertrek aan het plein, 9 uur".
Enthousiaste taal ("een avond om niet te missen", "ga je mee?") is geen feit en markeer je niet.
NIET gestaafd is alleen wat erbij verzonnen is: iets wat geen van de twee bronnen zegt.

Antwoord met één JSON-object: {"unsupported": [{"sentence": N, "reason": "korte reden in het Nederlands, met het stukje uit de zin dat in geen bron staat"}]}
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


# ── Days and hours: two facts, each with its own source (#1650) ─────────────

_NUMBER_WORDS = {
    "een": 1, "één": 1, "twee": 2, "drie": 3, "vier": 4, "vijf": 5, "zes": 6,
    "zeven": 7, "acht": 8, "negen": 9, "tien": 10, "elf": 11, "twaalf": 12,
}  # fmt: skip
_N = r"(\d{1,2}|" + "|".join(_NUMBER_WORDS) + r")"
_MONTHS = "januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december"
#: "10:30", "10.30", "14u", "14u30", "10 uur", "10 uur 30", "tien uur".
_CLOCK = re.compile(
    rf"(?<![\w:.]){_N}\s*(?:[:.]\s*(\d{{2}})(?!\d)|(?:uur|u|h)(?![a-z])\s*(\d{{2}})?)", re.I
)
#: "half drie" is 2:30.
_HALF = re.compile(rf"\bhalf\s+{_N}\b", re.I)
#: "kwart over drie", "kwart voor drie".
_QUARTER = re.compile(rf"\bkwart\s+(over|voor)\s+{_N}\b", re.I)
#: "van 10 tot 12", "om 10": a bare number after one of these is an hour —
#: unless a month follows ("tot 12 november").
_BARE = re.compile(
    rf"\b(?:om|van|tot|vanaf|rond|tegen)\s+{_N}\b(?!\s*(?:uur|u\b|h\b|{_MONTHS}))(?![:.]\d)", re.I
)
#: Words that make a passage a passage about a DAY.
_DAY_WORDS = frozenset(
    "vandaag morgen overmorgen maandag dinsdag woensdag donderdag vrijdag zaterdag zondag "
    "week weekend volgende komende eerstvolgende".split()
) | frozenset(_MONTHS.split("|"))


def _number(raw: str) -> int:
    return _NUMBER_WORDS.get(raw.lower()) or int(raw) if not raw.isdigit() else int(raw)


def hours_in(text: str) -> tuple[set[time], list[str]]:
    """The clock times a text gives, and the words it gives them in.

    A spoken hour is a source for its clock time: "10 uur in de voormiddag",
    "12 uur 's middags", "half drie", "14u", "van 10 tot 12". An hour up to
    twelve is read both ways — "3 uur" grounds 03:00 and 15:00 — because the
    part of the day is the model's to read ("in de namiddag"); what this rule
    guards is that the NUMBER was given, not that it was read well."""
    found: set[time] = set()
    words: list[str] = []

    def take(hour: int, minute: int, said: str) -> None:
        if not (0 <= hour <= 24 and 0 <= minute < 60):
            return
        hour %= 24
        found.add(time(hour, minute))
        if 1 <= hour <= 11:
            found.add(time(hour + 12, minute))
        elif hour == 12:
            found.add(time(0, minute))
        if said.strip() not in words:
            words.append(said.strip())

    text = text or ""
    for m in _CLOCK.finditer(text):
        take(_number(m.group(1)), int(m.group(2) or m.group(3) or 0), m.group(0))
    for m in _HALF.finditer(text):
        take((_number(m.group(1)) - 1) or 12, 30, m.group(0))
    for m in _QUARTER.finditer(text):
        hour = _number(m.group(2))
        if m.group(1).lower() == "over":
            take(hour, 15, m.group(0))
        else:
            take((hour - 1) or 12, 45, m.group(0))
    for m in _BARE.finditer(text):
        take(_number(m.group(1)), 0, m.group(0))
    return found, words


def _day_stands(passage: str, day: date, sources: str) -> bool:
    """Is `passage` a passage about a day, and do its words stand in a source?

    Word by word, not as one literal stretch (#1650): the model shortens what
    it quotes ("zaterdag 14 november" from "op zaterdag de 14e november"), and
    one dropped word refused everything. It must still SAY a day — a weekday, a
    month, "morgen", "volgende week", or the day's own number — so an hour
    cannot pass for one."""
    tokens = _TOKEN.findall(_plain(passage))
    if not tokens or not _every_word_stands_in(passage, sources):
        return False
    return any(token in _DAY_WORDS for token in tokens) or str(day.day) in tokens


def _date_fields(
    data: dict[str, Any], activity: Activity, sources: str, asked: str, left_out: list[str]
) -> tuple[list[dict[str, Any]], str]:
    """The proposed fields of the first date row, and what was accepted as text
    (a source for the description's numbers).

    **A day and an hour are separate facts** (#1650; Koen, 6 October 2026: he
    asked for other hours and was told "date and time" stood nowhere). Each is
    grounded on its own and refused on its own:

    - an hour is given when its number stands in the request or the record
      (`hours_in`) — also without a day: it goes on the first date row, or on a
      new row when there is none, and then the panel says the day is missing;
    - a day is given when the passage the model points at says a day and its
      words stand in a source (`_day_stands`).

    `asked` is the request alone: an hour that stands there and was neither
    proposed nor refused is named too, so the panel never answers a question
    about hours with silence."""
    answer = data.get("date")
    answer = answer if isinstance(answer, dict) else {}
    row = first_date(activity)
    passage = str(data.get("date_source") or "")
    given, _words = hours_in(sources)
    not_given = _("niet voorgesteld — staat niet in je vraag en niet in de fiche.")

    days: dict[str, Optional[date]] = {}
    for name, label in (("start_date", _("Datum")), ("end_date", _("Einddatum"))):
        day = _date(answer.get(name))
        if day is not None and not _day_stands(passage, day, sources):
            if _iso(day) != (_iso(getattr(row, name)) if row else ""):
                left_out.append(f"{label} ({long_date(day)}): {not_given}")
            day = None
        days[name] = day
    hours: dict[str, Optional[time]] = {}
    for name, label in (("start_time", _("Van")), ("end_time", _("Tot"))):
        hour = _time(answer.get(name))
        if hour is not None and hour not in given:
            left_out.append(f"{label} ({_hhmm(hour)}): {not_given}")
            hour = None
        hours[name] = hour

    start, end = days["start_date"], days["end_date"]
    first = start or (row.start_date if row else None)
    if end is not None and first is not None and end < first:
        end = None
    wanted = (
        ("start_date", _("Datum"), _iso(start), _iso(row.start_date) if row else ""),
        ("start_time", _("Van"), _hhmm(hours["start_time"]), _hhmm(row.start_time) if row else ""),
        ("end_date", _("Einddatum"), _iso(end), _iso(row.end_date) if row else ""),
        ("end_time", _("Tot"), _hhmm(hours["end_time"]), _hhmm(row.end_time) if row else ""),
    )
    words = {_iso(start): long_date(start), _iso(end): long_date(end)}
    fields = [
        _field(name, label, value, base, group=DATE_GROUP) | {"shown": words.get(value, value)}
        for name, label, value, base in wanted
        if value and value != base
    ]
    if fields and row is None and start is None:
        # Hours without a day on a record without a date: they go on a new row,
        # and the day is still the user's to give.
        left_out.append(
            _("De dag ontbreekt nog: het uur komt op een nieuwe datumrij, vul de datum zelf in.")
        )
    said_hours = hours_in(asked)[1]
    if said_hours and not any(hours.values()) and not any(_time(answer.get(n)) for n in hours):
        # The request gives an hour and the model proposed none: say so, with
        # the words it was given in, instead of answering about something else.
        left_out.append(
            _(
                "Uur: niet voorgesteld — Raakje las “%(said)s” in je vraag niet als begin- of einduur. Zeg het korter, bijvoorbeeld “van 10 tot 12 uur”."
            )
            % {"said": ", ".join(said_hours[:3])}
        )
    accepted = " ".join(
        part for value in (start, end) if value for part in (_iso(value), long_date(value))
    )
    for value in hours.values():
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


#: Words that carry no fact: little words, and the plainest verbs a sentence is
#: reworded with ("we trekken naar", "ga je mee", "het is aan"). A sentence made
#: of these and of given words adds nothing of its own.
_FILLER = frozenset(
    "aan achter alle allemaal als bij daar daarna dan dat deze die dit door een eens en er "
    "graag haar hebben heeft hem het hier hij hun iedereen ieder iets ik in is je jij jou "
    "jouw jullie kan kom komen komt kunnen maar mee met mijn naar niet nog of om onder ons "
    "onze ook op over samen te tot uit van veel voor waar wat we weer welkom wel wij wil "
    "willen worden wordt zal zich zij zijn zo zullen ga gaan gaat trek trekt trekken doe "
    "doen doet".split()
)
#: Words that make a part of the request an INSTRUCTION to Raakje and not a
#: fact about the activity: "schrijf je een leuke tekst als omschrijving?".
_INSTRUCTION = frozenset(
    "schrijf schrijven schrijft maak bedenk verzin formuleer stel voorstel voorstellen "
    "tekst tekstje omschrijving beschrijving naam titel".split()
)
#: Where one part of the request ends and the next begins.
_CLAUSE = re.compile(r"[.!?;:,\n]+|\s+(?:en|maar|dus|want)\s+")
_LABEL = re.compile(r"^(?:Naam|Locatie|Omschrijving|Datums|Onderdeel): ?", re.M)


def _stem(word: str) -> str:
    """A word as the comparison reads it: its first five letters when it is
    longer — "vertrekken" and "vertrek", "wandeling" and "wandelen" are one."""
    return word[:5] if len(word) > 5 else word


def given_facts(record: str, asked: str, accepted: str) -> str:
    """What was GIVEN about the activity — the only thing a claim can lean on
    (#1653, bounded on the master CLI's review, 6 October 2026).

    Not everything that stands in the sources is a fact someone gave: the
    labels of the record are ours, and a part of the request that tells Raakje
    what to do ("schrijf een leuke tekst als omschrijving") says nothing about
    the activity — so "een leuke tekst" grounds no sentence that calls the
    outing "leuk". Such a part is left out, by its words (`_INSTRUCTION`); the
    rest of the same request stays."""
    clauses = [c for c in _CLAUSE.split(asked or "") if c and c.strip()]
    facts = [c for c in clauses if not (set(_TOKEN.findall(_plain(c))) & _INSTRUCTION)]
    values = _LABEL.sub("", record or "").replace("(leeg)", " ").replace("(geen)", " ")
    return " ".join([values, *facts, accepted or ""])


def _new_to_the_sources(text: str, given: str) -> list[str]:
    """The words and numbers of `text` that nobody gave. Filler words say
    nothing; a word counts as given when its stem stands in `given`."""
    known = {_stem(token) for token in _TOKEN.findall(_plain(given))}
    return [
        token
        for token in _TOKEN.findall(_plain(text))
        if token not in _FILLER and _stem(token) not in known
    ]


def _sources_message(record: str, asked: str, accepted: str) -> str:
    """The two sources as the verification reads them. Each under its own name
    (#1653): under "VRAAG" beside an empty fiche, the model read the user's own
    words as the thing to check instead of as a source."""
    return (
        "BRON 1 — DE FICHE (wat er al staat)\n"
        + record
        + "\n\nBRON 2 — WAT DE GEBRUIKER SCHREEF (ook dit is een bron)\n"
        + asked
        + (f"\n\nAANVAARD VOOR DE DATUM\n{accepted}" if accepted.strip() else "")
    )


def _verify(
    provider: Any, sentences: list[str], sources_message: str, given: str, names: set[str]
) -> dict[int, str]:
    """The verification call: which sentences state something no source holds.
    Raises on a failed call — the caller says the proposal was not checked.

    **Its verdict is checked** (#1653; Koen, 6 October 2026: a description whose
    every fact stood in his request came back "geen enkele zin heeft een bron").
    The request is a source for the description as it is for the name, the place
    and the date, and that is a rule of this code, not a hope about a prompt: a
    verdict holds only when the SENTENCE carries a word or a number that nobody
    gave (`given_facts`, `_new_to_the_sources`). A sentence that only rewords
    what was given cannot be marked; one that adds anything — a fact, a mood, a
    word from the instruction — still is, alone or mixed with a given fact.

    **The known limit**, said plainly: a sentence built ONLY from given words
    can state something nobody said ("De zoo is aan het Dorpsplein"). The
    verification would catch it; this check then overrules it. It is the price
    of not refusing every reworded sentence, and the user reads the proposal
    before Toepassen. The `claim` the verification names is shown with its
    reason; it does not decide."""
    listing = "\n".join(f"{i}. {scrub(s, names)}" for i, s in enumerate(sentences, 1))
    reply = provider.complete(
        [
            {"role": "system", "content": VERIFY_PROMPT},
            {
                "role": "user",
                "content": f"{sources_message}\n\nOMSCHRIJVING (zinnen genummerd)\n{listing}",
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
        if not 0 <= index < len(sentences):
            continue
        if not _new_to_the_sources(sentences[index], given):
            logger.info(
                "Verification verdict refused: the sentence adds nothing to what was given."
            )
            continue
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

    date_fields, accepted = _date_fields(data, activity, sources, asked, proposal.left_out)

    description = _text(data, "description", DESCRIPTION_MAX)
    if description and description != (activity.description or ""):
        sentences = [s.strip() for s in _SENTENCE.findall(description) if s.strip()]
        facts = f"{sources} {accepted}"
        reasons = {i: why for i, s in enumerate(sentences) if (why := _own_marks(s, facts, names))}
        try:
            checked = _verify(
                provider,
                sentences,
                _sources_message(record, asked, accepted),
                given_facts(record, asked, accepted),
                names,
            )
            for index, why in checked.items():
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
            # The panel says why, per sentence (#1653): "geen bron" alone told Koen
            # nothing about which check had refused what.
            proposal.marks = []
            proposal.left_out.append(
                _("Omschrijving: niet voorgesteld — geen enkele zin heeft een bron.")
            )
            proposal.left_out.extend(f"«{sentences[i]}» — {reasons[i]}" for i in sorted(reasons))
    proposal.fields.extend(date_fields)
    return proposal
