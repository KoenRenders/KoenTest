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

Honest limits, stated here rather than discovered later: a nickname, an initial or
a typo slips the name match, and a family name that is also a street name gives a
false block. The first is why the payload log exists; the second is the safe side
of the trade and is resolved by rephrasing.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Sequence

from .providers.base import AssistantMessage, LLMProvider

logger = logging.getLogger(__name__)

# The two surfaces. A capability pack names one; the guard reads its rules from it.
SURFACE_PUBLIC = "public"
SURFACE_ADMIN = "admin"


class SeamBlocked(RuntimeError):
    """The guard refused to send this payload. The message is for the screen."""


# Patterns that have no business in outbound payload text, whichever surface sends
# it — with one exception per §5.8, the e-mail address a visitor types into the
# public contact path. Each is deliberately loose: a false block costs a rephrase,
# a miss costs a leak.
_EMAIL = re.compile(r"[^\s@<>()\[\]]+@[^\s@<>()\[\]]+\.[a-zA-Z]{2,}")
# Belgian shapes with and without the country code, spaces/dots/dashes allowed:
# 0473 12 34 56, +32 473 123 456, 016/12.34.56.
_PHONE = re.compile(r"(?:\+32|0032|\b0)[\s./-]?\d(?:[\s./-]?\d){7,9}\b")
# An IBAN: two letters, two check digits, then up to 30 alphanumerics in groups.
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}\b")

_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("een telefoonnummer", _PHONE),
    ("een rekeningnummer", _IBAN),
)

_WORD = re.compile(r"[a-zà-ÿ]+")


def redact(text: str) -> str:
    """Replace what the guard refuses by a neutral placeholder (#984).

    For a capability that sends content it did not write itself — flyer text,
    meeting notes — and would otherwise be blocked by an address somebody put
    there. The SAME patterns as the guard, so a redacted text never trips it on
    these; names are the caller's business (the guard reads them from mdm).
    """
    if not text:
        return text or ""
    text = _EMAIL.sub("[e-mailadres]", text)
    text = _IBAN.sub("[rekeningnummer]", text)
    return _PHONE.sub("[telefoonnummer]", text)

_ADMIN_MESSAGE = (
    "Deze vraag is niet verstuurd: er stond een persoonsgegeven in ({reden}). "
    "Raakje stuurt geen namen, e-mailadressen, telefoonnummers of "
    "rekeningnummers naar het taalmodel. Herformuleer de vraag zonder dat "
    "gegeven — vraag bijvoorbeeld naar een groep in plaats van naar één persoon."
)

# De publieke bot krijgt een andere tekst, want hij weigert iets anders. Naam en
# e-mailadres mág een bezoeker geven (daar is het contactpad voor); een
# telefoonnummer of rekeningnummer heeft Raakje nooit nodig, en wat hij niet nodig
# heeft, stuurt hij niet door.
_PUBLIC_MESSAGE = (
    "Dat bericht is niet verstuurd: er stond {reden} in. Raakje heeft dat niet "
    "nodig — laat het weg, dan geeft het bestuur je gerust een antwoord. Wil je "
    "teruggebeld worden, schrijf dat er dan gewoon bij."
)


@dataclass
class GuardRules:
    """What the guard checks for one capability.

    ``names`` is a callable and not a list: the name set is a database read, and a
    guard that loads it whether or not it is used would make the public bot pay for
    a check it does not run.
    """

    surface: str
    capability: str = ""
    match_names: bool = False
    match_email: bool = False
    #: Of het system-bericht meegescand wordt op namen. Standaard aan: wie er niets
    #: over zegt, krijgt de volledige controle. Uit mag alleen wanneer de prompt
    #: machinaal gegenereerd is en dus geen opgeslagen waarde kan dragen.
    scan_prompt_names: bool = True
    names: Callable[[], set[str]] = field(default=lambda: set())
    message: str = _ADMIN_MESSAGE


def public_rules() -> GuardRules:
    """The public bot: patterns only. Its contact path exists to collect a name."""
    return GuardRules(surface=SURFACE_PUBLIC, match_names=False,
                      match_email=False, message=_PUBLIC_MESSAGE)


