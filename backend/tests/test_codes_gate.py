"""The gate on the code pattern (CR-12 §B9.3) — eleven checks, each able to go red.

One shape for every fixed vocabulary: a code table, a label table per language,
and a plain `Enum` where Python branches on the value. This gate is what holds
future work to that shape — without it the rule is an agreement everybody
forgets the moment it gets busy.

**Two forms, and which one it is follows from the count.** While work is still
open the check is a **ratchet**: today's offenders are frozen in
`tests/codes_baseline.py`, a new one is red, and one that disappears from the
code must leave the list or the test is red. Once the count is zero it is a
**hard gate**. Phase 5 of CR-12 removes the lists and the exemption logic
together.

**Why the loose-string check is an AST walk and not a mypy rule (§B4.8).**
#779 relied on `strict_equality`. That does not work here: the models use the
legacy `Column()` style, so mypy types every column attribute as `Any`, and
`Any == "paid"` is never an error. A gate built on it would be green with all
of the comparisons still in place — exactly the kind of test `CLAUDE.md`
forbids.

## Proof that each check can go red

The method of the css gate (#652): make one real violation, see whether it
fires, put it back. All eleven measured that way on 26 September 2026, each on
its own, with the violation listed here:

| Check | Violation | Fired |
|---|---|---|
| FK registered | added `meetings.meetings.location` to `fk_from` | yes |
| FK net (ratchet) | column `payment_kind = Column(String(20))` on `Meeting` | yes |
| Label coverage | removed the `en` pass from the seeding helper | yes — `code nl has no en label` |
| Enum = codes | member `MeetingStatus.CANCELLED` without a row | yes |
| Enum without a list (ratchet) | `class Proef(Enum)` in `meetings/models.py` | yes |
| Tones total | removed `MeetingStatus.SENT` from the tone mapping | yes |
| No label dictionaries (ratchet) | put `STATUS_LABELS = {...}` back in `meetings/admin_ui.py` | yes |
| No template comparisons (ratchet) | `{% if meeting.status == "sent" %}` in `_vg_document.html` | yes |
| Loose strings (ratchet) | `meeting.status == "sent"` in `meetings/service.py` | yes |
| Enum member names English | added member `VERSTUURD = "verstuurd"` | yes — names the member |
| Shape | removed the `description` column from the helper's label table | yes |

One measurement had to be redone, and that is worth recording: for "enum member
names English" I first *renamed* `SENT` to `VERSTUURD`. That broke the import of
`service.py`, so the test never ran — and a green result that proves nothing is
worse than a red one. The violation has to be **additive**: a member added, not
a member renamed. Same trap as a gate that looks nowhere (#678), only on the
evidence side of it.
"""
import ast
import re
from pathlib import Path

import pytest
from sqlalchemy import String, inspect, text

from app.database import Base
from app.domains.registry import load_all_models
from app.kernel.codes import (
    ExternalVocabulary,
    TechnicalEnum,
    registry,
)
from tests import codes_baseline as baseline
from tests._bestanden import bestanden

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"

#: Attribute names that mark a fixed vocabulary. The net of §B9.3, and
#: explicitly no more than that: a column called `categorie` escapes it until
#: someone registers it. The review rule for a new `String` column with a
#: literal default stays "is this a list?".
VOCABULARY = {
    "status", "type", "kind", "method", "role", "mode", "state",
    "variant", "layout", "preset", "style", "audience", "provider",
    "purpose", "direction", "format", "gender", "source",
}

#: Suffixes that say the same thing on a column name.
VOCABULARY_SUFFIXES = ("_status", "_type", "_kind", "_method", "_role",
                       "_code", "_mode", "_state", "_purpose", "_variant")


def _is_exempt_table(table: str) -> bool:
    """History is append-only and must survive a retired code (§F4), and the
    code/label tables are the list itself."""
    return (table.endswith("_history") or table.endswith("_codes")
            or table.endswith("_labels") or table == "alembic_version")


def _is_vocabulary(column_name: str) -> bool:
    return column_name in VOCABULARY or column_name.endswith(VOCABULARY_SUFFIXES)


def _path(file: Path) -> str:
    return str(file.relative_to(BACKEND))


# ── Source files, always through the helper (#678) ───────────────────────────

