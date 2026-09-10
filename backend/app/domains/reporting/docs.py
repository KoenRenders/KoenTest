"""Generate ``docs/reporting-universe.md`` from the declaration (CR-06 §4.3).

Documentation of a semantic layer goes stale faster than any other kind: an object
is added in a hurry, the table in the document is not, and from then on the
document describes a universe that does not exist. So it is not written — it is
rendered, from the same tuples the engine builds SQL from, and a test compares the
file on disk with what this module renders. Drift is a red build, not a surprise.

Regenerate with::

    python -m app.domains.reporting.docs

The document is English (CLAUDE.md: all new documentation is English). The object
*names* inside it stay Dutch, because those are what a board member sees in the
objects pane — they are user-facing copy quoted in a document, not identifiers.
"""
from __future__ import annotations

from pathlib import Path

from app.domains.reporting.universe import (
    CLASSES,
    DIMENSIONS,
    FACTS,
    JOINS,
    OBJECTS,
    Role,
)

# backend/app/domains/reporting/docs.py -> repository root
DOC_PATH = Path(__file__).resolve().parents[4] / "docs" / "reporting-universe.md"

_HEADER = """<!--
GENERATED FILE — do not edit by hand.

Rendered from `backend/app/domains/reporting/universe.py` by
`python -m app.domains.reporting.docs`. `test_reporting_universe_gate.py` fails
when this file and the declaration disagree, so editing it here would only make
the build red.
-->

# The reporting universe

The semantic layer over the `reporting` star schema (CR-06 §4). A board member
picks **objects**; the engine resolves the joins, aggregates the measures, adds
the tenant filter, and writes the SQL. Nobody writes SQL, and no object exists
that is not in this document.

Object names are Dutch: they are what the objects pane shows. Object keys are
English and permanent — a saved report references keys, so a renamed key breaks
every report that used it.
"""


def _escape(text: str) -> str:
    """Markdown table cells cannot hold a raw pipe."""
    return text.replace("|", "\\|")


def _facts_section() -> list[str]:
    lines = ["## Facts", "",
             "A report is about exactly one fact — its measures decide the grain. "
             "Measures from two facts in one selection are refused: they would "
             "multiply each other (CR-06 §2.6).", "",
             "The last column is how the fact counts the people a group covers. "
             "The small-cell threshold needs it: a group of fewer than five is "
             "merged away, and a fact that cannot count people cannot be grouped "
             "by a sensitive dimension at all.", "",
             "The role column is the role the fact's **flat dataset dump** will "
             "need once the fence is built; see Roles below. Today every dump "
             "sits behind `require_admin_ui` like the rest of the back office.",
             "",
             "| Fact | Name | Grain | Role | People | What it holds |",
             "|---|---|---|---|---|---|"]
    for fact in FACTS:
        mensen = f"`{_escape(fact.people_sql)}`" if fact.people_sql else "—"
        lines.append(
            f"| `{fact.key}` | {_escape(fact.name)} | {_escape(fact.grain)} | "
            f"`{fact.role.value}` | {mensen} | {_escape(fact.description)} |"
        )
    return lines + [""]


def _dimensions_section() -> list[str]:
    lines = ["## Dimensions", "",
             "| Dimension | Name | Identifying column |",
             "|---|---|---|"]
    for dim in DIMENSIONS:
        lines.append(f"| `{dim.key}` | {_escape(dim.name)} | `{dim.key_column}` |")
    return lines + [""]


def _joins_section() -> list[str]:
    lines = ["## Join graph", "",
             "Every join also matches on `tenant_id`, unconditionally — a "
             "dimension row can never be borrowed from another tenant.", "",
             "| Fact | Dimension | On |",
             "|---|---|---|"]
    for join in JOINS:
        on = ", ".join(f"`{fact_col}` = `{dim_col}`" for fact_col, dim_col in join.pairs)
        lines.append(f"| `{join.fact}` | `{join.dimension}` | {on} |")
    return lines + [""]


def _roles_section() -> list[str]:
    lines = ["## Roles", "",
             "Every object carries a role. In v2.3.0 these are **declared and not "
             "enforced**: reporting sits behind `require_admin_ui`, the same door "
             "as every other admin screen, and the engine applies no per-object "
             "fence. The declaration records what must hold once that switch is "
             "built — as its own change, with its own test. Half a fence suggests "
             "a protection that is not there.", "",
             "| Universe role | Meaning | Objects |",
             "|---|---|---|"]
    meaning = {
        Role.ADMIN: "the default: what an admin screen already shows",
        Role.FINANCE: "money — every measure formatted as money, and the "
                      "Betalingen class",
        Role.MEMBER_DETAILS: "person-level details; CR-06 §7.3 keeps these out of "
                             "the universe, so nothing carries it yet",
    }
    for role in Role:
        count = sum(1 for o in OBJECTS if o.role is role)
        lines.append(f"| `{role.value}` | {meaning[role]} | {count} |")
    return lines + [""]


def _objects_section() -> list[str]:
    lines = ["## Objects", "",
             "**sensitive** marks a dimension that cuts people into groups small "
             "enough to recognise somebody by. Grouping on one turns on the "
             "small-cell threshold: every group of fewer than five people is "
             "merged into a single row. **not additive** marks a measure that may "
             "not be summed across those merged groups — an average of averages "
             "is not an average — so its cell stays empty there rather than "
             "showing a number that happens to be wrong.", ""]
    for klass in CLASSES:
        members = [o for o in OBJECTS if o.klass == klass]
        if not members:
            continue
        lines += [f"### {klass}", "",
                  "| Key | Name | Type | Format | Role | Source | Description |",
                  "|---|---|---|---|---|---|---|"]
        for obj in members:
            source = obj.sql.format(view=obj.view)
            lines.append(
                f"| `{obj.key}` | {_escape(obj.name)} | {obj.kind.value} | "
                f"{obj.format.value} | `{obj.role.value}` | `{_escape(source)}` | "
                f"{_escape(obj.description)} |"
            )
        lines.append("")
    return lines


def render() -> str:
    """The whole document as it should be on disk."""
    parts = [_HEADER]
    parts.append("\n".join(_facts_section()))
    parts.append("\n".join(_dimensions_section()))
    parts.append("\n".join(_joins_section()))
    parts.append("\n".join(_roles_section()))
    parts.append("\n".join(_objects_section()))
    return "\n".join(parts).rstrip() + "\n"


def write() -> Path:
    DOC_PATH.write_text(render(), encoding="utf-8")
    return DOC_PATH


if __name__ == "__main__":  # pragma: no cover - a developer command
    print(f"written: {write()}")
