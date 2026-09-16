"""Raakje drafts the newsletter (CR-05 §3.15, §3.16, #984).

The first *acting* capability on the CR-07 kernel — and acting only as far as
proposing: a proposal is text the author reviews and applies with a click. It
never sends, never sees a recipient, never picks the audience. It reaches the
kernel only through ``chatbot.api``.

**The division of labour.** The model writes the language; the facts come from
the sources. Five layers keep it that way, each catching what the previous one
misses:

1. *Facts as markers.* The model writes ``[[activiteit:12]]`` or
   ``[[fotos:12]]``; the server replaces them with the line the insert helper
   produces. A date, a place or a link in that line cannot be invented.
2. *Few sources, stated per call.* The chosen activities, the ticked meeting
   points, the author's instruction, the current letter — and the public read
   tools for an activity the author names in the conversation. Example letters
   are style only.
3. *Deterministic checks* on every number, every amount and every function
   word, and on known person names.
4. *A verification pass*: a second, separate call ties every factual claim to a
   source passage and names the ones without support. It catches what no
   word list can — an invented game is an ordinary word.
5. *The author decides per mark.* A marked sentence is left out on apply unless
   the author ticks "klopt, behouden".

**Names never leave, and never come back.** Everything outbound passes
``scrub`` first, with the same name list the seam guard scans against
(``mdm.person_name_parts``). A removed name becomes ``[naam]`` and is not put
back: individual organisers are never thanked (Koen, 16 September 2026). This is
also why this module does not reuse the reporting assistant's scrubber — that
one turns names into tokens *in order to* restore them.
"""
from __future__ import annotations

import html as html_lib
import json
import logging
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.i18n import _

from app.domains.newsletter.models import (
    LETTER_SENT,
    MESSAGE_AUTHOR,
    MESSAGE_RAAKJE,
    DraftingMessage,
    Newsletter,
)
from app.domains.newsletter import service as nb

logger = logging.getLogger(__name__)

CAPABILITY = "newsletter_drafting"
NAME_PLACEHOLDER = "[naam]"
# How many earlier letters to the same audience go along as style examples.
EXAMPLE_LETTERS = 2
# The part of an example letter that goes along — enough for the tone.
EXAMPLE_CHARS = 1500
# The conversation turns that go along, oldest dropped first.
HISTORY_TURNS = 6
MAX_TOOL_ROUNDS = 3
# The system prompt is generated from this module, not from stored content, so
# the guard need not scan it for names (CR-07's rule; proven by a test).
SCAN_PROMPT_NAMES = False

_MARKER = re.compile(r"\[\[(activiteit|fotos):(\d+)\]\]")
_NUMBER = re.compile(r"\d+(?:[.,:]\d+)*")
_AMOUNT = re.compile(r"(?:€\s*(\d+(?:[.,]\d{1,2})?))|(?:(\d+(?:[.,]\d{1,2})?)\s*(?:euro|eur)\b)",
                     re.IGNORECASE)
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_SENTENCE = re.compile(r"[^.!?]*[.!?]+|[^.!?]+$")

# Words that attach a role to someone. Each must occur in a source before a
# proposal may use it — the public Raakje once made a steward a treasurer (#309).
FUNCTION_WORDS = (
    "voorzitter", "ondervoorzitter", "secretaris", "penningmeester", "wijkmeester",
    "wijkmeesters", "bestuurslid", "bestuursleden", "organisator", "organisatoren",
    "organisatrice", "coördinator", "coordinator", "verantwoordelijke", "trekker",
    "trekkers", "gastspreker", "spreker",
)


class DraftingError(RuntimeError):
    """Raakje could not make a proposal. The message is for the screen."""


# ── Names ────────────────────────────────────────────────────────────────────

def scrub(text: str, names: set[str]) -> str:
    """Every known name part becomes ``[naam]`` — before anything leaves.

    The same list, and the same word rule, as the seam guard: whatever the guard
    would refuse, this removes first. A surname that is also an ordinary word is
    removed as well; the guard would block it just the same, and a slightly
    poorer sentence for the model is the safe side.
    """
    if not text or not names:
        return text or ""

    def replace(match: re.Match) -> str:
        word = match.group(0)
        return NAME_PLACEHOLDER if len(word) >= 3 and word.lower() in names else word

    return _WORD.sub(replace, text)


