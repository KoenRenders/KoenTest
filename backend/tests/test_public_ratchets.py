"""The gates of the public side that guard a count, as ratchets (#1591, CR-11
pilot B, P4; B7 test 2 extended to the site shell; end state §2.5, §2.6).

P1 gave the public site one shell (`test_public_shell_gate.py`: no second
header or footer, the newsletter's call once) and P2 one form page
(`test_public_form_page_gate.py`: those pages at zero). This file closes the
set for EVERY public page — each template that extends `site_base.html` and
everything it includes:

- **no button written by hand** and **no card drawn by hand**: both come from
  the kit's macros. The public pages that are not rebuilt yet (the activity
  cards, the photos, the family pages until P3) still have some; each stands
  in `tests/public_baseline.py` with its exact number, which may only fall;
- **no date tile, year heading or way back written by hand** (#1663, CR-11
  pilot C, C1; end state §2.7): they come from `_public_macros.html`
  (`date_tile`, `year_heading`, `public_back_link`). Counted by what gives one
  away: its `data-…` hook, the short-month filter of the tile, a left arrow;
- **the organisation's data are written by no page** but the one that is the
  organisation's own ("Onze organisatie"): everywhere else they stand in the
  footer's legal line;
- **no "* Verplicht veld" legend in any template** of the application, public
  or admin: the asterisk on the label says it (decision 12, point 2). At zero,
  so this one is a plain gate.

As in `test_ui_ratchets.py`: more than the baseline is red, fewer is red too
("lower the number" — room left standing is free for the next violation), and
an entry whose file is gone or clean is red ("remove the entry").

Proven red, each with an ADDITIVE violation on a real template (run, restored):
- `<button type="button">x</button>` added to `home.html` → buttons: "1 found,
  the baseline says 0";
- `<div class="bg-white rounded-2xl border p-4">x</div>` added to
  `activiteit.html` → cards;
- `{{ organisatie.iban }}` added to `home.html` → organisation fields;
- `<div data-date-tile>12</div>` added to `activiteit.html` → activity parts:
  "1 found, the baseline says 0" (and so for a year heading's hook and for
  `&larr;`, in the synthetic test);
- `<p>* Verplicht veld</p>` added to `admin_dashboard.html` → the legend.
The synthetic tests at the bottom keep those proofs without touching a page.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import pytest

from tests import public_baseline as baseline

pytestmark = pytest.mark.ui_serverrendered

APP = Path(__file__).resolve().parents[1] / "app"
SHELL = "site_base.html"

_COMMENT = re.compile(r"{#.*?#}", re.S)
_INCLUDE = re.compile(r'{%-?\s*(?:include|from)\s+"([^"]+)"')
_EXTENDS_SITE = re.compile(r'{%-?\s*extends\s+"site_base\.html"')
_BUTTON = re.compile(r'<button\b|<input\b[^>]*type="submit"')
_CARD = re.compile(
    r'class="(?=[^"]*\brounded-(?:lg|xl|2xl)\b)(?=[^"]*\bborder\b)(?=[^"]*\bbg-(?:white|surface)\b)[^"]*"'
)
_ORGANISATION = re.compile(r"\borganisatie\.(?!name\b)\w+")
_ACTIVITY_PART = re.compile(
    r"data-date-tile|data-year-heading|data-way-back|\|\s*maandkort\b|←|&larr;|‹|&lsaquo;"
)
_LEGEND = re.compile(r"\*\s*(?:</span>\s*)?Verplichte? veld|Verplichte? velden? zijn", re.I)


def _all_templates() -> dict[str, tuple[str, str]]:
    """file name → (path under app/, text without comments)."""
    found = {
        p.name: (str(p.relative_to(APP)), _COMMENT.sub("", p.read_text(encoding="utf-8")))
        for p in APP.rglob("templates/*.html")
    }
    assert len(found) > 150, f"only {len(found)} templates found — the glob looks nowhere"
    return found


def public_templates(sources: dict[str, tuple[str, str]] | None = None) -> dict[str, str]:
    """Every template of a public page: what extends the site shell, and what
    those include or import — the kit and the shell themselves left out (the
    kit is where a button is supposed to be written)."""
    sources = sources if sources is not None else _all_templates()
    seen: set[str] = set()

    def family(name: str) -> None:
        if (
            name in seen
            or name not in sources
            or name in ("_macros.html", "_public_macros.html", SHELL)
        ):
            return
        seen.add(name)
        for included in _INCLUDE.findall(sources[name][1]):
            family(included)

    for name, (_rel, text) in sources.items():
        if _EXTENDS_SITE.search(text):
            family(name)
    return {sources[name][0]: sources[name][1] for name in seen}


def hand_written_buttons(text: str) -> int:
    return len(_BUTTON.findall(text))


def hand_written_cards(text: str) -> int:
    return len(_CARD.findall(text))


def hand_written_activity_parts(text: str) -> int:
    return len(_ACTIVITY_PART.findall(text))


def organisation_fields(text: str) -> int:
    return len(_ORGANISATION.findall(text))


RULES: dict[str, tuple[Callable[[str], int], dict[str, int]]] = {
    "hand_written_buttons": (hand_written_buttons, baseline.HAND_WRITTEN_BUTTONS),
    "hand_written_cards": (hand_written_cards, baseline.HAND_WRITTEN_CARDS),
    "organisation_fields": (organisation_fields, baseline.ORGANISATION_FIELDS),
    "hand_written_activity_parts": (
        hand_written_activity_parts,
        baseline.HAND_WRITTEN_ACTIVITY_PARTS,
    ),
}


def judge(rule: str, found: dict[str, int], frozen: dict[str, int]) -> list[str]:
    """`found`: template → count for every public template (zeros included)."""
    wrong = []
    for rel, count in sorted(found.items()):
        allowed = frozen.get(rel, 0)
        if count > allowed:
            wrong.append(f"{rel}: {count} found, the baseline says {allowed} ({rule})")
        elif count < allowed and count:
            wrong.append(
                f"{rel}: {count} left, the baseline still says {allowed} — lower the number"
            )
        elif count < allowed:
            wrong.append(f"{rel}: clean now — remove the entry from the baseline ({rule})")
    for rel in sorted(set(frozen) - set(found)):
        wrong.append(f"{rel}: in the baseline of {rule}, but no template of a public page")
    return wrong


# ── The rules on the real templates ──────────────────────────────────────────


def test_the_gate_reads_the_public_pages_and_their_partials():
    """A gate that finds nothing is green forever."""
    public = public_templates()
    assert len(public) >= 30, sorted(public)
    for expected in (
        "domains/cms/templates/home.html",
        "domains/activities/templates/inschrijven.html",
        # reached only through an include of an include
        "domains/activities/templates/_inschrijf_velden.html",
        "domains/forms/templates/_formulier_veld.html",
    ):
        assert expected in public, expected
    assert not any(rel.endswith(("/_macros.html", "/" + SHELL)) for rel in public)
    assert not any("admin_" in Path(rel).name for rel in public), "an admin page counted as public"


@pytest.mark.parametrize("rule", list(RULES))
def test_the_count_only_falls(rule):
    collect, frozen = RULES[rule]
    found = {rel: collect(text) for rel, text in public_templates().items()}
    assert judge(rule, found, frozen) == []


def test_no_template_carries_a_required_field_legend():
    carrying = [rel for rel, text in _all_templates().values() if _LEGEND.search(text)]
    assert carrying == [], "the asterisk on the label says it (decision 12, point 2)"


# ── The rules on made-up templates ───────────────────────────────────────────


@pytest.mark.parametrize(
    ("rule", "violation"),
    [
        ("hand_written_buttons", '<button type="button">x</button>'),
        ("hand_written_buttons", '<input type="submit" value="x">'),
        ("hand_written_cards", '<div class="bg-white rounded-2xl shadow-sm border p-4">x</div>'),
        ("hand_written_cards", '<div class="border border-line rounded-lg bg-surface">x</div>'),
        ("organisation_fields", "{{ organisatie.iban }}"),
        ("hand_written_activity_parts", "<div data-date-tile>12</div>"),
        ("hand_written_activity_parts", "<h3 data-year-heading>2026</h3>"),
        ("hand_written_activity_parts", '<a href="/x">&larr; Terug</a>'),
        ("hand_written_activity_parts", "<span>{{ d | maandkort }}</span>"),
        # Since #1665 the lightbox's arrows are icons: a chevron typed by a public
        # template is a way back (or an arrow) written by hand again.
        ("hand_written_activity_parts", '<a href="/x">‹ Terug</a>'),
    ],
)
def test_each_collector_counts_its_violation(rule, violation):
    collect, _frozen = RULES[rule]
    clean = '{{ ui.btn_primary("x") }}{% call ui.flow_card() %}{{ organisatie.name }}{% endcall %}'
    assert collect(clean) == 0
    assert collect(clean + violation) == 1


def test_the_judge_is_red_on_more_on_less_and_on_a_stale_entry():
    frozen = {"a.html": 2}
    assert judge("r", {"a.html": 2, "b.html": 0}, frozen) == []
    assert judge("r", {"a.html": 3, "b.html": 0}, frozen) == [
        "a.html: 3 found, the baseline says 2 (r)"
    ]
    assert judge("r", {"a.html": 2, "b.html": 1}, frozen) == [
        "b.html: 1 found, the baseline says 0 (r)"
    ]
    assert judge("r", {"a.html": 1}, frozen) == [
        "a.html: 1 left, the baseline still says 2 — lower the number"
    ]
    assert judge("r", {"a.html": 0}, frozen) == [
        "a.html: clean now — remove the entry from the baseline (r)"
    ]
    assert judge("r", {"b.html": 0}, frozen) == [
        "a.html: in the baseline of r, but no template of a public page"
    ]


@pytest.mark.parametrize(
    "legend",
    [
        "<p>* Verplicht veld</p>",
        '<p><span class="x">*</span> Verplichte velden</p>',
        "Verplichte velden zijn gemarkeerd",
    ],
)
def test_a_legend_is_recognised_and_a_sentence_about_a_field_is_not(legend):
    assert _LEGEND.search(legend)
    assert not _LEGEND.search("meldt een leeg verplicht veld in de foutbanner")
