"""The guard on the provider seam: refuse, don't hope (CR-07 §5.8).

Everything else in this feature tries to make sure no personal data reaches a
language model: objects are classified, person-naming ones are refused, values
become tokens. This module assumes all of that failed and looks at the payload one
last time, immediately before the HTTP post.

**Independent, and that word carries the whole design.** It shares no code with
the `ai_exposure` declaration, with the tokenisation, or with the assistant's
refusals — a check that fails together with the thing it checks, checks nothing.
So it does not ask "was this classified correctly?" but "does this text contain a
name or an e-mail address?", which is a question the rest of the mechanism cannot
answer wrongly on its behalf. It is the layer that catches the bug nobody
predicted, and it is the reason the payload log and this guard were built in phase
1 rather than alongside the tokenisation they protect.

**Per capability, not global.** The public bot's contact path exists so a visitor
can type their own name and e-mail; a global name-and-e-mail guard would block
`submit_idea` on the first message it was designed for. So the tenant-name match
and the e-mail pattern are on for the back office and off for the public surface,
while the phone/IBAN patterns and the logging apply to both. That asymmetry is
deliberate and is the only one: everything else the two surfaces share.

**Wat er van het system-bericht gescand wordt, hangt af van waar dat bericht
vandaan komt.** Administratiegegevens komen een payload binnen langs twee deuren:
wat de gebruiker typt, en wat een tool teruggeeft. Een derde deur bestaat alleen
wanneer de prompt zélf uit opgeslagen inhoud gebouwd wordt — bij de publieke bot is
dat zo (CMS-pagina's en notities), bij de rapportage-assistent niet: die prompt
wordt gerenderd uit de universum-declaratie en kan per constructie geen enkele
waarde uit de databank bevatten.

Dat onderscheid is geen verfijning achteraf maar de reparatie van een blokkade die
ALLES tegenhield. Gemeten op HDEV: één gezin "Van den Broeck" zet `van` en `den` in
de namenlijst, de catalogus is twintigduizend tekens Nederlands, en dus botste élke
vraag — drie treffers, altijd dezelfde drie, ongeacht wat de beheerder typte. Voor
wie het gebruikt is dat geen bescherming maar een kapotte assistent, en zo'n
controle gaat uit.

Daarom `scan_prompt_names`, en daarom staat hij standaard AAN: een pakket dat er
niets over zegt, wordt volledig gescand. Alleen een pakket dat kan aantonen dat zijn
prompt machinaal gegenereerd is, mag hem uitzetten — en dat aantonen is een test,
geen belofte.

**De patroon-controles slaan het system-bericht altijd over, de naam-controle
alleen wanneer die prompt gegenereerd is.** Dat
is geen versoepeling maar een meting: de eerste keer dat de wachter draaide,
blokkeerde ze elke publieke vraag, en de dader was de privacypagina in de
system-prompt — met het e-mailadres van de vereniging en haar IBAN erin. Dat is
gepubliceerde tekst die er met opzet staat: zonder rekeningnummer kan de bot niet
zeggen waar het lidgeld heen moet. Een wachter die dát blokkeert, beschermt niets
en breekt alles, en wordt dus binnen de week uitgezet — dat is hoe een controle
sterft.

Wat blijft staan is wél de bewaking die telt: alles wat de gebruiker typt en alles
wat een tool teruggeeft — de twee kanalen waarlangs administratiegegevens kunnen
vertrekken — passeert onverkort. En de naam-controle kijkt ook naar het
system-bericht, want een ledennaam hoort daar evenmin thuis.

**It reads text, and it says where** (#1969). The checks read every string of
the payload as the text it holds — a tool's result and a tool call's arguments as
their tree — never the payload's serialised form, in which a line's first word
reads with a letter glued on. Which words of a text are name parts is one
function, `name_words`; the writer's cleaning (`scrub_names`) replaces exactly
those, so the guard and the cleaning cannot disagree on a word. And a refusal
names the PART of the payload the hit stands in — the question, a text that was
sent along, what a tool brought back — never what was found: the reader is told
what they can do about that part, only where there is something to do.

Honest limits, stated here rather than discovered later: a nickname, an initial or
a typo slips the name match, and a family name that is also a street name gives a
false block. The first is why the payload log exists; the second is the safe side
of the trade — the refusal says in which part the word stands, and for a report's
result it points to building the report by hand.
"""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Callable, Iterator, Optional, Sequence