def _python_files() -> list[Path]:
    return bestanden(APP.rglob("*.py"), wat="the Python files under app/",
                     minstens=100)


def _template_files() -> list[Path]:
    return bestanden(APP.rglob("*.html"), wat="the templates under app/",
                     minstens=50)


# ── The collectors (also usable on their own to measure the table) ───────────

def collect_enums_without_list() -> dict[str, str]:
    """`Enum` classes with no `CodeList` and no marker → key: message."""
    load_all_models()
    # On module and name, not on name alone. Measured in phase 2: as soon as
    # `auth.models.Role` was in a CodeList, this gate also took
    # `reporting.universe.Role` as covered — a different class with the same
    # name. A gate that compares a name instead of a thing silently covers
    # too much, and that is worse than too little.
    in_a_list = {(lst.enum.__module__, lst.enum.__name__)
                 for lst in registry().values() if lst.enum is not None}
    markers = {TechnicalEnum.__name__, ExternalVocabulary.__name__}
    found: dict[str, str] = {}
    for file in _python_files():
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = {b.id for b in node.bases if isinstance(b, ast.Name)}
            bases |= {b.attr for b in node.bases if isinstance(b, ast.Attribute)}
            if not (bases & {"Enum", "IntEnum", "StrEnum"} | (bases & markers)):
                continue
            if bases & markers:
                continue
            if node.name in markers:
                # The marker classes themselves: they are the exception, not an
                # instance of it. Without this line the kernel sits on its own
                # ratchet.
                continue
            module = (str(file.relative_to(APP.parent))
                      .removesuffix(".py").replace("/", "."))
            if (module, node.name) in in_a_list:
                continue
            found[f"{_path(file)}:{node.name}"] = (
                f"{_path(file)}:{node.lineno} — `{node.name}` is an Enum without a "
                f"CodeList. Declare one (table + labels) or mark it "
                f"TechnicalEnum/ExternalVocabulary with the reason.")
    return found


def collect_label_dictionaries() -> dict[str, str]:
    """Assignments like `X_LABELS = {...}` under `app/` → key: message."""
    found: dict[str, str] = {}
    for file in _python_files():
        if file.name == "codes.py" and file.parent.name == "kernel":
            continue
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Dict):
                continue
            for target in node.targets:
                if not isinstance(target, ast.Name):
                    continue
                if not re.search(r"LABELS?$", target.id):
                    continue
                found[f"{_path(file)}:{target.id}"] = (
                    f"{_path(file)}:{node.lineno} — `{target.id}` puts labels in "
                    f"Python. Use `code_label()` and a label table.")
    return found


_TEMPLATE_COMPARISON = re.compile(
    r"\.(?P<attr>[a-z_]+)\s*(?P<op>==|!=)\s*(?P<quote>['\"])(?P<value>[^'\"]*)(?P=quote)")


def collect_template_comparisons() -> dict[str, str]:
    """`.status == "paid"` and friends in a template → key: message."""
    found: dict[str, str] = {}
    for file in _template_files():
        for number, line in enumerate(
                file.read_text(encoding="utf-8").splitlines(), start=1):
            for hit in _TEMPLATE_COMPARISON.finditer(line):
                attr = hit.group("attr")
                if not _is_vocabulary(attr):
                    continue
                comparison = f"{attr}{hit.group('op')}{hit.group('value')}"
                found[f"{_path(file)}:{comparison}"] = (
                    f"{_path(file)}:{number} — compares `{attr}` to a literal. "
                    f"Expose what the screen needs on the view-model (§B4.7).")
    return found


def _string_constants(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, (ast.Tuple, ast.List, ast.Set)):
        out: list[str] = []
        for element in node.elts:
            out.extend(_string_constants(element))
        return out
    return []