def admin_rules(names: Callable[[], set[str]], *, capability: str,
                scan_prompt_names: bool = True) -> GuardRules:
    """The back office: everything on. Nothing here is anybody's own name to give.

    ``scan_prompt_names=False`` is for a pack whose system prompt is rendered from
    a declaration rather than from stored content — see the module docstring, and
    prove it with a test before passing it.
    """
    return GuardRules(surface=SURFACE_ADMIN, capability=capability,
                      match_names=True, match_email=True,
                      scan_prompt_names=scan_prompt_names, names=names)


def payload_text(messages: Sequence[dict[str, Any]], *,
                 include_system: bool = True) -> str:
    """The outbound messages as one string, tool calls included.

    Serialised rather than walked field by field: a payload shape that grows a
    field would otherwise slip past the scan unread, which is exactly the class of
    mistake this guard exists for.
    """
    selected = [m for m in messages
                if include_system or m.get("role") != "system"]
    return json.dumps(selected, ensure_ascii=False, default=str)


def findings(messages: Sequence[dict[str, Any]], rules: GuardRules) -> list[str]:
    """What the guard objects to in this payload. Empty means: send it."""
    found: list[str] = []

    # Patterns: everything except the system prompt — see the module docstring.
    typed = payload_text(messages, include_system=False)
    if rules.match_email and _EMAIL.search(typed):
        found.append("een e-mailadres")
    for reason, pattern in _PATTERNS:
        if pattern.search(typed):
            found.append(reason)

    # Names: the question and the tool results always; the system prompt only when
    # it is built from stored content (see the module docstring).
    if rules.match_names:
        known = rules.names()
        if known:
            whole = payload_text(
                messages, include_system=rules.scan_prompt_names).lower()
            words = {w for w in _WORD.findall(whole) if len(w) >= 3}
            hit = sorted(words & known)
            if hit:
                # The name itself does not go into the message: it would then stand
                # in a log line and a screen, which is the thing being prevented.
                found.append(f"een naam uit de ledenadministratie ({len(hit)}x)")
    return found


def _ms_since(begin: float) -> int:
    return int(round((time.monotonic() - begin) * 1000))


class GuardedProvider(LLMProvider):
    """Wraps any provider: scan, log, then send — in that order.

    The order is the point. A payload that is blocked is logged as blocked, so the
    one call you most want a record of is the one that never happened.
    """

    def __init__(self, inner: LLMProvider, rules: GuardRules,
                 sink: Optional[Callable[..., None]] = None) -> None:
        self._inner = inner
        self._rules = rules
        self._sink = sink
        self.name = getattr(inner, "name", "guarded")
        #: The payloads this provider sent, in order — what the "wat zag Mistral"
        #: fold-out shows for the answer being rendered.
        self.sent: list[str] = []

    def complete(self, messages, tools=None, tool_choice=None) -> AssistantMessage:
        text = payload_text(messages)
        reasons = findings(messages, self._rules)
        if reasons:
            reden = ", ".join(reasons)
            logger.warning(
                "Naadwachter blokkeerde een uitgaande oproep (%s/%s): %s",
                self._rules.surface, self._rules.capability or "-", reden,
            )
            self._log(text, blocked_reason=reden)
            raise SeamBlocked(self._rules.message.format(reden=reden))

        self.sent.append(text)
        begin = time.monotonic()
        try:
            reply = self._inner.complete(messages, tools=tools, tool_choice=tool_choice)
        except Exception:
            # #978: the payload left, so the call counts — a failed call is
            # still a call the provider may bill.
            self._log(text, status="error", duration_ms=_ms_since(begin))
            raise
        self._log(text, usage=getattr(reply, "usage", None),
                  duration_ms=_ms_since(begin),
                  provider_request_id=getattr(reply, "request_id", "") or "")
        return reply

    def _log(self, text: str, *, blocked_reason: str = "",
             usage: Optional[dict[str, int]] = None, status: str = "",
             duration_ms: Optional[int] = None,
             provider_request_id: str = "") -> None:
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
                provider=getattr(self._inner, "name", "") or "",
                endpoint=getattr(self._inner, "endpoint", "") or "",
                provider_request_id=provider_request_id,
                status=status or ("blocked" if blocked_reason else "ok"),
                duration_ms=duration_ms,
            )
        except Exception:  # pragma: no cover - a log must not break an answer
            logger.exception("Kon de uitgaande AI-oproep niet loggen")