from .models import AiCapability, AiStatus, AiSurface
from .providers.base import AssistantMessage, LLMProvider

logger = logging.getLogger(__name__)


class SeamBlocked(RuntimeError):
    """The guard refused to send this payload. The message is for the screen.

    `places` are the parts of the payload the hit stands in, in the screen's own
    words (#1969); `link` is where the reader can go on by hand — `(href, words)`
    — when the place has such a way (a report's result: Rapporten).
    """

    def __init__(
        self, message: str, *, places: tuple[str, ...] = (), link: tuple[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.places = places
        self.link = link


# Patterns that have no business in outbound payload text, whichever surface sends
# it — with one exception per §5.8, the e-mail address a visitor types into the
# public contact path. Each is deliberately loose: a false block costs a rephrase,
# a miss costs a leak.
# The part before the `@` is bounded at 64 characters, the most an address's
# local part may hold (RFC 5321 §4.5.3.1.1): so the pattern's running time grows
# linearly with the text (#1986).
_EMAIL = re.compile(r"[^\s@<>()\[\]]{1,64}@[^\s@<>()\[\]]+\.[a-zA-Z]{2,}")
# Belgian shapes with and without the country code, spaces/dots/dashes allowed:
# 0473 12 34 56, +32 473 123 456, 016/12.34.56.
_PHONE = re.compile(r"(?:\+32|0032|\b0)[\s./-]?\d(?:[\s./-]?\d){7,9}\b")
# An IBAN: two letters, two check digits, then up to 30 alphanumerics in groups.
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}\b")

# What `redact` puts in their place; a letter still carrying one is not sent (#984).
EMAIL_PLACEHOLDER = "[e-mailadres]"
IBAN_PLACEHOLDER = "[rekeningnummer]"
PHONE_PLACEHOLDER = "[telefoonnummer]"
REDACTION_PLACEHOLDERS = (EMAIL_PLACEHOLDER, PHONE_PLACEHOLDER, IBAN_PLACEHOLDER)

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("een telefoonnummer", _PHONE),
    ("een rekeningnummer", _IBAN),
)


def redact(text: str) -> str:
    """Replace what the guard refuses by a neutral placeholder (#984).

    For a capability that sends content it did not write itself — flyer text,
    meeting notes — and would otherwise be blocked by an address somebody put
    there. The SAME patterns as the guard, so a redacted text never trips it on
    these; names are the caller's business (the guard reads them from mdm).
    """
    if not text:
        return text or ""
    text = _EMAIL.sub(EMAIL_PLACEHOLDER, text)
    text = _IBAN.sub(IBAN_PLACEHOLDER, text)
    return _PHONE.sub(PHONE_PLACEHOLDER, text)


_NAME_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

#: Characters without width that can stand inside a word and would split it for
#: the word rule (#1986): zero-width space, non-joiner and joiner, word joiner,
#: soft hyphen, and the zero-width no-break space.
_NO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠­﻿"))


def normal_text(text: str) -> str:
    """A text in the one form the word rule reads (#1986): Unicode NFC — a
    letter with its accent is one character, however it was typed — and without
    the characters that have no width."""
    return unicodedata.normalize("NFC", text).translate(_NO_WIDTH)


def _name_key(word: str) -> str:
    return unicodedata.normalize("NFC", normal_text(word).lower())


def normal_names(names: set[str]) -> set[str]:
    """Name parts in the form `name_words` compares them in — taken once per
    payload, not once per text."""
    return {_name_key(name) for name in names}


def name_words(text: str, names: set[str]) -> list[re.Match[str]]:
    """The words of a text that are name parts — THE word rule, and its one copy.

    A whole word of three letters or more, of letters in any script, whose
    lower-case form is a name part (`mdm.person_name_parts`: which words those
    are is mdm's to say). `scrub_names` replaces exactly these, and the guard
    refuses on exactly these (#1969): the two cannot disagree on a word, because
    neither has a rule of its own. It reads TEXT — what a person would read —
    never a serialisation of it.

    The text is read in one Unicode form (`normal_text`, #1986), so the matches
    are of `normal_text(text)`; `names` are compared in that form too
    (`normal_names` — the callers in this module pass them so).
    """
    if not text or not names:
        return []
    return [
        match
        for match in _NAME_WORD.finditer(normal_text(text))
        if len(match.group(0)) >= 3 and _name_key(match.group(0)) in names
    ]