def collect_loose_strings() -> dict[str, str]:
    """`record.status == "paid"` in `app/**/*.py` → key: message.

    An AST walk and not a grep: a grep finds the text, not the shape, and it
    cannot tell a comparison from a key in a dictionary.
    """
    found: dict[str, str] = {}
    for file in _python_files():
        if file.name == "codes.py" and file.parent.name == "kernel":
            continue
        tree = ast.parse(file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Compare):
                continue
            for operator, right in zip(node.ops, node.comparators):
                if not isinstance(operator, (ast.Eq, ast.NotEq, ast.In, ast.NotIn)):
                    continue
                for attribute, other in ((node.left, right), (right, node.left)):
                    if not isinstance(attribute, ast.Attribute):
                        continue
                    if not _is_vocabulary(attribute.attr):
                        continue
                    for value in _string_constants(other):
                        sign = {ast.Eq: "==", ast.NotEq: "!=",
                                ast.In: " in ", ast.NotIn: " not in "}[type(operator)]
                        comparison = f"{attribute.attr}{sign}{value}"
                        found[f"{_path(file)}:{comparison}"] = (
                            f"{_path(file)}:{node.lineno} — compares "
                            f"`{attribute.attr}` to {value!r}. Use the Enum member "
                            f"of the list.")
    return found


def collect_missing_fks() -> dict[str, str]:
    """Columns that look like they store a vocabulary but carry no FK."""
    load_all_models()
    registered = {column for lst in registry().values() for column in lst.fk_from}
    found: dict[str, str] = {}
    for table in Base.metadata.tables.values():
        schema = table.schema or "public"
        if _is_exempt_table(table.name):
            continue
        for column in table.columns:
            if not isinstance(column.type, String):
                continue
            if not _is_vocabulary(column.name):
                continue
            key = f"{schema}.{table.name}.{column.name}"
            if key in registered or column.foreign_keys:
                continue
            found[key] = (
                f"`{key}` stores a vocabulary but has no FK to a code table — "
                f"declare a CodeList or add it to the ratchet with a reason.")
    return found


COLLECTORS = {
    "FK_MISSING": collect_missing_fks,
    "ENUM_WITHOUT_LIST": collect_enums_without_list,
    "LABEL_DICTIONARIES": collect_label_dictionaries,
    "TEMPLATE_COMPARISONS": collect_template_comparisons,
    "LOOSE_STRINGS": collect_loose_strings,
}


#: Per ratchet, the dict of permanent exceptions that belongs to it. Entries
#: there are neither a violation nor progress: they are values somebody else
#: owns. They are counted separately, so a ratchet stays a promise about our own
#: work and does not carry a number that can never reach zero.
PERMANENT = {
    "FK_MISSING": "FK_NOT_OUR_LIST",
    "LOOSE_STRINGS": "LOOSE_STRINGS_NOT_A_CODE",
}


def _permanent(name: str) -> dict[str, str]:
    return getattr(baseline, PERMANENT[name], {}) if name in PERMANENT else {}


def _ratchet(name: str) -> None:
    """The one shape of every ratchet: nothing new, and nothing left behind."""
    found = {k: v for k, v in COLLECTORS[name]().items()
             if k not in _permanent(name)}
    frozen = getattr(baseline, name)
    added = sorted(set(found) - set(frozen))
    gone = sorted(set(frozen) - set(found))
    errors = []
    if added:
        errors.append("New violations:\n  " + "\n  ".join(found[k] for k in added))
    if gone:
        errors.append(
            f"These are still in `codes_baseline.{name}` but no longer exist:\n  "
            + "\n  ".join(gone)
            + "\nRemove them from the list — a ratchet that does not shrink is no "
              "ratchet.")
    assert not errors, "\n\n".join(errors)


# ── 1. FK coverage, registered (hard) ────────────────────────────────────────

def test_every_registered_column_carries_its_fk(db_session):
    """What a `CodeList` promises in `fk_from` really is in the database.

    Positive and exact: the registry is the list, so no heuristic is needed
    here and no ratchet — a promise without a foreign key is simply wrong.
    """
    load_all_models()
    missing = []
    for lst in registry().values():
        for column in lst.fk_from:
            schema, table, column_name = column.split(".")
            fks = inspect(db_session.bind).get_foreign_keys(table, schema=schema)
            hit = any(column_name in fk["constrained_columns"]
                      and fk["referred_table"] == f"{lst.name}_codes"
                      for fk in fks)
            if not hit:
                missing.append(
                    f"`{column}` is in the CodeList `{lst.name}` but carries no FK "
                    f"to `{lst.codes_table}`")
    assert not missing, "\n".join(missing)


# ── 2. FK coverage, unregistered (ratchet) ───────────────────────────────────

def test_no_new_vocabulary_column_without_an_fk():
    """The net: a new `String` column storing a list without a code table."""
    _ratchet("FK_MISSING")


