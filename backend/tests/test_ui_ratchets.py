"""The gates of CR-11 B7 that guard a count, as ratchets (#1563, pilot A, K9).

Every rule below counts something the end state refuses, per template, and
compares it with `tests/ui_baseline.py`: one exact number per file.

- more than the baseline says → red, naming the file and the rule;
- fewer → red too, with "lower the number": room that is left standing is free
  for the next violation, which is how a ratchet with slack stops being one
  (the two integers this file replaces allowed 19 raw fields and 8 raw
  checkboxes more than there were);
- a file in the baseline that is gone or clean → red, "remove the entry";
- **a pilot screen in the baseline → red.** Betalingen and the activity
  (Gegevens, Inschrijvingen, Betalingen) are on the kit; their templates stand
  at zero for every rule and stay there.

The pilot's templates are not listed here: they are what the four pilot pages
include, so a partial added to a pilot screen is a pilot template the moment it
is included.

Each rule was proven red on a real template with an additive violation, noted at
its collector; the synthetic tests at the bottom keep those proofs.
"""

import re
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from tests import ui_baseline as baseline
from tests._bestanden import bestanden

APP = Path(__file__).resolve().parents[1] / "app"

#: The kit itself and its demo page are not screens: the kit is where a raw
#: element is supposed to live, and the demo page shows the refused shapes too.
NOT_A_SCREEN = {"_macros.html", "design_system.html"}

#: The pages of pilot A. Everything they include is a pilot template.
PILOT_PAGES = (
    "domains/payment/templates/betalingen.html",
    "domains/activities/templates/admin_activiteit.html",
    "domains/activities/templates/admin_activiteit_inschrijvingen.html",
    "domains/payment/templates/admin_activiteit_betalingen.html",
)


def _without_comments(text: str) -> str:
    return re.sub(r"\{#.*?#\}", "", text, flags=re.S)


def templates() -> dict[str, str]:
    """Every screen template of the application, comments removed."""
    paths = bestanden(
        (APP / "domains").glob("*/templates/**/*.html"),
        (APP / "ui" / "templates").glob("**/*.html"),
        wat="the templates of the domains and of app/ui",
        minstens=150,
    )
    return {
        str(p.relative_to(APP)): _without_comments(p.read_text(encoding="utf-8"))
        for p in paths
        if p.name not in NOT_A_SCREEN
    }


def pilot_templates(sources: dict[str, str] | None = None) -> set[str]:
    """The pilot pages and everything they include, minus the partials the
    baseline names as included-but-not-rendered there."""
    sources = sources if sources is not None else templates()
    by_name: dict[str, str] = {}
    for rel in sources:
        by_name.setdefault(Path(rel).name, rel)
    seen: set[str] = set()
    todo = [p for p in PILOT_PAGES]
    while todo:
        rel = todo.pop()
        if rel in seen:
            continue
        assert rel in sources, f"the pilot template {rel} does not exist — PILOT_PAGES is stale"
        seen.add(rel)
        for name in re.findall(r"\{%-?\s*include\s+\"([^\"]+)\"", sources[rel]):
            if name in by_name:
                todo.append(by_name[name])
    return seen - set(baseline.INCLUDED_BY_THE_PILOT_NOT_RENDERED_THERE)


# ── The collectors: text of one template → number of violations ─────────────

