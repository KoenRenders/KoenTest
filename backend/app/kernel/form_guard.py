"""Public forms against automated submissions: a honeypot and a signed time (#1297).

Koen, 29 September 2026: about ten spam messages through the contact form on PROD.
Measured there: 25 submissions in three days, each a name of exactly ten letters and
a message of exactly thirty characters, one to three an hour, day and night — an
automated probe, well under the per-IP limit of ten a minute, so that limit never
saw it. Every one of them also opened a task for the board.

Two checks, both in our own backend (Europe First: no reCAPTCHA, no Turnstile — they
send visitor data to a service outside the EU):

- **the honeypot** — a field people do not see and simple bots fill in;
- **the signed time** — every public form carries the moment it was rendered,
  signed with the app's secret. A submission without it did not come from our
  form; one inside `MIN_SECONDS` came faster than anyone can type.

A refused submission gets the ordinary thanks and leaves nothing behind: no row, no
task, no mail. So the bot learns nothing. It is logged with its reason and an IP
prefix, never with its content, so the refusals can be counted.

The checks live in the services (`submit_bericht`, the public form's submit,
`subscribe_public`), which take a `Proof`: a route cannot forget them, and the JSON
way in falls under them too. A caller that is not a visitor's form — the chatbot,
which has no form to load — says so with `TRUSTED`, visibly, in its own line.

`MIN_SECONDS` is the trap to avoid: too strict and a person is refused in silence.
The e2e of this issue sends like a quick person and must pass; it caught a first
choice of three seconds as too strict.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import time
from dataclasses import dataclass

from app.kernel.codes import TechnicalEnum

logger = logging.getLogger(__name__)

#: The honeypot's field name. `website`, because that is what simple bots fill in.
#: The newsletter form used this name before #1297; every form now shares it.
HONEYPOT_FIELD = "website"
#: The signed render time.
TOKEN_FIELD = "form_ts"
#: Faster than this after rendering is not a person typing. Two and not three:
#: the e2e of this issue, typing a public form at 60 ms a key with the name and
#: address short, sent after 1.8 s and was dropped at three — and a browser that
#: autofills the name and address makes a real person that quick. Two still
#: catches every script that posts as soon as the page has loaded.
MIN_SECONDS = 2
#: Older than this is not a page someone still has open. Generous on purpose: a
#: tab left open over a weekend should still send; a refusal is silent.
MAX_AGE_SECONDS = 7 * 24 * 3600

_PURPOSE = b"form-guard/1297"


class Refusal(TechnicalEnum):
    """Why a public submission was dropped. Logged, never shown and never stored."""

    HONEYPOT = "honeypot"
    NO_TOKEN = "no_token"
    BAD_TOKEN = "bad_token"
    TOO_FAST = "too_fast"
    EXPIRED = "expired"


@dataclass(frozen=True)
class Proof:
    """What a submitted public form brings to show a person sent it."""

    honeypot: str = ""
    token: str = ""
    #: For the log line only, reduced to a prefix there.
    client_ip: str = ""

    @classmethod
    def from_values(cls, values, client_ip: str = "") -> Proof:
        """From a submitted form (or any mapping with the two field names)."""

        def text(name: str) -> str:
            value = values.get(name)
            return value if isinstance(value, str) else ""

        return cls(honeypot=text(HONEYPOT_FIELD), token=text(TOKEN_FIELD), client_ip=client_ip)

    @classmethod
    def from_request(cls, request, values) -> Proof:
        """From a submitted form, with the client address the rate limiter trusts."""
        from app.limiter import client_ip

        return cls.from_values(values, client_ip(request))


class _Trusted:
    """Marker for a caller that is not a visitor's form (the chatbot)."""

    def __repr__(self) -> str:
        return "TRUSTED"


TRUSTED = _Trusted()


def _secret() -> bytes:
    from app.config import settings

    return settings.secret_key.encode()


def _sign(timestamp: int) -> str:
    message = _PURPOSE + b":" + str(timestamp).encode()
    return hmac.new(_secret(), message, hashlib.sha256).hexdigest()[:32]


def issue_token(now: float | None = None) -> str:
    """The signed render time, for the form's hidden field."""
    timestamp = int(time.time() if now is None else now)
    return f"{timestamp}.{_sign(timestamp)}"


def refusal(proof: Proof | _Trusted, now: float | None = None) -> Refusal | None:
    """Why this submission is not a person's, or None."""
    if isinstance(proof, _Trusted):
        return None
    if proof.honeypot.strip():
        return Refusal.HONEYPOT
    if not proof.token:
        return Refusal.NO_TOKEN
    stamp, _, signature = proof.token.partition(".")
    if not stamp.isdigit() or not hmac.compare_digest(signature, _sign(int(stamp))):
        return Refusal.BAD_TOKEN
    age = (time.time() if now is None else now) - int(stamp)
    if age < MIN_SECONDS:
        return Refusal.TOO_FAST
    if age > MAX_AGE_SECONDS:
        return Refusal.EXPIRED
    return None


def ip_prefix(ip: str) -> str:
    """The network, not the address: /24 for IPv4, /48 for IPv6."""
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return "unknown"
    bits = 24 if address.version == 4 else 48
    return str(ipaddress.ip_network(f"{address}/{bits}", strict=False))


def refused(proof: Proof | _Trusted, where: str, now: float | None = None) -> bool:
    """True when the submission must be dropped; logs the reason, never the content."""
    reason = refusal(proof, now)
    if reason is None:
        return False
    client_ip = proof.client_ip if isinstance(proof, Proof) else ""
    logger.warning(
        "form_guard: dropped a submission to %s (%s) from %s",
        where,
        reason.value,
        ip_prefix(client_ip),
    )
    return True