class _Pairs(list[tuple[str, Any]]):
    """A JSON object as the string wrote it: its `(key, value)` pairs in order,
    a key that stands twice included. A mapping would keep one value per key."""


def _json_tree(text: str) -> Any:
    """What a string holds when it is itself JSON — an object or a list — else
    None. A tool's result and a tool call's arguments travel as such a string;
    the text a person would read is in its values, not in its escapes.

    A JSON string is read by its pairs (`_Pairs`), so what is read is what
    leaves. A string nested too deep — for the parser, or deeper than
    `_MAX_JSON_DEPTH` and so too deep to walk — is no tree: it is read as the
    plain text it is.
    """
    stripped = text.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        tree = json.loads(stripped, object_pairs_hook=_Pairs)
    except (ValueError, RecursionError):
        return None
    if not isinstance(tree, list) or _too_deep(tree):
        return None
    return tree


#: How deep a JSON string may nest and still be read as a tree. A tool's result
#: is a handful of levels deep; the walk over a tree recurses per level, so a
#: fixed ceiling far under the interpreter's own keeps it from ever raising.
_MAX_JSON_DEPTH = 100


def _too_deep(tree: list[Any]) -> bool:
    """Whether a parsed JSON tree nests deeper than `_MAX_JSON_DEPTH` — counted
    with a list of its own, not by recursion."""
    todo: list[tuple[list[Any], int]] = [(tree, 1)]
    while todo:
        node, depth = todo.pop()
        if depth > _MAX_JSON_DEPTH:
            return True
        children = (value for _, value in node) if isinstance(node, _Pairs) else node
        todo.extend((child, depth + 1) for child in children if isinstance(child, list))
    return False


def _scrub_tree(node: Any, names: set[str], placeholder: str) -> Any:
    if isinstance(node, str):
        return _scrub(node, names, placeholder)
    if isinstance(node, _Pairs):
        return {key: _scrub_tree(value, names, placeholder) for key, value in node}
    if isinstance(node, dict):
        return {key: _scrub_tree(value, names, placeholder) for key, value in node.items()}
    if isinstance(node, list):
        return [_scrub_tree(item, names, placeholder) for item in node]
    return node


def scrub_names(text: str, names: set[str], placeholder: str) -> str:
    """`redact`, and every known name part replaced by `placeholder` — for a
    capability that sends text it did not write (a request, a record, notes, a
    tool's result).

    The words are `name_words`', the guard's own (#1667, #1969): whatever the
    guard would refuse, this removes first. A text that is itself JSON (a tool's
    result) is cleaned value by value and written out again, because that is how
    the guard reads it: both look at the text inside, never at its escapes. The
    text that comes back is in the word rule's form (`normal_text`, #1986).
    """
    return _scrub(text or "", normal_names(names), placeholder)


def _scrub(text: str, names: set[str], placeholder: str) -> str:
    tree = _json_tree(text)
    if tree is not None:
        return json.dumps(_scrub_tree(tree, names, placeholder), ensure_ascii=False)
    text = normal_text(redact(text))
    hits = name_words(text, names)
    if not hits:
        return text
    out: list[str] = []
    last = 0
    for match in hits:
        out.extend((text[last : match.start()], placeholder))
        last = match.end()
    out.append(text[last:])
    return "".join(out)


# #1969: a refusal says WHERE the hit stands — the author's question, a text
# that was sent along, what a tool brought back — and never what it is. `{waar}`
# is the place in the screen's words, `{reden}` what was found, `{advies}` what
# the reader can do about that place, only where there is something to do.
_ADMIN_MESSAGE = (
    "Dit is niet verstuurd: in {waar} staat {reden}. Raakje stuurt geen namen, "
    "e-mailadressen, telefoonnummers of rekeningnummers naar het taalmodel.{advies}"
)

# De publieke bot krijgt een andere tekst, want hij weigert iets anders. Naam en
# e-mailadres mág een bezoeker geven (daar is het contactpad voor); een
# telefoonnummer of rekeningnummer heeft Raakje nooit nodig, en wat hij niet nodig
# heeft, stuurt hij niet door.
_PUBLIC_MESSAGE = (
    "Dat is niet verstuurd: in {waar} staat {reden}. Raakje heeft dat niet nodig.{advies}"
)