_RAW_ELEMENT = re.compile(r"<(?:label|select|textarea)\b|<input\b(?![^>]*type=\"hidden\")")
_RAW_CHECKBOX = re.compile(r"<input\b[^>]*type=\"checkbox\"")
_RAW_TAG = re.compile(r"<(?:label|select|textarea|input)\b[^>]*>", re.S)
_SPACING = re.compile(
    r"(?<![\w-])(?:[a-z]+:)*-?(?:m|p)[trblxyse]?-(?:\d|\[|px|auto)|(?<![\w-])(?:[a-z]+:)*(?:gap|space)-[xy]?-?[\d\[]"
)
_SURFACE = re.compile(r"(?<![\w:-])bg-(?:white|gray-50|gray-100)(?![\w/-])")
_HEADER = re.compile(
    r"\{%-?\s*call\s+ui\.page_header\(.*?%\}(.*?)\{%-?\s*endcall\s*-?%\}",
    re.S,
)
_BUTTON = re.compile(r"ui\.(?:btn_\w+|button|link_action)\(\s*(?:_\(\s*)?[\"']([^\"']*)[\"']")
_TOOLBAR = re.compile(
    r"\{%-?\s*call\s+ui\.(?:toolbar|filter_bar)\(.*?%\}(.*?)\{%-?\s*endcall\s*-?%\}",
    re.S,
)
_TAG_CLASS = re.compile(r"<\w+\b[^>]*?\bclass=\"([^\"]*)\"", re.S)
_ROW_WIDENER = re.compile(
    r"(?<![\w-])(?:[a-z]+:)*(?:flex-nowrap|whitespace-nowrap|min-w-(?!0\b|full\b|min\b|max\b|fit\b)[\w\[\].]+)"
)
_EXTENDS_SHELL = re.compile(r"\{%-?\s*extends\s+\"admin_base\.html\"")


def raw_form_elements(text: str) -> int:
    """B7 test 8. A `<label>`, `<select>`, `<textarea>` or visible `<input>`
    written by the template; a form control comes from `ui.field`.

    Proven red by adding `<input name="x">` to `_aa_inschrijvingen_lijst.html`."""
    return len(_RAW_ELEMENT.findall(text))


def raw_checkboxes(text: str) -> int:
    """B7 test 9. A raw `type="checkbox"`; a boolean setting is a `switch`,
    several out of a list a `checkbox_group`.

    Proven red by adding `<input type="checkbox" name="x">` to `_aa_rail.html`."""
    return len(_RAW_CHECKBOX.findall(text))


def spacing_on_form_elements(text: str) -> int:
    """B7 test 8. A margin, padding, gap or space class in the opening tag of a
    raw `<label>`, `<input>`, `<select>` or `<textarea>`: a distance the
    template sets itself is a distance it can get wrong.

    Proven red by adding `<label class="mt-2">` to `_betalingen_scherm.html`
    (which trips the raw-element rule as well)."""
    return sum(len(_SPACING.findall(tag)) for tag in _RAW_TAG.findall(text))


def raw_surfaces(text: str) -> int:
    """B7 test 8. `bg-white`, `bg-gray-50` or `bg-gray-100` written by the
    template; a surface comes from the kit (card, section, table).

    Proven red by adding `<div class="bg-white">` to `_aa_recordkop.html`."""
    return len(_SURFACE.findall(text))


def header_extras(text: str) -> int:
    """B7 test 17. A button in a `page_header` call slot that is neither the
    create ("+ …") nor "Instellingen"; everything else is an action passed as
    data, or belongs on the page.

    Proven red by adding a `page_header` call with `ui.btn_secondary(_("Exporteren"))`
    to `betalingen.html`."""
    count = 0
    for body in _HEADER.findall(text):
        for label in _BUTTON.findall(body):
            if not (label.startswith("+ ") or label.startswith("Instellingen")):
                count += 1
    return count


def hand_drawn_tiles(text: str) -> int:
    """B7 test 18. A tile strip drawn outside `ui.figures`: the macro
    refuses two figures in one tile, a hand-drawn strip refuses nothing.

    Proven red by adding `<div class="kpi-strip">` to `betalingen.html`."""
    return len(re.findall(r"(?<![\w-])kpi-strip(?![\w-])|\bdata-figure(?![\w-])", text))