# ── 3. Label coverage (hard) ─────────────────────────────────────────────────

def test_every_active_code_has_a_label_in_both_languages(db_session):
    """A screen may never render blank, and `en` is not a "later".

    This change request seeds both languages for every list; a gate that makes
    `en` optional never gets `en`.
    """
    load_all_models()
    missing = []
    for lst in registry().values():
        codes = db_session.execute(text(
            f"SELECT code FROM {lst.codes_table} WHERE is_active")).scalars().all()
        assert codes, f"`{lst.codes_table}` has no active code at all"
        for language in ("nl", "en"):
            present = set(db_session.execute(text(
                f"SELECT code FROM {lst.labels_table} "
                f"WHERE language = :language AND value <> ''"),
                {"language": language}).scalars().all())
            for code in codes:
                if code not in present:
                    missing.append(
                        f"`{lst.codes_table}`: code `{code}` has no "
                        f"{language} label")
    assert not missing, "\n".join(missing)


# ── 4. Enum = codes (hard) ───────────────────────────────────────────────────

def test_every_enum_covers_exactly_its_codes(db_session):
    """Both directions, retired codes included.

    A retired code keeps its member (§B4.3): without one, that row reads back
    as a bare string, and a bare string is unequal to every member. That is the
    mistake nobody notices.
    """
    load_all_models()
    errors = []
    for lst in registry().values():
        if lst.enum is None:
            continue
        in_the_table = set(db_session.execute(text(
            f"SELECT code FROM {lst.codes_table}")).scalars().all())
        in_the_enum = {member.value for member in lst.enum}
        for value in sorted(in_the_enum - in_the_table):
            errors.append(f"`{lst.enum.__name__}` has a member with value `{value}` "
                          f"and no row in `{lst.codes_table}`")
        for code in sorted(in_the_table - in_the_enum):
            errors.append(f"`{lst.codes_table}` has code `{code}` with no member in "
                          f"`{lst.enum.__name__}` — a retired code keeps its member "
                          f"too. A list that is meant to grow by a row gets no enum "
                          f"at all and names its codes with `Code` constants, the "
                          f"way `contact_type` does")
    assert not errors, "\n".join(errors)


# ── 5. Enum without a list (ratchet) ─────────────────────────────────────────

def test_no_new_enum_without_a_code_list():
    """Every `Enum` under `app/` belongs to a `CodeList` or carries its reason.

    The exception that does not reach zero and should not: a `TechnicalEnum` or
    an `ExternalVocabulary`. Those are counted, not capped — see the ratchet
    table at the bottom.
    """
    _ratchet("ENUM_WITHOUT_LIST")


# ── 6. Tones total (hard) ────────────────────────────────────────────────────

def test_every_tone_mapping_is_total():
    """A badge without a tone falls back to grey, and nobody notices."""
    load_all_models()
    import app.main  # noqa: F401  — loads the UI modules that register the tones

    errors = []
    for lst in registry().values():
        if not lst.tones or lst.enum is None:
            continue
        for member in lst.enum:
            if member.value not in lst.tones:
                errors.append(f"`{lst.enum.__name__}.{member.name}` has no badge "
                              f"tone in the mapping of `{lst.name}`")
    assert not errors, "\n".join(errors)


# ── 7-9. The three text ratchets ─────────────────────────────────────────────

def test_no_new_label_dictionary_in_python():
    _ratchet("LABEL_DICTIONARIES")


def test_no_new_template_comparison_on_a_code():
    _ratchet("TEMPLATE_COMPARISONS")


def test_no_new_loose_string_comparison():
    _ratchet("LOOSE_STRINGS")


# ── 10. Enum member names in English (hard) ──────────────────────────────────

#: Dutch words that appear, or threaten to appear, as an enum member name. Not
#: a dictionary: a net, in the spirit of #780. The *value* may be Dutch — that
#: is stored data — the NAME may not.
#: "PARTNER" was here and has been taken out: it is an English word too, and
#: the catalogue of §B5.3 gives `PARTNER` as the member name. A net that
#: rejects a correct member costs more than it catches.
DUTCH_WORDS = {
    "HOOFDLID", "KIND", "GEZIN", "LID", "LEDEN", "BEDRIJF",
    "VERENIGING", "FEITELIJKE", "VERSTUURD", "BETAALD", "OPENSTAAND",
    "VEREFFEND", "GEANNULEERD", "MISLUKT", "AFWACHTING", "VERSLAG",
    "OVERSCHRIJVING", "CONTANT", "LIJN", "KLEUR", "BEELD", "TEKST",
    "EENVOUDIG", "AANWEZIG", "VERONTSCHULDIGD", "BIJLAGE", "SOORT",
}


