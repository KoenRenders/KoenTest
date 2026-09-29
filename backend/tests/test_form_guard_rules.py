"""#1297 — the rules of the public-form guard, on their own.

`app/kernel/form_guard.py` decides whether a public submission is a person's: the
honeypot empty, the signed render time present, genuine, at least `MIN_SECONDS`
old and not older than `MAX_AGE_SECONDS`. The services call it; these tests hold
the rules, `tests/integration/test_form_guard_ways_in.py` holds the wiring.

The log line is part of the rule: it names the reason and a network prefix,
never the full address and never the content.

Proven red (29 September 2026), additively in `form_guard.py`:
- `return None` added at the top of `refusal` → every refusal test here fails;
- `MIN_SECONDS = 60` added after the constant → "a person after a few seconds"
  fails, and the e2e of this issue with it — the too-strict limit the issue warns of.
"""

import logging

import pytest

from app.kernel import form_guard
from app.kernel.form_guard import (
    MAX_AGE_SECONDS,
    MIN_SECONDS,
    TRUSTED,
    Proof,
    Refusal,
    ip_prefix,
    issue_token,
    refusal,
)

pytestmark = pytest.mark.ui_agnostisch

NOW = 1_790_000_000.0


def _loaded(seconds_ago: float, **extra) -> Proof:
    return Proof(token=issue_token(now=NOW - seconds_ago), **extra)


#: A quick person with a short message. Fixed, not derived from MIN_SECONDS: a
#: limit raised past it must fail here, not move along with it.
QUICK_PERSON_SECONDS = 5


def test_a_person_after_a_few_seconds_passes():
    assert refusal(_loaded(QUICK_PERSON_SECONDS), now=NOW) is None
    assert refusal(_loaded(3600), now=NOW) is None
    # A tab left open over a weekend still sends.
    assert refusal(_loaded(3 * 24 * 3600), now=NOW) is None


@pytest.mark.parametrize(
    "proof, reason",
    [
        (Proof(honeypot="http://spam.example", token=issue_token(now=NOW - 60)), Refusal.HONEYPOT),
        (Proof(), Refusal.NO_TOKEN),
        (Proof(token="1790000000.0000000000000000000000000000000"), Refusal.BAD_TOKEN),
        (Proof(token="not-a-token"), Refusal.BAD_TOKEN),
        (_loaded(0.5), Refusal.TOO_FAST),
        (_loaded(MIN_SECONDS - 1), Refusal.TOO_FAST),
        (_loaded(MAX_AGE_SECONDS + 60), Refusal.EXPIRED),
    ],
    ids=[
        "honeypot",
        "no-token",
        "forged-signature",
        "garbage",
        "too-fast",
        "just-too-fast",
        "expired",
    ],
)
def test_what_is_not_a_person_is_refused(proof, reason):
    assert refusal(proof, now=NOW) is reason


def test_a_token_moved_to_another_time_is_refused():
    """The signature covers the time: an older stamp with a fresh signature fails."""
    stamp, signature = issue_token(now=NOW - 1).split(".")
    moved = Proof(token=f"{int(stamp) - 600}.{signature}")
    assert refusal(moved, now=NOW) is Refusal.BAD_TOKEN


def test_the_chatbot_is_trusted_by_name():
    assert refusal(TRUSTED, now=NOW) is None


def test_the_log_names_reason_and_prefix_never_address_or_content(caplog):
    caplog.set_level(logging.WARNING, logger=form_guard.__name__)
    proof = Proof(honeypot="buy cheap watches", client_ip="203.0.113.77")

    assert form_guard.refused(proof, "berichten", now=NOW) is True

    line = caplog.records[-1].getMessage()
    assert "berichten" in line and "honeypot" in line and "203.0.113.0/24" in line, line
    assert "203.0.113.77" not in line and "watches" not in line, line


@pytest.mark.parametrize(
    "ip, prefix",
    [
        ("198.51.100.23", "198.51.100.0/24"),
        ("2001:db8:1234:5678::1", "2001:db8:1234::/48"),
        ("", "unknown"),
        ("not-an-ip", "unknown"),
    ],
)
def test_the_prefix_is_the_network(ip, prefix):
    assert ip_prefix(ip) == prefix
