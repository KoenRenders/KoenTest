"""Characterisation of every field type on every form screen (CR-12 phase 4).

Written BEFORE the form builder's fourteen `field_type` comparisons leave the
templates, on Koen's condition of 26 September 2026: "first enough GUI tests to
make sure everything that worked before keeps working with the new release".
So these tests describe what the screens rendered before, not what they should
render, and the refactor that follows must not change them.

**"Before" is master, not this branch.** The snapshots were recorded by running
this file on `origin/master` (17c968d1, v2.6.0 plus #1211), where `field_type`
is still a plain string. Recording them on the branch would have frozen what
phase 4 had already broken — and it had: the print route handed the
templates the raw `FormField`, whose `field_type` is a `FieldType` member since
phase 4, so every `field_type == "select"` was false. Every choice, rating
scale and info block printed as an empty line. The print now goes through the
`ScreenField` adapter like the other screens and matches master again.

Against master, exactly one screen differs, on purpose, and the builder
snapshot carries it: words that used to be raw codes now come from the label
tables. The type "info" reads "Infotekst" (13 options and one badge), and the
form status reads "Concept", "Open", "Gesloten" instead of `draft`, `open`,
`closed`. Checked by replacing those words in the master snapshot: the result
is equal to this one, character for character. The public form, the edit link,
the print and the results are equal to master unchanged.

Broken on purpose to check that these tests can go red: `min` renamed to
`minimum` in the number branch of `_fb_resultaten.html` → the results test falls
over with that one line in its diff. And the print test was red on this branch
before the adapter fix, which is how the regression was found.

**After the refactor** (the fourteen comparisons became `FieldKind` flags in
`screenfields.py`) all five snapshots stayed as they were — no snapshot was
rewritten. Broken on purpose once more: `FieldKind.input_type` made to answer
"text" for every type → the public form and the edit link fall over on the
e-mail and phone inputs.

One form carries one field of every type, a choice with an "Anders" option, a
jump to a second section and a submission that answers every question. Six
screens render it:

| Screen | Route | Region compared |
|---|---|---|
| public form | `/formulier/{token}` | every `data-veld` block |
| edit link | `/formulier/{token}/edit/{edit_token}` | every `data-veld` block, answers filled in |
| print | `/admin/formulieren/{id}/afdruk` | the body |
| results | `/admin/formulieren/{id}/resultaten` | the list of questions |
| builder | `/admin/formulieren/{id}` | `#fb-detail` |

The region is compared as normalised HTML against a file in
`tests/snapshots/form_field_types/`. Normalised means: whitespace between tags
collapsed, the row ids of this test replaced by names (`<F:rating>`), and
tokens masked. Nothing else — a changed class, attribute or word is a
difference.

To rewrite the snapshots after an intended change: `SNAPSHOT_UPDATE=1 pytest
tests/test_form_field_types_characterisation.py`, and read the diff before
committing it. An unread snapshot update is a test switched off.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.forms.models import (
    Form,
    FormField,
    FormFieldOption,
    FormSection,
    FormSubmission,
    FormSubmissionAnswer,
)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered

SNAPSHOTS = Path(__file__).parent / "snapshots" / "form_field_types"

#: High fixed ids, so masking them can never hit a number the page renders on
#: its own (a rating scale of 1…5, a count). Name → id.
BASE = 970_000
FORM_ID = BASE
SECTION_IDS = {"one": BASE + 1, "two": BASE + 2}
SUBMISSION_ID = BASE + 3
SHARE_TOKEN = "characterisation-share-token"
EDIT_TOKEN = "characterisation-edit-token"

#: One field per type, in this order. Extra columns per type exercise the
#: branches the builder and the public form take on them.
FIELDS = [
    ("text", dict(label="Korte vraag", required=True, help_text="Hulp bij tekst",
                  min_length=2, max_length=40)),
    ("textarea", dict(label="Lange vraag", min_length=5, max_length=500)),
    ("number", dict(label="Getal", min_value=Decimal("1"), max_value=Decimal("10"))),
    ("email", dict(label="Mailadres", required=True)),
    ("phone", dict(label="Telefoon")),
    ("select", dict(label="Keuzelijst")),
    ("radio", dict(label="Eén keuze", required=True)),
    ("checkbox", dict(label="Meerdere keuzes")),
    ("rating", dict(label="Score", rating_max=4, rating_low_label="slecht",
                    rating_high_label="goed")),
    ("info", dict(label="Ter info", help_text="Dit is uitleg")),
]
FIELD_IDS = {kind: BASE + 10 + i for i, (kind, _) in enumerate(FIELDS)}

#: Options per choice field: (name, label, extra). The radio carries the
#: "Anders" option and the jump to section two.
OPTIONS = {
    "select": [("a", "Optie A", {}), ("b", "Optie B", {})],
    "radio": [("ja", "Ja", {}),
              ("verder", "Ga verder", {"skip_to_section_id": SECTION_IDS["two"]}),
              ("anders", "Anders", {"is_other": True})],
    "checkbox": [("x", "Vink X", {}), ("y", "Vink Y", {}),
                 ("anders", "Anders", {"is_other": True})],
}
OPTION_IDS = {}
_next = BASE + 100
for _kind, _options in OPTIONS.items():
    for _name, _label, _extra in _options:
        OPTION_IDS[(_kind, _name)] = _next
        _next += 1


def _names() -> dict[int, str]:
    names = {FORM_ID: "<FORM>", SUBMISSION_ID: "<SUBMISSION>"}
    names.update({i: f"<S:{n}>" for n, i in SECTION_IDS.items()})
    names.update({i: f"<F:{k}>" for k, i in FIELD_IDS.items()})
    names.update({i: f"<O:{k}.{n}>" for (k, n), i in OPTION_IDS.items()})
    return names


@pytest.fixture
def form(db_session):
    tenant = 2
    f = Form(id=FORM_ID, tenant_id=tenant, title="Karakterisering",
             description="Elk veldtype op elk scherm", share_token=SHARE_TOKEN,
             status="open", allow_edit=True)
    db_session.add(f)
    db_session.flush()
    db_session.add(FormSection(id=SECTION_IDS["one"], tenant_id=tenant, form_id=f.id,
                               title="Eerste deel", position=0))
    db_session.add(FormSection(id=SECTION_IDS["two"], tenant_id=tenant, form_id=f.id,
                               title="Tweede deel", position=1))
    db_session.flush()
    for position, (kind, extra) in enumerate(FIELDS):
        db_session.add(FormField(id=FIELD_IDS[kind], tenant_id=tenant, form_id=f.id,
                                 section_id=SECTION_IDS["one"], field_type=kind,
                                 position=position, **extra))
    db_session.add(FormField(id=BASE + 50, tenant_id=tenant, form_id=f.id,
                             section_id=SECTION_IDS["two"], field_type="text",
                             label="Vraag in deel twee", position=0))
    db_session.flush()
    for kind, options in OPTIONS.items():
        for position, (name, label, extra) in enumerate(options):
            db_session.add(FormFieldOption(id=OPTION_IDS[(kind, name)], tenant_id=tenant,
                                           field_id=FIELD_IDS[kind], label=label,
                                           position=position, **extra))
    db_session.flush()

    submission = FormSubmission(
        id=SUBMISSION_ID, tenant_id=tenant, form_id=f.id, submitter_name="Proef",
        submitter_email="proef@example.org", edit_token=EDIT_TOKEN,
        submitted_at=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc))
    db_session.add(submission)
    db_session.flush()
    answers = [
        dict(field_id=FIELD_IDS["text"], value_text="Een antwoord"),
        dict(field_id=FIELD_IDS["textarea"], value_text="Een lang antwoord"),
        dict(field_id=FIELD_IDS["number"], value_number=Decimal("7")),
        dict(field_id=FIELD_IDS["email"], value_text="antwoord@example.org"),
        dict(field_id=FIELD_IDS["phone"], value_text="0400 00 00 00"),
        dict(field_id=FIELD_IDS["select"], value_option_id=OPTION_IDS[("select", "b")]),
        dict(field_id=FIELD_IDS["radio"], value_option_id=OPTION_IDS[("radio", "anders")],
             value_text="Iets anders"),
        dict(field_id=FIELD_IDS["checkbox"], value_option_id=OPTION_IDS[("checkbox", "x")]),
        dict(field_id=FIELD_IDS["checkbox"],
             value_option_id=OPTION_IDS[("checkbox", "anders")], value_text="Nog iets"),
        dict(field_id=FIELD_IDS["rating"], value_rating=3),
    ]
    for answer in answers:
        db_session.add(FormSubmissionAnswer(tenant_id=tenant, submission_id=SUBMISSION_ID,
                                            **answer))
    db_session.flush()
    return f


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


# ── Extracting and normalising a region ──────────────────────────────────────

_TAG = re.compile(r"<(/?)([a-zA-Z][a-zA-Z0-9]*)\b[^>]*?(/?)>")
_VOID = {"input", "br", "img", "hr", "meta", "link", "source", "wbr", "area",
         "base", "col", "embed", "param", "track"}


def _element_at(html: str, start: int) -> str:
    """The element whose opening tag starts at `start`, up to its own close."""
    first = _TAG.match(html, start)
    assert first, f"no tag at {start}"
    name = first.group(2).lower()
    depth = 0
    for m in _TAG.finditer(html, start):
        if m.group(2).lower() != name or m.group(3):
            continue
        depth += -1 if m.group(1) else 1
        if depth == 0:
            return html[start:m.end()]
    raise AssertionError(f"<{name}> at {start} is never closed")


def _elements(html: str, opening: str) -> list[str]:
    starts = [m.start() for m in re.finditer(opening, html)]
    assert starts, f"the screen has no {opening!r} — is this test still looking?"
    return [_element_at(html, s) for s in starts]


def _normalise(fragment: str) -> str:
    text = fragment
    for number, name in sorted(_names().items(), key=lambda kv: -kv[0]):
        text = re.sub(rf"(?<!\d){number}(?!\d)", name, text)
    text = re.sub(r"[A-Za-z0-9_\-.]{40,}", "<TOKEN>", text)
    text = re.sub(r">\s+<", ">\n<", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return text.strip() + "\n"


def _compare(screen: str, fragment: str) -> None:
    path = SNAPSHOTS / f"{screen}.html"
    got = _normalise(fragment)
    if os.environ.get("SNAPSHOT_UPDATE") == "1":
        path.write_text(got, encoding="utf-8")
    assert path.exists(), f"no snapshot for {screen}; run with SNAPSHOT_UPDATE=1"
    want = path.read_text(encoding="utf-8")
    if got != want:
        import difflib

        diff = "".join(difflib.unified_diff(want.splitlines(True), got.splitlines(True),
                                            "snapshot", "rendered", n=2))
        pytest.fail(f"{screen} renders differently than before:\n{diff[:6000]}")


# ── The screens ──────────────────────────────────────────────────────────────

def test_the_public_form_renders_every_type_as_before(client, form):
    page = client.get(f"/formulier/{SHARE_TOKEN}")
    assert page.status_code == 200
    blocks = _elements(page.text, r'<div data-veld="')
    assert len(blocks) == len(FIELDS) + 1, "one block per question"
    _compare("public", "\n".join(blocks))


def test_the_edit_link_renders_every_answer_as_before(client, form):
    page = client.get(f"/formulier/{SHARE_TOKEN}/edit/{EDIT_TOKEN}")
    assert page.status_code == 200
    blocks = _elements(page.text, r'<div data-veld="')
    assert "Een antwoord" in page.text, "the edit link shows the stored answers"
    _compare("edit", "\n".join(blocks))


def test_the_print_renders_every_type_as_before(client, form):
    _login(client)
    page = client.get(f"/admin/formulieren/{FORM_ID}/afdruk")
    assert page.status_code == 200
    [body] = _elements(page.text, r"<body\b")
    _compare("print", body)


def test_the_results_render_every_type_as_before(client, form):
    _login(client)
    page = client.get(f"/admin/formulieren/{FORM_ID}/resultaten")
    assert page.status_code == 200
    [results] = _elements(page.text, r'<div class="space-y-5">')
    assert "Iets anders" in results, "the Anders text is part of the results"
    _compare("results", results)


def test_the_builder_renders_every_type_as_before(client, form):
    _login(client)
    page = client.get(f"/admin/formulieren/{FORM_ID}")
    assert page.status_code == 200
    [detail] = _elements(page.text, r'<div[^>]*\bid="fb-detail"')
    _compare("builder", detail)