def sideways_scrolls(text: str) -> int:
    """A list that scrolls sideways (`overflow-x-auto`); the kit's table lays a
    list out for the width it has.

    Proven red by adding `<div class="overflow-x-auto">` to
    `_betalingen_lijst.html`."""
    return len(re.findall(r"(?<![\w-])overflow-x-auto(?![\w-])", text))


def widened_rows(text: str) -> int:
    """B7 test 22, the mechanical half. `flex-nowrap`, `whitespace-nowrap` or a
    fixed `min-w-*` on a flex row itself. A child's minimum width is not counted
    (decided with the master CLI, 5 October 2026: the search field of a filter
    bar keeps its `min-w-[14rem]`).

    Proven red by adding `<div class="flex flex-nowrap">` to `_aa_detail.html`."""
    count = 0
    for classes in _TAG_CLASS.findall(text):
        names = classes.split()
        if any(n.split(":")[-1] in ("flex", "inline-flex") for n in names):
            count += len(_ROW_WIDENER.findall(classes))
    return count


def checkbox_groups_in_toolbars(text: str) -> int:
    """B7 test 23, the mechanical half. A `checkbox_group` inside a toolbar or a
    filter bar pushes the list off the first screen; `multiselect` is the one
    multi-choice control there.

    Proven red by adding `ui.checkbox_group("x", [])` to the toolbar of
    `_betalingen_scherm.html`."""
    return sum(body.count("checkbox_group(") for body in _TOOLBAR.findall(text))


def shell_extended_directly(text: str) -> int:
    """B7 test 1. An admin page that extends the shell itself instead of a
    layout. There is one layout today, `list_page.html`; a record page has no
    layout file yet and counts as on the kit when it renders the record head
    (`ui.record_header`, itself or through what it includes) — `measure` hands
    this collector the page with its includes folded in.

    Proven red by letting `betalingen.html` extend `admin_base.html`."""
    if not _EXTENDS_SHELL.search(text):
        return 0
    return 0 if "ui.record_header(" in text else 1


def _with_includes(rel: str, sources: dict[str, str]) -> str:
    """The template's text with what it includes appended, one level deep and
    then theirs — enough to see a record head that sits in a partial."""
    by_name = {Path(r).name: r for r in sources}
    seen, todo, parts = set(), [rel], []
    while todo:
        current = todo.pop()
        if current in seen:
            continue
        seen.add(current)
        parts.append(sources[current])
        for name in re.findall(r"\{%-?\s*include\s+\"([^\"]+)\"", sources[current]):
            if name in by_name:
                todo.append(by_name[name])
    return "\n".join(parts)


#: rule → (collector, what to do instead). The name is the baseline's name in
#: upper case.
RULES: dict[str, tuple[Callable[[str], int], str]] = {
    "raw_form_elements": (raw_form_elements, "a form control comes from `ui.field` (§3.1)"),
    "raw_checkboxes": (
        raw_checkboxes,
        "a boolean setting is a `switch` field, several out of a list a `checkbox_group` (§3.5)",
    ),
    "spacing_on_form_elements": (
        spacing_on_form_elements,
        "the kit's field and form grid own the distances (§3.1)",
    ),
    "raw_surfaces": (raw_surfaces, "a surface comes from the kit: card, section, table (§2)"),
    "header_extras": (
        header_extras,
        'a header slot holds the create and "Instellingen"; the rest is an action as data (§3.9)',
    ),
    "hand_drawn_tiles": (hand_drawn_tiles, "tiles come from `ui.figures` (§3.11)"),
    "sideways_scrolls": (sideways_scrolls, "a list is the kit's table (§3.12)"),
    "widened_rows": (widened_rows, "a row of controls wraps (§2.1)"),
    "checkbox_groups_in_toolbars": (
        checkbox_groups_in_toolbars,
        "`multiselect` is the multi-choice control of a toolbar (§3.10)",
    ),
    "shell_extended_directly": (
        shell_extended_directly,
        "a list extends `list_page.html`; a record renders `ui.record_header`",
    ),
}