def _names(db: Session) -> set[str]:
    from app.domains.mdm.api import person_name_parts

    return person_name_parts(db)


# ── The letter as numbered paragraphs ────────────────────────────────────────

class _Splitter(HTMLParser):
    """Splits sanitised editor HTML into its top-level blocks, verbatim."""

    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=False)
        self.source = source
        self.blocks: list[str] = []
        self._depth = 0
        self._start: Optional[int] = None
        self._lines = [0]
        for line in source.splitlines(keepends=True):
            self._lines.append(self._lines[-1] + len(line))

    def _offset(self) -> int:
        line, col = self.getpos()
        return self._lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        if self._depth == 0:
            self._start = self._offset()
        if tag not in ("br", "img", "hr"):
            self._depth += 1

    def handle_endtag(self, tag):
        if tag in ("br", "img", "hr"):
            return
        self._depth = max(0, self._depth - 1)
        if self._depth == 0 and self._start is not None:
            end = self.source.index(">", self._offset()) + 1
            self.blocks.append(self.source[self._start:end])
            self._start = None

    def handle_startendtag(self, tag, attrs):
        if self._depth == 0:
            start = self._offset()
            end = self.source.index(">", start) + 1
            if tag not in ("br",):
                self.blocks.append(self.source[start:end])

    def handle_data(self, data):
        if self._depth == 0 and data.strip():
            self.blocks.append(f"<div>{html_lib.escape(data.strip())}</div>")


def paragraphs(body_html: str) -> list[str]:
    """The top-level blocks of the letter, as HTML."""
    splitter = _Splitter(body_html or "")
    splitter.feed(body_html or "")
    splitter.close()
    return [block for block in splitter.blocks if block.strip()]