#: What the reader is told a finding is. A name is said as what the guard can
#: know: a word that is also somebody's name part — it may be the street.
_NAME = "een woord dat ook een naam uit de ledenadministratie is"
_SAID = {
    "een e-mailadres": "een e-mailadres",
    "een telefoonnummer": "een telefoonnummer",
    "een rekeningnummer": "een rekeningnummer",
}


@dataclass(frozen=True)
class Part:
    """A part of the payload, named for the reader (#1969).

    `where` is the place in the screen's words, with its article ("je vraag",
    "een voorbeeld van een eerdere brief"); `text` is the text of that part as
    it was sent; `advice` is one sentence on what the reader can do about that
    part — empty where there is nothing to do; `link` is `(href, words)` for a
    place that has a way to go on by hand.
    """

    where: str
    text: str = ""
    advice: str = ""
    link: tuple[str, str] | None = None


#: The places every payload has, by the role of the message the hit stands in.
QUESTION = Part(
    where="je vraag",
    advice=(
        "Herformuleer je vraag zonder dat gegeven — vraag bijvoorbeeld naar een groep "
        "in plaats van naar één persoon."
    ),
)
PUBLIC_QUESTION = Part(
    where="je bericht",
    advice=(
        "Laat het weg, dan geeft het bestuur je gerust een antwoord. Wil je "
        "teruggebeld worden, schrijf dat er dan gewoon bij."
    ),
)
CONVERSATION = Part(where="het gesprek tot nu toe")
INSTRUCTIONS = Part(where="de vaste instructies van Raakje")
TOOL_RESULT = Part(where="wat Raakje opzocht om te antwoorden")


@dataclass
class GuardRules:
    """What the guard checks for one capability.

    ``names`` is a callable and not a list: the name set is a database read, and a
    guard that loads it whether or not it is used would make the public bot pay for
    a check it does not run.
    """

    # A capability pack names its surface; the guard reads its rules from it.
    surface: AiSurface
    capability: AiCapability = AiCapability.CHAT
    match_names: bool = False
    match_email: bool = False
    #: Of het system-bericht meegescand wordt op namen. Standaard aan: wie er niets
    #: over zegt, krijgt de volledige controle. Uit mag alleen wanneer de prompt
    #: machinaal gegenereerd is en dus geen opgeslagen waarde kan dragen.
    scan_prompt_names: bool = True
    names: Callable[[], set[str]] = field(default=lambda: set())
    message: str = _ADMIN_MESSAGE
    #: #1969 — the places of this capability's payload. `parts` are the texts it
    #: sent along, each named for the reader (an activity's text, an example of
    #: an earlier letter); a callable, read only when a call is refused. What no
    #: part holds is placed by the message's role: `question` for the last
    #: message of the reader, `tool` for what a tool brought back.
    parts: Callable[[], Sequence[Part]] = field(default=lambda: ())
    question: Part = QUESTION
    tool: Part = TOOL_RESULT
    #: #1986 — the tools whose result is declared with labels (#1154): only in
    #: their result are the keys and the label fields read as labels. Every other
    #: tool's result is read in full.
    label_tools: frozenset[str] = frozenset()


def public_rules() -> GuardRules:
    """The public bot: patterns only. Its contact path exists to collect a name."""
    return GuardRules(
        surface=AiSurface.PUBLIC,
        match_names=False,
        match_email=False,
        message=_PUBLIC_MESSAGE,
        question=PUBLIC_QUESTION,
    )


def admin_rules(
    names: Callable[[], set[str]],
    *,
    capability: AiCapability,
    scan_prompt_names: bool = True,
    parts: Callable[[], Sequence[Part]] | None = None,
    tool: Part | None = None,
    label_tools: frozenset[str] = frozenset(),
) -> GuardRules:
    """The back office: everything on. Nothing here is anybody's own name to give.

    ``parts`` and ``tool`` (#1969) name the places of this pack's payload for a
    refusal: the texts it sends along, and what its tools bring back.
    ``label_tools`` (#1986) names the pack's tools whose result is declared with
    labels; see `GuardRules.label_tools`.

    ``scan_prompt_names=False`` is for a pack whose system prompt is rendered from
    a declaration rather than from stored content — see the module docstring, and
    prove it with a test before passing it.
    """
    return GuardRules(
        surface=AiSurface.ADMIN,
        capability=capability,
        match_names=True,
        match_email=True,
        scan_prompt_names=scan_prompt_names,
        names=names,
        parts=parts or (lambda: ()),
        tool=tool or TOOL_RESULT,
        label_tools=label_tools,
    )