def test_enum_members_of_a_code_list_have_english_names():
    """The value is data and stays; the name is an identifier and is English.

    `RelationType.PRIMARY_MEMBER = "HOOFDLID"` — otherwise every Dutch code
    becomes a new Dutch identifier and the #780 ratchet fills up.
    """
    load_all_models()
    errors = []
    for lst in registry().values():
        if lst.enum is None:
            continue
        for member in lst.enum:
            for word in member.name.split("_"):
                if word in DUTCH_WORDS:
                    errors.append(
                        f"`{lst.enum.__name__}.{member.name}`: member names are "
                        f"English — the value `{member.value}` stays as it is stored")
    assert not errors, "\n".join(errors)


# ── 11. Shape (hard) ─────────────────────────────────────────────────────────

CODES_COLUMNS = {"code", "sort_order", "is_active", "created_at"}
LABELS_COLUMNS = {"code", "language", "value", "description", "created_at",
                  "updated_at"}


def test_every_list_has_the_shape_the_helper_writes(db_session):
    """The helper wrote them; this gate proves nobody adjusted them afterwards.

    Including the FK from `language` to `mdm.language_codes`: that is the
    reason there is one language list, and this is the only place it is checked
    per list (which is why `mdm/codes.py` leaves `fk_from` empty).
    """
    load_all_models()
    inspector = inspect(db_session.bind)
    errors = []
    for lst in registry().values():
        for table, expected in (
                (f"{lst.name}_codes", CODES_COLUMNS | set(lst.extra_code_columns)),
                (f"{lst.name}_labels", LABELS_COLUMNS)):
            present = {c["name"] for c in
                       inspector.get_columns(table, schema=lst.schema)}
            if present != expected:
                errors.append(
                    f"`{lst.schema}.{table}` has columns {sorted(present)}, "
                    f"expected {sorted(expected)} — an extra column on a code "
                    f"table is allowed, but it has to be declared in the "
                    f"CodeList's `extra_code_columns` with the reason")
        language_fk = [fk for fk in inspector.get_foreign_keys(
                           f"{lst.name}_labels", schema=lst.schema)
                       if fk["constrained_columns"] == ["language"]]
        if not language_fk or language_fk[0]["referred_table"] != "language_codes":
            errors.append(
                f"`{lst.labels_table}.language` does not point at "
                f"`mdm.language_codes` — then any spelling can end up in it")
    assert not errors, "\n".join(errors)


# ── The ratchet table (AC5) ──────────────────────────────────────────────────

def _count_mapped_enum_columns() -> int:
    """Columns written as `Mapped[X] = mapped_column(EnumColumn(X))` (§B4.8).

    Through the AST and not through a text search, and that is not a matter of
    taste here: the first version counted the literal text
    `mapped_column(EnumColumn` and returned 0 while the one column written that
    way was sitting right there — the call ran over two lines. A counter that
    returns zero because the shape is slightly different is the same mistake as
    a gate that looks nowhere (#678), and it happened immediately.
    """
    total = 0
    for file in _python_files():
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "mapped_column"):
                continue
            for child in ast.walk(node):
                if (isinstance(child, ast.Call) and isinstance(child.func, ast.Name)
                        and child.func.id == "EnumColumn"):
                    total += 1
                    break
    return total