def plain(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html or "", flags=re.I)
    text = re.sub(r"</(li|div|p|h\d)>", "\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"[ \t]+", " ", html_lib.unescape(text)).strip()


# ── Sources ──────────────────────────────────────────────────────────────────

@dataclass
class Sources:
    """Everything a proposal may state facts from, already scrubbed."""

    activity_ids: list[int]
    activity_texts: dict[int, str]
    points: list[str]
    instruction: str
    letter: list[str]
    upcoming: str
    house_style: str
    examples: list[str]
    tool_results: list[str] = field(default_factory=list)

    def fact_text(self) -> str:
        """The text a fact must be found in (layer 3). Style examples excluded."""
        return "\n".join([*self.activity_texts.values(), *self.points,
                          self.instruction, *self.letter, self.upcoming,
                          *self.tool_results])


def _activity_text(db: Session, activity_id: int) -> str:
    from app.domains.chatbot.api import execute_read_tool

    return execute_read_tool("get_activity_detail", {"activity_id": activity_id}, db)


def _upcoming_list(db: Session) -> str:
    """Names and ids of the coming activities — so "zet de BBQ er ook bij"
    resolves to an id. Dates are left out on purpose: the marker brings them."""
    spans = nb.insertable_activities(db)
    return "\n".join(f"- {s.activity.id}: {s.activity.name}" for s in spans)


def _examples(db: Session, letter: Newsletter, names: set[str]) -> list[str]:
    if not letter.audience:
        return []
    earlier = (db.query(Newsletter)
               .filter(Newsletter.status == LETTER_SENT,
                       Newsletter.audience == letter.audience,
                       Newsletter.id != letter.id)
               .order_by(Newsletter.send_finished_at.desc())
               .limit(EXAMPLE_LETTERS).all())
    return [scrub(plain(e.body_html)[:EXAMPLE_CHARS], names) for e in earlier]


def gather_sources(db: Session, letter: Newsletter, *, instruction: str,
                   names: set[str]) -> Sources:
    from app.domains.meetings.api import recent_report_points
    from app.kernel.tenant_config import tenant_newsletter_house_style

    ticked = set(letter.draft_meeting_item_ids or [])
    points = []
    for point in recent_report_points(db):
        if point.item.id not in ticked:
            continue
        line = f"[{point.section}] {point.item.label}"
        if point.item.activity_id:
            line += f" (activiteit {point.item.activity_id})"
        notes = plain(point.item.notes)
        if notes:
            line += f": {notes}"
        points.append(scrub(line, names))
    activity_ids = list(letter.draft_activity_ids or [])
    return Sources(
        activity_ids=activity_ids,
        activity_texts={i: scrub(_activity_text(db, i), names) for i in activity_ids},
        points=points,
        instruction=scrub(instruction, names),
        letter=[scrub(plain(p), names) for p in paragraphs(letter.body_html)],
        upcoming=scrub(_upcoming_list(db), names),
        house_style=scrub(tenant_newsletter_house_style(db), names),
        examples=_examples(db, letter, names),
    )


# ── The prompt ───────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Je bent Raakje en je helpt het bestuur van een Vlaamse vereniging een nieuwsbrief te schrijven, in het Nederlands (België).

WAT JE DOET
- Je schrijft voorstellen. Je verstuurt niets, en je weet niet wie de brief krijgt.
- Je schrijft de TAAL: warm, enthousiast, helder, in de huisstijl hieronder.
- De FEITEN komen uitsluitend uit de BRONNEN die je krijgt, en uit de leestools voor activiteiten. Staat iets niet in een bron, schrijf het dan niet. Weglaten is altijd beter dan aanvullen.

VASTE REGELS
- Schrijf NOOIT zelf een datum, een uur, een plaats, een inschrijflink of een fotolink. Zet in de plaats daarvan een markering op een eigen regel: [[activiteit:ID]] voor de regel met datum, uur, plaats en inschrijflink van activiteit ID, en [[fotos:ID]] voor de link naar het fotoalbum van activiteit ID. Het portaal vult die in.
- Noem nooit personen en bedank nooit individuele organisatoren of vrijwilligers. [naam] betekent dat er een naam weggehaald is: neem die nooit over en raad nooit wie het was.
- Geef niemand een functie of rol die niet letterlijk in een bron staat.
- Verzin geen programma-onderdelen, spelletjes, gerechten, prijzen of aantallen. Een bedrag noem je alleen zoals het in de activiteitgegevens staat.
- Schrijf geen afsluiting of groet onderaan: het portaal zet die er zelf onder.
- Kopjes schrijf je als een regel die begint met "# ". Vet schrijf je als **zo**.

ANTWOORD
Antwoord met één JSON-object en niets anders.
- Voor een volledige brief: {"reply": "één korte zin voor de auteur", "subject": "onderwerp", "paragraphs": ["alinea", "..."]}
- Voor een wijziging aan de bestaande brief: {"reply": "één korte zin", "subject": null of een nieuw onderwerp, "operations": [{"op": "replace", "paragraph": N, "text": "..."}, {"op": "insert_after", "paragraph": N, "text": "..."}, {"op": "remove", "paragraph": N}]}
  De alinea's van de bestaande brief zijn genummerd vanaf 1; "insert_after" met paragraph 0 zet iets bovenaan.
"""

VERIFY_PROMPT = """Je controleert een voorstel voor een nieuwsbrief tegen de BRONNEN. Je schrijft zelf niets bij.

Zoek elke feitelijke bewering in het voorstel: wat er te doen is, wie wat doet, hoeveel iets kost, hoeveel er zijn, wanneer of waar iets is, wat er gebeurde.
Een bewering is GESTAAFD als een bron ze zegt. Enthousiaste taal ("een avond om niet te missen") is geen feit.
Markeringen zoals [[activiteit:12]] zijn altijd gestaafd.

Antwoord met één JSON-object: {"unsupported": [{"paragraph": N, "quote": "letterlijk stuk uit die alinea", "reason": "korte reden in het Nederlands"}]}
Een lege lijst betekent: alles is gestaafd.
"""


def _sources_message(src: Sources) -> str:
    parts = ["BRONNEN"]
    for activity_id in src.activity_ids:
        parts.append(f"## Activiteit {activity_id} (gekozen)\n{src.activity_texts.get(activity_id, '')}")
    if src.points:
        parts.append("## Aangevinkte punten uit het vergaderverslag\n" + "\n".join(f"- {p}" for p in src.points))
    if src.instruction:
        parts.append(f"## Wat de auteur wil vertellen\n{src.instruction}")
    if src.upcoming:
        parts.append("## Komende activiteiten (id: naam) — details via de leestools\n" + src.upcoming)
    parts.append("HUISSTIJL\n" + (src.house_style or "Warm, enthousiast, jij-vorm, korte zinnen."))
    if src.examples:
        parts.append("VOORBEELDEN VAN EERDERE BRIEVEN (alleen voor de toon — geen bron voor feiten)\n"
                     + "\n---\n".join(src.examples))
    if src.letter:
        parts.append("DE BRIEF ZOALS HIJ NU IS\n"
                     + "\n".join(f"{i}. {p}" for i, p in enumerate(src.letter, 1)))
    else:
        parts.append("DE BRIEF IS NOG LEEG")
    return "\n\n".join(parts)


def _parse_json(text: str) -> dict[str, Any]:
    start, end = (text or "").find("{"), (text or "").rfind("}")
    if start < 0 or end <= start:
        raise DraftingError(_("Raakje gaf geen bruikbaar voorstel. Probeer het opnieuw."))
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise DraftingError(_("Raakje gaf geen bruikbaar voorstel. Probeer het opnieuw.")) from exc
    if not isinstance(data, dict):
        raise DraftingError(_("Raakje gaf geen bruikbaar voorstel. Probeer het opnieuw."))
    return data


# ── Rendering a proposal ─────────────────────────────────────────────────────

def _inline(text: str) -> str:
    escaped = html_lib.escape(text)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def _paragraph_html(text: str, facts: dict[int, Any]) -> str:
    """Model text → editor HTML, with every marker filled in by the server."""
    blocks = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        marker = _MARKER.fullmatch(line)
        if marker:
            kind, activity_id = marker.group(1), int(marker.group(2))
            fact = facts.get(activity_id)
            if fact is None:
                continue
            html = (nb.activity_line_html(fact) if kind == "activiteit"
                    else nb.photos_line_html(fact))
            if html:
                blocks.append(f"<div>{html}</div>")
            continue
        line = _MARKER.sub("", line).strip()
        if not line:
            continue
        if line.startswith("# "):
            blocks.append(f"<div><strong>{_inline(line[2:].strip())}</strong></div>")
        else:
            blocks.append(f"<div>{_inline(line)}</div>")
    return "".join(blocks)


def _marker_ids(texts: list[str]) -> set[int]:
    return {int(m.group(2)) for t in texts for m in _MARKER.finditer(t or "")}


def _sentence_of(text: str, quote: str) -> str:
    """The sentence of ``text`` that holds ``quote`` — what "left out" removes."""
    position = text.find(quote)
    if position < 0:
        return quote
    for match in _SENTENCE.finditer(text):
        if match.start() <= position < match.end():
            return match.group(0).strip()
    return quote


def _to_decimal(raw: str) -> Optional[Decimal]:
    try:
        return Decimal(raw.replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def deterministic_marks(text: str, sources: Sources, prices: set[Decimal],
                        names: set[str]) -> list[dict[str, str]]:
    """Layer 3: numbers, amounts, function words and names, without a model."""
    marks: list[dict[str, str]] = []
    prose = _MARKER.sub(" ", text or "")
    fact_text = sources.fact_text().lower()
    fact_numbers = set(_NUMBER.findall(fact_text))

    for match in _AMOUNT.finditer(prose):
        value = _to_decimal(match.group(1) or match.group(2))
        if value is None or value not in prices:
            marks.append({"quote": match.group(0),
                          "reason": _("dit bedrag is geen prijs van de activiteit")})
    amounts = {m.group(0) for m in _AMOUNT.finditer(prose)}
    for number in _NUMBER.findall(prose):
        if any(number in a for a in amounts):
            continue
        if number not in fact_numbers:
            marks.append({"quote": number,
                          "reason": _("dit getal staat in geen enkele bron")})
    lowered = prose.lower()
    for word in FUNCTION_WORDS:
        if re.search(rf"\b{re.escape(word)}\b", lowered) and word not in fact_text:
            found = re.search(rf"\b{re.escape(word)}\b", prose, re.IGNORECASE)
            marks.append({"quote": found.group(0),
                          "reason": _("deze rol staat in geen enkele bron")})
    for word in _WORD.findall(prose):
        if len(word) >= 3 and word.lower() in names:
            marks.append({"quote": word, "reason": _("dit is een naam uit de ledenadministratie")})
    if NAME_PLACEHOLDER in prose:
        marks.append({"quote": NAME_PLACEHOLDER,
                      "reason": _("hier stond een weggehaalde naam")})
    return marks


def _attach(marks: list[dict[str, str]], texts: dict[int, str]) -> list[dict[str, Any]]:
    """Give every mark its paragraph, its sentence and an id."""
    out = []
    for mark in marks:
        index = mark.get("index")
        if index is None or index not in texts:
            continue
        quote = mark["quote"]
        if quote not in texts[index]:
            continue
        sentence = _sentence_of(texts[index], quote)
        key = (index, sentence)
        if any((m["index"], m["sentence"]) == key for m in out):
            continue
        out.append({"id": len(out) + 1, "index": index, "quote": quote,
                    "sentence": sentence, "reason": mark["reason"]})
    return out


@dataclass
class Turn:
    """What one request to Raakje produced."""

    reply: str
    proposal: dict[str, Any]


def _provider(db: Session, actor: str):
    from app.config import settings
    from app.domains.chatbot.api import (
        GuardedProvider, admin_rules, get_provider, sink_for)
    from app.domains.mdm.api import person_name_parts

    return GuardedProvider(
        get_provider(settings.admin_chat_model),
        admin_rules(lambda: person_name_parts(db), capability=CAPABILITY,
                    scan_prompt_names=SCAN_PROMPT_NAMES),
        sink_for(actor),
    )


def _history(letter: Newsletter, names: set[str]) -> list[dict[str, str]]:
    turns = []
    for message in list(letter.messages)[-HISTORY_TURNS:]:
        role = "user" if message.role == MESSAGE_AUTHOR else "assistant"
        turns.append({"role": role, "content": scrub(message.text, names)})
    return turns


def _dispatcher(names: set[str], collected: list[str]) -> Callable[[str, dict, Session], str]:
    """The public read tools, with names scrubbed out of every result."""
    from app.domains.chatbot.api import execute_read_tool

    def dispatch(name: str, arguments: dict, db: Session) -> str:
        result = scrub(execute_read_tool(name, arguments, db), names)
        collected.append(result)
        return result

    return dispatch


def ask(db: Session, letter: Newsletter, *, instruction: str, actor: str,
        base_url: str, selection: str = "") -> Turn:
    """One request: the whole letter when it is empty, pieces otherwise.

    Raises ``DraftingError`` for a proposal that cannot be used, and lets the
    kernel's ``SeamBlocked`` / ``ChatTimeout`` through for the screen.
    """
    from app.config import settings
    from app.domains.chatbot.api import read_tool_specs, run_chat

    if letter.status != "draft":
        raise DraftingError(_("Deze nieuwsbrief is al verstuurd."))
    instruction = (instruction or "").strip()
    names = _names(db)
    sources = gather_sources(db, letter, instruction=instruction, names=names)
    whole = not sources.letter

    request = instruction or (_("Schrijf een volledige nieuwsbrief.") if whole
                              else _("Verbeter de brief."))
    if selection.strip():
        target = scrub(selection.strip(), names)
        match = next((i for i, p in enumerate(sources.letter, 1) if target[:40] in p), None)
        if match:
            request += "\n" + _("(Dit gaat over alinea %(n)s.)") % {"n": match}
    request += "\n" + (_("Geef een volledige brief (paragraphs).") if whole
                       else _("Geef wijzigingen (operations)."))

    messages = [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": _sources_message(sources)},
                {"role": "assistant", "content": _("Begrepen. Wat wil je?")},
                *_history(letter, names),
                {"role": "user", "content": scrub(request, names)}]
    provider = _provider(db, actor)
    collected: list[str] = []
    deadline = time.monotonic() + settings.admin_chat_timeout_seconds
    answer = run_chat(db, messages, provider, max_rounds=MAX_TOOL_ROUNDS,
                      tools=read_tool_specs(), dispatch=_dispatcher(names, collected),
                      deadline=deadline)
    sources.tool_results = collected
    data = _parse_json(answer)

    proposal = build_proposal(db, letter, data, sources=sources, names=names,
                              base_url=base_url, whole=whole)
    verify(db, proposal, sources=sources, provider=provider, names=names)
    return Turn(reply=str(data.get("reply") or "").strip()[:500], proposal=proposal)


def build_proposal(db: Session, letter: Newsletter, data: dict[str, Any], *,
                   sources: Sources, names: set[str], base_url: str,
                   whole: bool) -> dict[str, Any]:
    """The model's JSON → a proposal the screen can show and apply."""
    ops: list[dict[str, Any]] = []
    if whole or "paragraphs" in data and not data.get("operations"):
        texts = [str(t) for t in (data.get("paragraphs") or []) if str(t).strip()]
        if not texts:
            raise DraftingError(_("Raakje gaf een leeg voorstel. Probeer het opnieuw."))
        ops = [{"op": "insert_after", "paragraph": 0, "text": "\n\n".join(texts)}]
        kind = "draft"
    else:
        count = len(sources.letter)
        for raw in data.get("operations") or []:
            if not isinstance(raw, dict):
                continue
            op = raw.get("op")
            try:
                number = int(raw.get("paragraph"))
            except (TypeError, ValueError):
                continue
            if op not in ("replace", "insert_after", "remove"):
                continue
            if op == "insert_after" and not 0 <= number <= count:
                continue
            if op in ("replace", "remove") and not 1 <= number <= count:
                continue
            text = str(raw.get("text") or "") if op != "remove" else ""
            if op != "remove" and not text.strip():
                continue
            ops.append({"op": op, "paragraph": number, "text": text})
        if not ops and not data.get("subject"):
            raise DraftingError(_("Raakje stelde geen wijziging voor. Zeg anders wat er moet veranderen."))
        kind = "edit"

    ids = set(sources.activity_ids) | _marker_ids([o["text"] for o in ops])
    facts = nb.activity_facts(db, ids, base_url=base_url)
    prices = {p for f in facts.values() for p in f.prices}
    texts = {i: o["text"] for i, o in enumerate(ops) if o["text"]}
    raw_marks = []
    for index, text in texts.items():
        for mark in deterministic_marks(text, sources, prices, names):
            raw_marks.append({**mark, "index": index})
    for index, op in enumerate(ops):
        op["index"] = index
        op["html"] = _paragraph_html(op["text"], facts)
    subject = data.get("subject")
    return {"kind": kind, "subject": scrub(str(subject), names).strip()[:500] if subject else None,
            "operations": ops, "marks": _attach(raw_marks, texts),
            "facts": sorted(facts), "snapshot": nb_snapshot(letter.body_html),
            "status": "open"}


def verify(db: Session, proposal: dict[str, Any], *, sources: Sources, provider,
           names: set[str]) -> None:
    """Layer 4: a separate call names the claims without support.

    If the verification itself fails, the proposal is marked as a whole — an
    unchecked proposal must not look like a checked one.
    """
    texts = {op["index"]: op["text"] for op in proposal["operations"] if op["text"]}
    if not texts:
        return
    # Scrubbed like everything else that leaves: a name the model wrote itself
    # would otherwise block this call. It is marked by layer 3 anyway.
    # Numbered from 1, as a reader counts; mapped back below.
    listing = "\n".join(f"{i + 1}. {scrub(_MARKER.sub('[markering]', t), names)}"
                        for i, t in texts.items())
    messages = [{"role": "system", "content": VERIFY_PROMPT},
                {"role": "user", "content": _sources_message(sources)
                 + "\n\nRESULTATEN VAN DE LEESTOOLS\n" + "\n".join(sources.tool_results)
                 + "\n\nVOORSTEL (alinea's genummerd)\n" + listing}]
    try:
        reply = provider.complete(messages, tools=None)
        data = _parse_json(reply.content or "")
        found = data.get("unsupported") or []
    except Exception as exc:  # noqa: BLE001 — see the docstring
        from app.domains.chatbot.api import SeamBlocked

        if isinstance(exc, SeamBlocked):
            raise
        logger.warning("Controleronde van het nieuwsbriefvoorstel mislukte: %s", exc)
        proposal["unverified"] = True
        return
    extra = []
    for item in found:
        if not isinstance(item, dict):
            continue
        try:
            index = int(item.get("paragraph")) - 1
        except (TypeError, ValueError):
            continue
        quote = str(item.get("quote") or "").strip()
        if index in texts and quote and quote in scrub(texts[index], names):
            if quote not in texts[index]:
                continue
            extra.append({"index": index, "quote": quote,
                          "reason": str(item.get("reason") or _("staat in geen enkele bron"))[:200]})
    existing = [{"index": m["index"], "quote": m["quote"], "reason": m["reason"]}
                for m in proposal["marks"]]
    proposal["marks"] = _attach(existing + extra, texts)


def nb_snapshot(body_html: str) -> str:
    import hashlib

    return hashlib.sha256((body_html or "").encode()).hexdigest()


# ── Applying ─────────────────────────────────────────────────────────────────

def _without(text: str, sentences: list[str]) -> str:
    for sentence in sentences:
        text = text.replace(sentence, "")
    return re.sub(r"[ \t]{2,}", " ", text).strip()


def apply(db: Session, letter: Newsletter, message: DraftingMessage, *,
          keep: set[int], body_html: str, base_url: str,
          placement: str = "replace") -> str:
    """The letter as it becomes when this proposal is applied.

    A marked sentence is left out unless its mark id is in ``keep``
    (CR-05 §3.16, layer 5). An edit is refused when the letter changed since
    the proposal was made: its paragraph numbers would point elsewhere.

    Returns the HTML the editor takes over. For a whole draft with
    ``placement="cursor"`` that is only the proposal, to insert at the cursor.
    """
    proposal = dict(message.proposal or {})
    if proposal.get("status") != "open":
        raise DraftingError(_("Dit voorstel is al afgehandeld."))
    nb.update_draft(db, letter, subject=letter.subject, body_html=body_html,
                    audience=letter.audience)
    drop = {}
    for mark in proposal.get("marks") or []:
        if mark["id"] not in keep:
            drop.setdefault(mark["index"], []).append(mark["sentence"])

    facts = nb.activity_facts(db, proposal.get("facts") or [], base_url=base_url)
    rendered = {}
    for op in proposal.get("operations") or []:
        text = _without(op["text"], drop.get(op["index"], []))
        rendered[op["index"]] = _paragraph_html(text, facts)

    closing = nb.closing_html(db)
    if proposal.get("kind") == "draft":
        html = rendered.get(0, "")
        result = html if placement == "cursor" else html + closing
    else:
        if proposal.get("snapshot") != nb_snapshot(letter.body_html):
            raise DraftingError(_("De brief veranderde sinds dit voorstel. Vraag het "
                                  "Raakje opnieuw, dan werkt het op de tekst van nu."))
        blocks = paragraphs(letter.body_html)
        inserts: dict[int, list[str]] = {}
        replaced: dict[int, str] = {}
        removed: set[int] = set()
        for op in proposal.get("operations") or []:
            if op["op"] == "insert_after":
                inserts.setdefault(op["paragraph"], []).append(rendered[op["index"]])
            elif op["op"] == "replace":
                replaced[op["paragraph"]] = rendered[op["index"]]
            else:
                removed.add(op["paragraph"])
        out = list(inserts.get(0, []))
        for number, block in enumerate(blocks, 1):
            if number not in removed:
                out.append(replaced.get(number, block))
            out.extend(inserts.get(number, []))
        result = "".join(out)

    if proposal.get("subject") and (placement != "cursor" or not letter.subject):
        letter.subject = proposal["subject"]
    proposal["status"] = "applied"
    proposal["kept"] = sorted(keep)
    message.proposal = proposal
    new_body = result if placement != "cursor" else letter.body_html
    nb.update_draft(db, letter, subject=letter.subject, body_html=new_body,
                    audience=letter.audience)
    from app.domains.cms.api import sanitize_cms_html

    return sanitize_cms_html(result) or ""


def dismiss(db: Session, message: DraftingMessage) -> None:
    proposal = dict(message.proposal or {})
    if proposal.get("status") == "open":
        proposal["status"] = "dismissed"
        message.proposal = proposal
        db.commit()


def record(db: Session, letter: Newsletter, *, author_text: str,
           turn: Optional[Turn] = None, error: str = "") -> DraftingMessage:
    """Store both sides of the turn with the draft."""
    db.add(DraftingMessage(newsletter_id=letter.id, role=MESSAGE_AUTHOR,
                           text=author_text or _("Schrijf een voorstel.")))
    answer = DraftingMessage(newsletter_id=letter.id, role=MESSAGE_RAAKJE,
                             text=(turn.reply if turn else error) or "",
                             proposal=turn.proposal if turn else None)
    db.add(answer)
    db.commit()
    return answer


def get_message(db: Session, letter: Newsletter, message_id: int) -> Optional[DraftingMessage]:
    message = db.get(DraftingMessage, message_id)
    if message is None or message.newsletter_id != letter.id:
        return None
    return message


def display(db: Session, letter: Newsletter, message: DraftingMessage) -> dict[str, Any]:
    """A proposal as the screen shows it: per operation what changes, with the
    marked sentences highlighted and their reasons listed. Built here and not
    in the template (design-system §8.3)."""
    proposal = message.proposal or {}
    current = [plain(p) for p in paragraphs(letter.body_html)]
    unchanged = proposal.get("snapshot") == nb_snapshot(letter.body_html)
    from app.domains.activities.api import Activity

    ids = proposal.get("facts") or []
    names = {a.id: a.name for a in db.query(Activity).filter(Activity.id.in_(ids)).all()} if ids else {}
    marks_by_op: dict[int, list[dict[str, Any]]] = {}
    for mark in proposal.get("marks") or []:
        marks_by_op.setdefault(mark["index"], []).append(mark)

    def shown(text: str, marks: list[dict[str, Any]]) -> str:
        out = html_lib.escape(text)
        for mark in marks:
            sentence = html_lib.escape(mark["sentence"])
            out = out.replace(sentence, f'<mark class="bg-yellow-100 text-ink rounded px-0.5" data-markering="{mark["id"]}">'
                                        f'{sentence}</mark>', 1)

        def chip(match: re.Match) -> str:
            kind, activity_id = match.group(1), int(match.group(2))
            name = html_lib.escape(names.get(activity_id, str(activity_id)))
            label = (_("datum, plaats en inschrijflink van %(n)s") if kind == "activiteit"
                     else _("link naar de foto's van %(n)s")) % {"n": name}
            return f'<span class="text-ink-soft italic">[{label}]</span>'

        out = re.sub(r"\[\[(activiteit|fotos):(\d+)\]\]", chip, out)
        return out.replace("\n", "<br>")

    operations = []
    for op in proposal.get("operations") or []:
        number = op.get("paragraph", 0)
        if proposal.get("kind") == "draft":
            label = _("Volledige brief")
        elif op["op"] == "replace":
            label = _("Vervang alinea %(n)s") % {"n": number}
        elif op["op"] == "remove":
            label = _("Schrap alinea %(n)s") % {"n": number}
        elif number == 0:
            label = _("Invoegen bovenaan")
        else:
            label = _("Invoegen na alinea %(n)s") % {"n": number}
        old = (current[number - 1] if unchanged and op["op"] in ("replace", "remove")
               and 0 < number <= len(current) else "")
        operations.append({"label": label, "old": old,
                           "new_html": shown(op.get("text") or "", marks_by_op.get(op["index"], [])),
                           "marks": marks_by_op.get(op["index"], [])})
    return {"id": message.id, "kind": proposal.get("kind"), "status": proposal.get("status"),
            "subject": proposal.get("subject"), "operations": operations,
            "unverified": bool(proposal.get("unverified")),
            "stale": proposal.get("kind") == "edit" and not unchanged,
            "has_text": bool(current)}