def measure(rule: str, sources: dict[str, str] | None = None) -> dict[str, int]:
    """file → count, for the files where the rule finds anything."""
    sources = sources if sources is not None else templates()
    collector = RULES[rule][0]
    found = {}
    for rel, text in sources.items():
        subject = _with_includes(rel, sources) if rule == "shell_extended_directly" else text
        count = collector(subject)
        if count:
            found[rel] = count
    return found


def judge(rule: str, found: dict[str, int], frozen: dict[str, int], pilot: set[str]) -> list[str]:
    """What is wrong between a measurement and its baseline; empty when equal."""
    advice = RULES[rule][1]
    name = rule.upper()
    errors = []
    for rel in sorted(set(found) | set(frozen)):
        now, was = found.get(rel, 0), frozen.get(rel, 0)
        if rel in pilot and (now or was):
            errors.append(
                f"{rel}: {max(now, was)} × {rule} on a pilot screen — the pilot stands at zero and "
                f"is in no baseline: {advice}."
            )
        elif now > was:
            errors.append(f"{rel}: {now} × {rule}, the baseline says {was} — {advice}.")
        elif now < was and now == 0:
            errors.append(
                f"{rel}: clean now — remove the entry from `ui_baseline.{name}`; a ratchet that "
                "does not shrink is no ratchet."
            )
        elif now < was:
            errors.append(
                f"{rel}: {now} left, `ui_baseline.{name}` still says {was} — lower the number."
            )
    return errors


def _standing(rule: str) -> str:
    frozen = getattr(baseline, rule.upper())
    return f"{rule}={sum(frozen.values())}-in-{len(frozen)}-files"


# ── The ratchets on the real templates ───────────────────────────────────────


@pytest.mark.parametrize("rule", [pytest.param(r, id=_standing(r)) for r in RULES])
def test_the_count_only_falls(rule):
    """One test per rule; its id carries the standing, so a run shows it."""
    sources = templates()
    errors = judge(
        rule, measure(rule, sources), getattr(baseline, rule.upper()), pilot_templates(sources)
    )
    assert not errors, "\n".join(errors)


def test_every_rule_has_its_baseline_and_no_baseline_is_an_orphan():
    names = {
        n for n in vars(baseline) if n.isupper() and n != "INCLUDED_BY_THE_PILOT_NOT_RENDERED_THERE"
    }
    assert names == {r.upper() for r in RULES}


def test_the_pilot_is_found_through_its_includes():
    """A walk that finds nothing would make "the pilot at zero" green for ever:
    the partials the four pages are built from must be in the set."""
    pilot = pilot_templates()
    for name in (
        "_betalingen_scherm.html",
        "_betalingen_lijst.html",
        "_aa_recordkop.html",
        "_aa_detail.html",
        "_aa_rail.html",
        "_aa_inschrijvingen_lijst.html",
    ):
        assert any(rel.endswith("/" + name) for rel in pilot), (
            f"{name} is not seen as a pilot template"
        )
    assert len(pilot) >= 10


def test_a_partial_the_pilot_includes_but_does_not_render_is_really_included():
    """The one exemption from "the pilot at zero" is a file the pilot includes
    behind a condition that is false there. An entry for a file the pilot no
    longer includes is dead."""
    sources = templates()
    everything = "\n".join(_with_includes(page, sources) for page in PILOT_PAGES)
    for rel, reason in baseline.INCLUDED_BY_THE_PILOT_NOT_RENDERED_THERE.items():
        assert rel in sources, f"{rel} is gone — remove the entry"
        included = sources[rel] in everything
        assert included, f"{rel} is not included by a pilot page — remove the entry"
        assert reason.strip(), f"{rel} carries no reason"


def test_every_collector_still_finds_something_or_is_at_zero_on_purpose():
    """A collector whose pattern stopped matching reads as a rule that is met.
    Each one is fed its own violation below; here: a rule with an empty
    baseline is named, so that "nothing found" is a statement and not a silence."""
    empty = sorted(r for r in RULES if not getattr(baseline, r.upper()))
    assert empty == sorted(baseline_empty_on_purpose()), empty