def payload_text(messages: Sequence[dict[str, Any]], *, include_system: bool = True) -> str:
    """The outbound messages as one string, tool calls included.

    Serialised rather than walked field by field: a payload shape that grows a
    field would otherwise slip past the scan unread, which is exactly the class of
    mistake this guard exists for.
    """
    selected = [m for m in messages if include_system or m.get("role") != "system"]
    return json.dumps(selected, ensure_ascii=False, default=str)


#: Velden waarvan de WAARDE een machinaal etiket is en geen gegeven (#1154).
#: Vandaag twee: `key` en `name` van een kolom komen uit `universe.py`, en de
#: `name` van een tool-bericht is de naam van de tool. Ze staan hier bij naam en
#: niet als "alles behalve de waardevelden": een tool-antwoord dat later een veld
#: bijkrijgt, hoort gescand te worden en niet stil overgeslagen.
#: Since #1986 this holds only in the result of a tool in `GuardRules.label_tools`.
_ETIKETVELDEN = frozenset({"key", "name"})


def _texts(node: Any, *, machine: bool) -> Iterator[str]:
    """Every string of a payload tree, as the text it holds (#1969).

    Walked whole — nothing is skipped because it is unknown, which is the
    property of `payload_text` this keeps: whoever adds a field gets it scanned.
    A string that is itself JSON (a tool's result, a tool call's arguments) is
    read as its tree, so a line break inside it is a line break and not two
    characters glued to the next word.

    `machine` is for a tool's result (#1154): there a key, and the value of a
    label field (`_ETIKETVELDEN`), comes from a declaration and can carry no
    value of the database — a column title such as "Herkomst inschrijver" is not
    scanned as if somebody were called so. Everywhere else a key is text like
    any other: what a person types and what the model writes back cannot be
    told from a name.
    """
    if isinstance(node, str):
        tree = _json_tree(node)
        if tree is None:
            yield node
        else:
            yield from _texts(tree, machine=machine)
    elif isinstance(node, (dict, _Pairs)):
        for key, value in node if isinstance(node, _Pairs) else node.items():
            if machine and key in _ETIKETVELDEN:
                continue
            if not machine:
                yield str(key)
            yield from _texts(value, machine=machine)
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from _texts(item, machine=machine)
    elif node is not None and not isinstance(node, (bool, int, float)):
        yield str(node)


def _message_texts(
    message: dict[str, Any], *, labels: bool, label_tools: frozenset[str] = frozenset()
) -> Iterator[str]:
    """The texts of one message. `labels=False` leaves the keys and label fields
    out of the result of a tool in `label_tools` (the name check, #1154, #1986);
    `labels=True` reads them too (the pattern checks: an e-mail address in a
    column title is a fault to see)."""
    tool = message.get("role") == "tool" and not labels
    machine = tool and message.get("name") in label_tools
    for key, value in message.items():
        if tool and key in _ETIKETVELDEN:
            continue  # the `name` of a tool message is the tool's own name
        yield from _texts(value, machine=machine)


@dataclass(frozen=True)
class _Hit:
    """One thing the guard objects to: what kind, in which message, which text."""

    kind: str
    message: int
    found: str


def _hits(messages: Sequence[dict[str, Any]], rules: GuardRules) -> list[_Hit]:
    """Everything the guard objects to in this payload, with the message it
    stands in.

    Every check reads the texts of the payload (`_texts`), not its serialised
    form: the guard and the writer's cleaning read the same text with the same
    rule (#1969).
    """
    hits: list[_Hit] = []
    known = normal_names(rules.names()) if rules.match_names else set()
    for index, message in enumerate(messages):
        system = message.get("role") == "system"
        # Patterns: everything except the system prompt — see the module docstring.
        if not system:
            for text in _message_texts(message, labels=True):
                if rules.match_email:
                    hits += [
                        _Hit("een e-mailadres", index, m.group(0)) for m in _EMAIL.finditer(text)
                    ]
                for reason, pattern in _PATTERNS:
                    hits += [_Hit(reason, index, m.group(0)) for m in pattern.finditer(text)]
        # Names: the question and the tool results always; the system prompt only
        # when it is built from stored content (see the module docstring). #1154:
        # de etiketten van een tool-resultaat vallen buiten DEZE controle; de
        # patroon-controles hierboven lezen ze nog wel — een e-mailadres in een
        # kolomtitel is geen vals alarm maar een fout die je wil zien.
        if known and (rules.scan_prompt_names or not system):
            for text in _message_texts(message, labels=False, label_tools=rules.label_tools):
                hits += [_Hit(_NAME, index, m.group(0).lower()) for m in name_words(text, known)]
    return hits


