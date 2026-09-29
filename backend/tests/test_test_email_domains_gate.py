"""#1293 — no e-mail address in the tests outside the reserved example domains.

This repository is public. A test that needs a contact person is tempted to take
one from the material at hand — a flyer, an export — and then a real person's
name and address are published, in every clone and forever in the history. That
happened once (the design studio's contact test, #1007), and a reviewer caught
it, not a check.

So: every e-mail address in the tests — `backend/tests/`, `backend/tests_e2e/`
and each domain's `app/domains/<x>/tests/` (CR-13 phase 0b) — sits on a
domain reserved for examples (RFC 2606 / RFC 6761): `example.com`,
`example.org`, `example.net`, their subdomains, or the reserved top-level
domains `.example`, `.test`, `.invalid` and `.localhost`. None of those can ever
be anyone's mailbox. The app itself needs no other domain in its tests.

`EXEMPT` holds what was there before this gate, per file and address, each with
its reason. It may only shrink: an entry that no longer occurs in its file makes
this gate fail until it is removed, so a cleaned-up file cannot keep its
permission. Do not add to it — change the address to `example.com` instead.

Proven red (29 September 2026), each one additive and seen failing on its own
assertion:

| Violation | Failed |
|---|---|
| `"iemand@telenet.be"` added to `tests/integration/test_forms.py` | "every address is on an example domain" |
| the same added to a domain's test file (`mail/tests/test_email_log.py`) | the same test |
| a stale `EXEMPT` entry added for an address that is not in its file | "the exemptions only shrink" |
| the domain glob pointed at `*/testen/` | `bestanden()` — "0 bestanden (… app/domains/*/tests)" |

Note for the next gate over the tests: since phase 0b `bestanden()` drops a domain's
test files unless it is called with `met_tests=True`. Without it the domain half of
this scan came back empty — which is exactly what the floor is for.
"""

import re
from pathlib import Path

from tests._bestanden import bestanden

BACKEND = Path(__file__).resolve().parents[1]
ROOTS = (BACKEND / "tests", BACKEND / "tests_e2e")
DOMAINS = BACKEND / "app" / "domains"
SUFFIXES = {".py", ".html", ".md", ".json", ".csv", ".txt", ".eml", ".sh"}

EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,})")

RESERVED_DOMAINS = ("example.com", "example.org", "example.net")
RESERVED_TLDS = ("example", "test", "invalid", "localhost")

# (file relative to backend/, address) → why it is still here. Shrink only.
EXEMPT: dict[tuple[str, str], str] = {
    (
        "app/domains/mail/tests/test_email_log.py",
        "x@raak.be",
    ): "placeholder sender; raak.be is a registrable domain — move to example.com",
    (
        "tests/integration/test_member_import_upsert.py",
        "admin@raak.be",
    ): "placeholder importer; raak.be is a registrable domain — move to example.com",
    (
        "app/domains/mdm/tests/test_member_change_audit.py",
        "suske@suske.be",
    ): "comic-strip placeholder on a registrable domain — move to example.com",
    (
        "tests/integration/test_payment_name_soft_delete.py",
        "suske@suske.be",
    ): "comic-strip placeholder on a registrable domain — move to example.com",
    (
        "tests/integration/test_forms.py",
        "a@b.be",
    ): "one-letter placeholder on a registrable domain — move to example.com",
    (
        "tests/integration/test_forms.py",
        "jan@x.be",
    ): "one-letter placeholder on a registrable domain — move to example.com",
    (
        "tests/integration/test_designstudio_service.py",
        "info@example.be",
    ): "example.be is not reserved, unlike example.com — move to example.com",
    (
        "tests/integration/test_designstudio_service.py",
        "raak@example.be",
    ): "example.be is not reserved, unlike example.com — move to example.com",
}


def _is_reserved(domain: str) -> bool:
    domain = domain.lower()
    if domain.rsplit(".", 1)[-1] in RESERVED_TLDS:
        return True
    return any(domain == d or domain.endswith("." + d) for d in RESERVED_DOMAINS)


def _files() -> list[Path]:
    # Two collections, each with its own floor: since phase 0b most tests sit in
    # their domain, and a glob that lost either half must not pass for a scan.
    shared = bestanden(
        (p for root in ROOTS for p in root.rglob("*") if p.suffix in SUFFIXES),
        wat="the text files under backend/tests and backend/tests_e2e",
        minstens=100,
    )
    in_domains = bestanden(
        (p for p in DOMAINS.glob("*/tests/**/*") if p.suffix in SUFFIXES),
        wat="the text files under app/domains/*/tests",
        minstens=100,
        met_tests=True,
    )
    return shared + in_domains


def _addresses() -> dict[tuple[str, str], list[int]]:
    """Every address outside a reserved domain, with the lines it is on."""
    found: dict[tuple[str, str], list[int]] = {}
    for path in _files():
        if path == Path(__file__).resolve():
            continue  # this file names the exempted addresses, and one example
        rel = path.relative_to(BACKEND).as_posix()
        for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            for match in EMAIL.finditer(line):
                if not _is_reserved(match.group(1)):
                    found.setdefault((rel, match.group(0)), []).append(number)
    return found


def test_the_rule_tells_reserved_from_registrable():
    """The rule itself, so the gate below cannot pass by allowing everything."""
    for domain in (
        "example.com",
        "Example.org",
        "mail.example.net",
        "raak.example",
        "x.test",
        "a.invalid",
        "localhost",
    ):
        assert _is_reserved(domain) or domain == "localhost", domain
    for domain in ("gmail.com", "example.be", "notexample.com", "example.com.evil.be"):
        assert not _is_reserved(domain), domain


def test_every_address_is_on_an_example_domain():
    offenders = {key: lines for key, lines in _addresses().items() if key not in EXEMPT}
    assert not offenders, (
        "e-mail addresses outside example.com/.org/.net or a reserved TLD in the "
        "tests — this repository is public; use @example.com:\n"
        + "\n".join(
            f"  {f}:{','.join(map(str, lines))}  {a}" for (f, a), lines in sorted(offenders.items())
        )
    )


def test_the_exemptions_only_shrink():
    present = set(_addresses())
    stale = sorted(key for key in EXEMPT if key not in present)
    assert not stale, (
        "these exemptions no longer occur in their file — remove them from EXEMPT:\n"
        + "\n".join(f"  {f}  {a}" for f, a in stale)
    )