def ratchet_table(db_session=None) -> list[tuple[str, int]]:
    """The numbers of §B9.2 as the gate measures them, not as grep guessed them.

    **What is deliberately absent.** §B9.2 opens with "lists with a fixed
    vocabulary: 49". That number is an *inventory* from §B5.3 — somebody read
    the codebase and counted the lists, in whatever shape they were in. No gate
    can reproduce that: a list that is a module constant today, or a bare string
    with a comment, is by definition not recognisable by a shape. What is here
    is the half that *is* measurable: how many are in the pattern, and how many
    are still outside it per kind of violation. The 49 stays the target the 2
    below grows towards, and it lives in the document.
    """
    load_all_models()
    lists = registry()
    marked = sum(
        1 for file in _python_files()
        for node in ast.walk(ast.parse(file.read_text(encoding="utf-8")))
        if isinstance(node, ast.ClassDef)
        and {b.id for b in node.bases if isinstance(b, ast.Name)}
        & {"TechnicalEnum", "ExternalVocabulary"})
    rows = [
        ("lists in the pattern (CodeList) — target 49, see §B5.3", len(lists)),
        ("… with an Enum", sum(1 for x in lists.values() if x.enum is not None)),
        ("enum-carrying columns written as Mapped[]", _count_mapped_enum_columns()),
        ("vocabulary columns without an FK (ratchet)", len(baseline.FK_MISSING)),
        ("enums without a CodeList (ratchet)", len(baseline.ENUM_WITHOUT_LIST)),
        ("enums marked technical/external (counted, not capped)", marked),
        ("label dictionaries in Python (ratchet)", len(baseline.LABEL_DICTIONARIES)),
        ("template comparisons on a code (ratchet)",
         len(baseline.TEMPLATE_COMPARISONS)),
        ("loose string comparisons in .py (ratchet)", len(baseline.LOOSE_STRINGS)),
        ("permanent exceptions — not our vocabulary (counted, not capped)",
         len(baseline.FK_NOT_OUR_LIST) + len(baseline.LOOSE_STRINGS_NOT_A_CODE)),
    ]
    if db_session is not None:
        for language in ("nl", "en"):
            total = sum(db_session.execute(text(
                f"SELECT count(*) FROM {lst.labels_table} WHERE language = :lang"),
                {"lang": language}).scalar_one() for lst in lists.values())
            rows.append((f"label rows in `{language}`", total))
    return rows


def test_the_ratchet_table_is_measurable_and_gets_printed(capsys, db_session):
    """AC5: the table comes out of the gate, not out of the document.

    Run `pytest -s -k ratchet_table` and paste the output into the closing
    comment of the phase issue. Every number must be lower than or equal to the
    previous phase's — that is the whole ratchet.
    """
    rows = ratchet_table(db_session)
    with capsys.disabled():
        print("\n\n§B9.2 — measured by the gate\n")
        for name, total in rows:
            print(f"  {total:>5}  {name}")
        print()
    assert all(total >= 0 for _, total in rows)


# ── The gate can go red itself ───────────────────────────────────────────────

@pytest.mark.parametrize("name", sorted(COLLECTORS))
def test_every_ratchet_looks_somewhere(name):
    """#678 in miniature: a collector that scans nothing is green forever.

    The collectors go through `bestanden()`, so an empty path is caught there
    already. This test covers the case after that: a collector that does read
    files but, because a shape changed, never recognises anything again. That
    the frozen entries are still found is the proof that the walk works.
    """
    found = COLLECTORS[name]()
    frozen = set(getattr(baseline, name))
    assert set(found) >= frozen, (
        f"`{name}` finds less than the frozen list — that is either cleanup "
        f"(remove them from the baseline) or a collector that has fallen silent")


@pytest.mark.parametrize("name", sorted(PERMANENT))
def test_every_permanent_exception_still_has_a_target(name):
    """An exemption whose target is gone must go too — same rule as a ratchet.

    The ratchets have this rule: an entry that disappears from the code has to
    leave the list or the test is red. Without the same rule here the two
    drift, and that asymmetry is how a rule dies quietly. Replace the Mollie
    adapter and `payment.gateway_payments.status` would stay exempt forever —
    an exemption with a reason that no longer applies, which is worse than no
    exemption, because the next reader takes the reason at face value.

    **Proven by violation, 26 September 2026:** added
    `"payment.payment_records.status"` to `FK_NOT_OUR_LIST`. That column *does*
    have a foreign key now, so the collector no longer finds it, and the test
    went red naming the entry and the list. Removed again.
    """
    found = set(COLLECTORS[name]())
    stale = sorted(set(_permanent(name)) - found)
    assert not stale, (
        f"`codes_baseline.{PERMANENT[name]}` exempts something that no longer "
        f"exists:\n  " + "\n  ".join(stale)
        + f"\nRemove the entry. An exemption outlives the thing it excuses "
          f"otherwise, and its reason stops being true without anybody noticing.")