def baseline_empty_on_purpose() -> list[str]:
    return ["checkbox_groups_in_toolbars"]


# ── The red proofs, kept ─────────────────────────────────────────────────────

VIOLATIONS = {
    "raw_form_elements": ('<input name="x">', 1),
    "raw_checkboxes": ('<input type="checkbox" name="x">', 1),
    "spacing_on_form_elements": ('<label class="mt-2 md:gap-x-4 text-sm">', 2),
    "raw_surfaces": ('<div class="bg-white hover:bg-gray-50">', 1),
    "header_extras": (
        '{% call ui.page_header(_("Leden")) %}{{ ui.btn_secondary(_("Exporteren")) }}'
        '{{ ui.btn_primary(_("+ Nieuw lid")) }}{{ ui.btn_secondary(_("Instellingen")) }}{% endcall %}',
        1,
    ),
    "hand_drawn_tiles": (
        '<div class="kpi-strip"><dd data-figure>3</dd><p data-figure-value>4</p></div>',
        2,
    ),
    "sideways_scrolls": ('<div class="overflow-x-auto">', 1),
    "widened_rows": (
        '<div class="flex flex-nowrap md:min-w-[9rem] min-w-0"><span class="whitespace-nowrap min-w-[14rem]">',
        2,
    ),
    "checkbox_groups_in_toolbars": (
        '{% call ui.toolbar() %}{{ ui.checkbox_group("x", []) }}{% endcall %}{{ ui.checkbox_group("y", []) }}',
        1,
    ),
    "shell_extended_directly": ('{% extends "admin_base.html" %}<h1>x</h1>', 1),
}


@pytest.mark.parametrize("rule", list(RULES))
def test_each_collector_counts_its_violation(rule):
    source, expected = VIOLATIONS[rule]
    assert RULES[rule][0](source) == expected
    assert RULES[rule][0]("<p>{{ ui.field('name', 'Naam') }}</p>") == 0


def test_a_hidden_input_is_no_control_and_a_record_page_is_on_the_kit():
    assert raw_form_elements('<input type="hidden" name="csrf_token">') == 0
    assert (
        shell_extended_directly('{% extends "admin_base.html" %}{{ ui.record_header(head) }}') == 0
    )
    assert shell_extended_directly('{% extends "list_page.html" %}') == 0


def test_the_judge_is_red_on_more_on_less_on_a_stale_entry_and_on_the_pilot():
    rule = "raw_form_elements"
    assert judge(rule, {"a.html": 2}, {"a.html": 2}, set()) == []
    assert "the baseline says 2" in judge(rule, {"a.html": 3}, {"a.html": 2}, set())[0]
    assert "the baseline says 0" in judge(rule, {"new.html": 1}, {}, set())[0]
    assert "lower the number" in judge(rule, {"a.html": 1}, {"a.html": 2}, set())[0]
    assert "remove the entry" in judge(rule, {}, {"a.html": 2}, set())[0]
    assert "pilot" in judge(rule, {"a.html": 2}, {"a.html": 2}, {"a.html"})[0]
    assert "pilot" in judge(rule, {}, {"a.html": 2}, {"a.html"})[0]


if (
    __name__ == "__main__"
):  # pragma: no cover — `python -m tests.test_ui_ratchets` prints the standing
    all_sources = templates()
    for rule_name in RULES:
        measured = measure(rule_name, all_sources)
        sys.stdout.write(f"\n{rule_name.upper()}: dict[str, int] = {{\n")
        for rel_path, number in sorted(measured.items()):
            sys.stdout.write(f'    "{rel_path}": {number},\n')
        sys.stdout.write(f"}}  # {sum(measured.values())} in {len(measured)} files\n")