def _reasons(hits: Sequence[_Hit]) -> list[str]:
    """The findings in the guard's own fixed order and words — what the log's
    `blocked_reason` and the callers of `findings` have always read."""
    found = [
        reason
        for reason in ("een e-mailadres", *(r for r, _p in _PATTERNS))
        if any(hit.kind == reason for hit in hits)
    ]
    names = {hit.found for hit in hits if hit.kind == _NAME}
    if names:
        # The name itself does not go into the message: it would then stand in a
        # log line and a screen, which is the thing being prevented.
        found.append(f"een naam uit de ledenadministratie ({len(names)}x)")
    return found


def findings(messages: Sequence[dict[str, Any]], rules: GuardRules) -> list[str]:
    """What the guard objects to in this payload. Empty means: send it."""
    return _reasons(_hits(messages, rules))


def _role_place(messages: Sequence[dict[str, Any]], index: int, rules: GuardRules) -> Part:
    """The place of a message by its role — for what no declared part holds."""
    role = messages[index].get("role")
    if role == "system":
        return INSTRUCTIONS
    if role == "tool":
        return rules.tool
    last_typed = max((i for i, m in enumerate(messages) if m.get("role") == "user"), default=-1)
    return rules.question if role == "user" and index == last_typed else CONVERSATION


def _places(
    messages: Sequence[dict[str, Any]], rules: GuardRules, hits: Sequence[_Hit]
) -> list[Part]:
    """The parts of the payload the hits stand in, each once, in the payload's
    order (#1969).

    A capability's own parts first: a part holds a hit when its text stands in
    the hit's message and the same check finds the same thing in it. What no
    part holds is placed by the role of its message — so a payload whose parts
    nobody declared still says "your question" or "what Raakje looked up".
    """
    known = normal_names(rules.names()) if rules.match_names else set()

    def found_in(text: str) -> set[tuple[str, str]]:
        found = {(_NAME, m.group(0).lower()) for m in name_words(text, known)}
        if rules.match_email:
            found |= {("een e-mailadres", m.group(0)) for m in _EMAIL.finditer(text)}
        for reason, pattern in _PATTERNS:
            found |= {(reason, m.group(0)) for m in pattern.finditer(text)}
        return found

    declared = [(part, found_in(part.text)) for part in rules.parts() if part.text]
    places: list[Part] = []
    for hit in hits:
        content = messages[hit.message].get("content")
        # A part holds this hit when its text stands in the hit's own message and
        # the same check finds the same thing in it. A word that also stands in a
        # part of ANOTHER message is not that part's.
        holders = [
            part
            for part, found in declared
            if isinstance(content, str) and part.text in content and (hit.kind, hit.found) in found
        ]
        for place in holders or [_role_place(messages, hit.message, rules)]:
            if place not in places:
                places.append(place)
    return places


def _all_of(words: Sequence[str]) -> str:
    """ "a", "a en b", "a, b en c"."""
    words = list(dict.fromkeys(words))
    return words[0] if len(words) == 1 else ", ".join(words[:-1]) + " en " + words[-1]


def refusal(messages: Sequence[dict[str, Any]], rules: GuardRules) -> SeamBlocked | None:
    """The refusal of this payload — its sentence for the screen says in which
    part the hit stands and what the reader can do there — or None: send it."""
    hits = _hits(messages, rules)
    if not hits:
        return None
    places = _places(messages, rules, hits)
    said = [_NAME if hit.kind == _NAME else _SAID[hit.kind] for hit in hits]
    advice = " ".join(dict.fromkeys(place.advice for place in places if place.advice))
    blocked = SeamBlocked(
        rules.message.format(
            waar=_all_of([place.where for place in places]),
            reden=_all_of(said),
            advies=f" {advice}" if advice else "",
        ),
        places=tuple(place.where for place in places),
        link=next((place.link for place in places if place.link), None),
    )
    return blocked


def _ms_since(begin: float) -> int:
    return int(round((time.monotonic() - begin) * 1000))


