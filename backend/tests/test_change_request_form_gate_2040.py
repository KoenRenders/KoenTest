"""Refuses a change request on master that lacks a drawing, the traceability matrix or the walkthrough the template requires · ratchet · since #2040.

The template (`docs/change_request_template.md`, since `5ea16e54`) puts the drawings
before the word budget: a writer over budget cuts prose, never a drawing or a table.
CR-36 to CR-39 lost their B2 and B3 to the budget and nobody saw it until Koen did
(15 October 2026). This gate makes the form fail by itself.

Per `docs/change_request_*.md` — except the template and CR-01 to CR-17, written before
2 October 2026 under the previous numbering (the template names them) — it requires:

- A2 and A3 each hold a Mermaid block;
- B2 holds a Mermaid block, a table under a heading with "Traceability" and a numbered
  list under a heading with "Walkthrough";
- B3 holds a Mermaid `flowchart` and a Mermaid `erDiagram`.

A change request still being shaped lives on its own branch, not on master, and is not
checked; one on master is. A ratchet, not a hard gate: `NOT_YET` is the frozen list of
change requests on master that failed when the gate was made (each owes its drawings, to
be added by their writer); it may only shrink, and a document that passes must leave it.

Proven red (16 October 2026, each put back): a file `docs/change_request_99_proof.md`, a
copy of CR-19 with its `erDiagram` block removed, added → `test_a_change_request_on_master_
has_what_the_template_requires` fails with "change_request_99_proof.md: B3: no erDiagram".
`test_the_checker_names_a_missing_part` makes the same kind of violation on a copy in
memory (no `erDiagram`, no table, no numbered list) and wants each one named.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests._bestanden import bestanden

pytestmark = pytest.mark.ui_agnostisch

DOCS = Path(__file__).resolve().parents[2] / "docs"
TEMPLATE = "change_request_template.md"
#: CR-01 to CR-17 follow the previous numbering (the template names them).
FIRST_CHECKED = 18

#: Change requests on master that fail today. Frozen; may only shrink.
NOT_YET: frozenset[str] = frozenset(
    {
        "change_request_18_code_review_by_other_ai_tool.md",
        "change_request_21_shop.md",
        "change_request_22_sign_in.md",
        "change_request_23_fields_and_labels.md",
        "change_request_24_back_office_rights.md",
        "change_request_25_back_office_part_2.md",
        "change_request_26_party_model.md",
        "change_request_27_bank_statement_import.md",
        "change_request_28_shop_workbench_tasks.md",
        "change_request_29_shorter_ci.md",
        "change_request_30_european_forge.md",
        "change_request_31_checkout_in_two_steps.md",
        "change_request_32_sections_cards_and_own_look.md",
        "change_request_33_attribute_inventory.md",
        "change_request_33_attribute_register.md",
        "change_request_34_invoices.md",
        "change_request_35_peppol.md",
    }
)

_HEADING = re.compile(r"^#{1,6}\s")
_SECTION = re.compile(r"^##\s+([AB]\d+)\.")
_FENCE = re.compile(r"^```\s*mermaid\s*$")
_BOLD_LABEL = re.compile(r"^\*\*[^*]+\*\*")
_NUMBERED = re.compile(r"^\d+\.\s")


def number_of(path: Path) -> int:
    return int(re.match(r"change_request_(\d+)_", path.name).group(1))


def _sections(text: str) -> dict[str, list[str]]:
    """The lines of A2, A3, B2, B3: from their `## X.` heading to the next `## `."""
    found: dict[str, list[str]] = {}
    current: list[str] | None = None
    for line in text.splitlines():
        match = _SECTION.match(line)
        if match:
            current = found.setdefault(match.group(1), [])
        elif line.startswith("## "):
            current = None
        elif current is not None:
            current.append(line)
    return found


def _mermaid_blocks(lines: list[str]) -> list[str]:
    """The diagram type (`flowchart`, `erDiagram`, …) of each ```mermaid block: the
    first line of its body that is not a comment. A block with no body counts for
    nothing."""
    kinds, state = [], "out"
    for line in lines:
        if state == "out":
            if _FENCE.match(line):
                state = "open"
        elif line.startswith("```"):
            state = "out"
        elif state == "open" and line.strip() and not line.strip().startswith("%%"):
            kinds.append(line.split()[0])
            state = "rest"
    return kinds