class GuardedProvider(LLMProvider):
    """Wraps any provider: scan, log, then send — in that order.

    The order is the point. A payload that is blocked is logged as blocked, so the
    one call you most want a record of is the one that never happened.
    """

    def __init__(
        self, inner: LLMProvider, rules: GuardRules, sink: Optional[Callable[..., None]] = None
    ) -> None:
        self._inner = inner
        self._rules = rules
        self._sink = sink
        self.name = getattr(inner, "name", "guarded")
        #: The payloads this provider sent, in order — what the "wat zag Mistral"
        #: fold-out shows for the answer being rendered.
        self.sent: list[str] = []
        #: The block of `fields` the last call rendered (empty before one): what a
        #: caller reads for its own sources, so the text that went and the text it
        #: checks against are one (CR-33 F6).
        self.fields_text = ""
        #: Surface and capability of this provider's calls, for a log line about
        #: what came back (#1968).
        self.log_name = "/".join(
            str(getattr(part, "value", part) or "-") for part in (rules.surface, rules.capability)
        )

    def complete(
        self, messages, tools=None, tool_choice=None, json_answer: bool = False, fields=()
    ) -> AssistantMessage:
        """One call through the seam: classify the `fields`, scan, log, then send.

        `fields` (CR-33 F6) are the stored values the caller hands as `(attribute key,
        value)` pairs instead of formatting them into the prompt: the classification of
        each key for this call's surface is applied first, a key that may not go is
        refused before anything is scanned or sent (and logged as blocked, with the key
        and never the value), and the rendered block takes the place of `FIELDS_MARK`
        in the messages (`chatbot.fields`)."""
        if fields:
            from .fields import FieldRefused, place_fields, render_fields

            try:
                block = render_fields(fields, self._rules)
            except FieldRefused as refused:
                reason = f"gegeven {refused.key}: {refused.why}"
                logger.warning(
                    "Naadwachter weigerde een gegeven (%s/%s): %s",
                    self._rules.surface,
                    self._rules.capability or "-",
                    reason,
                )
                self._log(payload_text(messages), blocked_reason=reason)
                raise
            self.fields_text = block
            messages = place_fields(messages, block)
        text = payload_text(messages)
        blocked = refusal(messages, self._rules)
        if blocked is not None:
            # What was found, and in which part — never the word itself (#1969).
            reden = ", ".join(findings(messages, self._rules))
            reden = f"{reden} — in: {'; '.join(blocked.places)}"
            logger.warning(
                "Naadwachter blokkeerde een uitgaande oproep (%s/%s): %s",
                self._rules.surface,
                self._rules.capability or "-",
                reden,
            )
            self._log(text, blocked_reason=reden)
            raise blocked

        self.sent.append(text)
        begin = time.monotonic()
        try:
            # The JSON setting travels only when asked (#1968): a free-text
            # chat's request is what it was.
            asked = {"json_answer": True} if json_answer else {}
            reply = self._inner.complete(messages, tools=tools, tool_choice=tool_choice, **asked)
        except Exception:
            # #978: the payload left, so the call counts — a failed call is
            # still a call the provider may bill.
            self._log(text, status=AiStatus.ERROR, duration_ms=_ms_since(begin))
            raise
        self._log(
            text,
            usage=getattr(reply, "usage", None),
            duration_ms=_ms_since(begin),
            provider_request_id=getattr(reply, "request_id", "") or "",
        )
        return reply

    def _log(
        self,
        text: str,
        *,
        blocked_reason: str = "",
        usage: Optional[dict[str, int]] = None,
        status: Optional[AiStatus] = None,
        duration_ms: Optional[int] = None,
        provider_request_id: str = "",
    ) -> None:
        if self._sink is None:
            return
        try:
            self._sink(
                surface=self._rules.surface,
                capability=self._rules.capability,
                model=getattr(self._inner, "model", "") or self.name,
                payload=text,
                blocked_reason=blocked_reason,
                usage=usage or {},
                provider=getattr(self._inner, "name", "") or None,
                endpoint=getattr(self._inner, "endpoint", "") or "",
                provider_request_id=provider_request_id,
                status=status or (AiStatus.BLOCKED if blocked_reason else AiStatus.OK),
                duration_ms=duration_ms,
            )
        except Exception:  # pragma: no cover - a log must not break an answer
            logger.exception("Kon de uitgaande AI-oproep niet loggen")