def _after_label(lines: list[str], word: str, *, to_end: bool = False) -> list[str]:
    """The lines under the first heading or bold label that contains `word`: up to the
    next heading or bold label, or to the end of the section with `to_end` (a
    walkthrough has a bold line per role)."""
    out, inside = [], False
    for line in lines:
        is_label = bool(_HEADING.match(line)) or bool(_BOLD_LABEL.match(line.strip()))
        if is_label and not (inside and to_end):
            if inside:
                break
            inside = word.lower() in line.lower()
            continue
        if inside:
            out.append(line)
    return out


def missing_parts(text: str) -> list[str]:
    """What the template requires and this document does not have, one phrase each."""
    sections = _sections(text)
    missing = []
    for name in ("A2", "A3", "B2", "B3"):
        if name not in sections:
            missing.append(f"{name}: the section is missing")
    for name in ("A2", "A3", "B2"):
        if name in sections and not _mermaid_blocks(sections[name]):
            missing.append(f"{name}: no Mermaid block")
    if "B2" in sections:
        if not any(
            line.lstrip().startswith("|") for line in _after_label(sections["B2"], "Traceability")
        ):
            missing.append("B2: no table under a Traceability heading")
        if not any(
            _NUMBERED.match(line)
            for line in _after_label(sections["B2"], "Walkthrough", to_end=True)
        ):
            missing.append("B2: no numbered list under a Walkthrough heading")
    if "B3" in sections:
        kinds = _mermaid_blocks(sections["B3"])
        if "flowchart" not in kinds and "graph" not in kinds:
            missing.append("B3: no flowchart")
        if "erDiagram" not in kinds:
            missing.append("B3: no erDiagram")
    return missing


def _checked() -> list[Path]:
    return [
        p
        for p in bestanden(
            DOCS.glob("change_request_*.md"), wat="the change requests in docs/", minstens=30
        )
        if p.name != TEMPLATE and number_of(p) >= FIRST_CHECKED
    ]


def test_a_change_request_on_master_has_what_the_template_requires():
    """Every change request after CR-17 that is not on the frozen list has its
    drawings, its traceability matrix and its walkthrough; the message names the
    document and the part."""
    paths = _checked()
    assert len(paths) >= 20, f"only {len(paths)} change requests found after CR-17"
    problems = []
    for path in paths:
        if path.name in NOT_YET:
            continue
        for part in missing_parts(path.read_text(encoding="utf-8")):
            problems.append(f"{path.name}: {part}")
    assert not problems, (
        "a change request misses a part the template requires (drawings come before "
        "the word budget):\n" + "\n".join(problems)
    )


def test_the_frozen_list_only_shrinks():
    """A name on `NOT_YET` must exist and must still fail: a document that now passes
    leaves the list (a list that cannot shrink hides what has been repaired)."""
    by_name = {p.name: p for p in _checked()}
    gone = sorted(NOT_YET - by_name.keys())
    assert not gone, f"on the frozen list but not a checked change request: {gone}"
    repaired = sorted(
        n for n in NOT_YET if not missing_parts(by_name[n].read_text(encoding="utf-8"))
    )
    assert not repaired, f"these now pass; take them off NOT_YET: {repaired}"


def _a_passing_text() -> str:
    for path in _checked():
        if path.name not in NOT_YET:
            return path.read_text(encoding="utf-8")
    raise AssertionError("no change request passes: nothing to break on purpose")


def _without_block(text: str, kind: str) -> str:
    """The text with the first mermaid block of diagram type `kind` removed."""
    out: list[str] = []
    buffer: list[str] = []
    inside = removed = False
    for line in text.splitlines():
        if not inside:
            if _FENCE.match(line) and not removed:
                inside, buffer = True, [line]
            else:
                out.append(line)
            continue
        buffer.append(line)
        if line.startswith("```"):
            body = [b for b in buffer[1:-1] if b.strip() and not b.strip().startswith("%%")]
            if body and body[0].split()[0] == kind:
                removed = True
            else:
                out.extend(buffer)
            inside = False
    assert removed, f"the passing text has no {kind} block to remove"
    return "\n".join(out)


def test_the_checker_names_a_missing_part():
    """The added violations, made on a copy of a passing document: each is named."""
    text = _a_passing_text()
    assert missing_parts(text) == []
    assert "B3: no erDiagram" in missing_parts(_without_block(text, "erDiagram"))
    no_table = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("|"))
    assert "B2: no table under a Traceability heading" in missing_parts(no_table)
    no_walkthrough = re.sub(r"(?m)^\d+\.\s.*$", "", text)
    assert "B2: no numbered list under a Walkthrough heading" in missing_parts(no_walkthrough)
    assert missing_parts("# Not a change request\n") != []
