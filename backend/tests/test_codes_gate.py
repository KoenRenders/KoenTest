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

**Phase 5 (#1182, 27 September 2026).** Four of the five ratchets reached zero
and are hard now: enums without a list, label dictionaries, template
comparisons and loose strings. Their frozen sets are gone from
`codes_baseline.py`, and `_hard()` has no "left behind" half because nothing
is left. `FK_MISSING` followed on 28 September, when Koen decided the last
column (`mdm.external_numbers.source`, a code list — migration 166): **no
ratchet is left**, and `_ratchet()` went with it. With the frozen lists gone,
a hard gate proves it still looks somewhere through its exemptions
(`test_every_hard_gate_looks_somewhere`) or, for the enum gate, by counting
the enum classes it recognised.

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
| … also when annotated (phase 4) | `PROBE_LABELS: dict[str, str] = {...}` in `audit/changes.py` | yes — before this, it did not |
| No template comparisons (ratchet) | `{% if meeting.status == "sent" %}` in `_vg_document.html` | yes |
| Loose strings (ratchet) | `meeting.status == "sent"` in `meetings/service.py` | yes |
| Enum member names English | added member `VERSTUURD = "verstuurd"` | yes — names the member |
| Shape | removed the `description` column from the helper's label table | yes |

**Phase 5, the four gates at zero, proven again as hard gates** — each by an
*added* violation, 27 September 2026:

| Hard gate | Violation added | Fired |
|---|---|---|
| Enum without a list | `class Proef(Enum)` at the end of `meetings/models.py` | yes — only this test |
| No label dictionaries | `PROBE_LABELS = {"a": "b"}` at the end of `audit/changes.py` | yes — only this test |
| No template comparisons | `{% if meeting.status == "sent" %}` at the end of `_vg_document.html` | yes — only this test |
| No loose strings | `meeting.status == "sent"` in a function added to `meetings/service.py` | yes — only this test |
| A hard gate looks somewhere | the template pattern's operators changed to `===`/`!==` | yes — the walk test and the shelf-life test lost the exemptions; the gate itself fired too, because the altered pattern caught Alpine's `!==` |
| The enum gate looks somewhere | the walk counting only the marker classes | yes — only this test |
| No vocabulary column without an FK (28 September, the last one) | `payment_kind = Column(String(20))` added to `Meeting` | yes — only this test |

**A twelfth came with phase 3**, after three enum members reached an HTML
attribute and none of the eleven above could see it — a member that is
*rendered* is not a comparison. It is a guard rather than a sample
(`install_enum_guard` hooks Jinja's `finalize`), so it lives in
`tests/test_enum_render_gate.py` with its own proof, and this table carries
its two numbers.

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
from app.kernel import codes as kernel_codes
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

def collect_enums_without_list(seen: list[str] | None = None) -> dict[str, str]:
    """`Enum` classes with no `CodeList` and no marker → key: message.

    `seen` collects every enum class the walk recognised, marked or not, so a
    hard gate can prove it looked somewhere (#678): with nothing left to find,
    an empty result would otherwise read the same as a walk that broke.
    """
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
            if seen is not None and node.name not in markers:
                seen.append(f"{_path(file)}:{node.name}")
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
            # `X_LABELS = {...}` and `X_LABELS: dict[..., str] = {...}` alike.
            # Only the first used to count: `activities/service.py:STATUS_LABELS`
            # was annotated, and it sat outside this ratchet for the whole of
            # CR-12 until phase 4 removed it by hand.
            if isinstance(node, ast.AnnAssign):
                targets = [node.target]
            elif isinstance(node, ast.Assign):
                targets = node.targets
            else:
                continue
            if not isinstance(node.value, ast.Dict):
                continue
            for target in targets:
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


#: Phase 5 (#1182): every gate reached zero and is hard. There is no ratchet left.
HARD = ("FK_MISSING", "ENUM_WITHOUT_LIST", "LABEL_DICTIONARIES",
        "TEMPLATE_COMPARISONS", "LOOSE_STRINGS")

#: Per gate, the dict of permanent exceptions that belongs to it. Entries
#: there are neither a violation nor progress: they are values somebody else
#: owns. They are counted separately, so a ratchet stays a promise about our own
#: work and does not carry a number that can never reach zero.
PERMANENT = {
    "FK_MISSING": "FK_NOT_OUR_LIST",
    "LABEL_DICTIONARIES": "LABELS_NOT_A_VOCABULARY",
    "LOOSE_STRINGS": "LOOSE_STRINGS_NOT_A_CODE",
    "TEMPLATE_COMPARISONS": "TEMPLATE_COMPARISONS_NOT_A_CODE",
}


def _permanent(name: str) -> dict[str, str]:
    return getattr(baseline, PERMANENT[name], {}) if name in PERMANENT else {}


def _violations(name: str) -> dict[str, str]:
    return {k: v for k, v in COLLECTORS[name]().items() if k not in _permanent(name)}


def _hard(name: str) -> None:
    """A gate at zero: every hit that is not a permanent exemption is red.

    No frozen list and no "nothing left behind" half: there is nothing left to
    leave behind. That is the difference that matters after #1268 — two
    comparisons sat on a ratchet as tolerated old work, CR-12 phase 2 made the
    attribute an enum, and they broke while the ratchet stayed green. A hard
    gate has no tolerated entries for that to happen to.

    **This IS the #1268 rule for CR-12, not an omission of it.** §B9.3 asks
    that a remaining entry on an attribute that has become an enum turns the
    gate red. After phase 5 no text gate has remaining entries — only
    exemptions, and those already carry a mandatory reason and the shelf-life
    rule (`test_every_permanent_exception_still_has_a_target`). A gate cannot
    type-check, so a rule on the attribute's *name* would flag exemptions that
    are right: `request.method`, the chat API's `role`, a Raakje proposal's
    `kind` all share a name with an enum column. Decided with the master CLI,
    27 September 2026.
    """
    found = _violations(name)
    assert not found, "\n".join(found[k] for k in sorted(found))


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


# ── 2. FK coverage, unregistered (hard since phase 5) ────────────────────────

def test_no_vocabulary_column_without_an_fk():
    """The net: a `String` column storing a list without a code table."""
    _hard("FK_MISSING")


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


# ── 5. Enum without a list (hard since phase 5) ────────────────────────────────────

def test_no_new_enum_without_a_code_list():
    """Every `Enum` under `app/` belongs to a `CodeList` or carries its reason.

    The exception that does not reach zero and should not: a `TechnicalEnum` or
    an `ExternalVocabulary`. Those are counted, not capped — see the ratchet
    table at the bottom.
    """
    _hard("ENUM_WITHOUT_LIST")


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


# ── 7-9. The three text gates (hard since phase 5) ───────────────────────────

def test_no_label_dictionary_in_python():
    _hard("LABEL_DICTIONARIES")


def test_no_template_comparison_on_a_code():
    _hard("TEMPLATE_COMPARISONS")


def test_no_loose_string_comparison():
    _hard("LOOSE_STRINGS")


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
        ("lists in the pattern (CodeList) — see §B5.3", len(lists)),
        ("… with an Enum", sum(1 for x in lists.values() if x.enum is not None)),
        ("enum-carrying columns written as Mapped[]", _count_mapped_enum_columns()),
        # Phase 5: every row below is a hard gate. Its number is measured, not
        # read from a frozen list — it is zero because the gate is green, and a
        # number above zero here comes with a red gate beside it.
        ("vocabulary columns without an FK (hard)", len(_violations("FK_MISSING"))),
        ("enums without a CodeList (hard)", len(_violations("ENUM_WITHOUT_LIST"))),
        ("enums marked technical/external (counted, not capped)", marked),
        ("label dictionaries in Python (hard)", len(_violations("LABEL_DICTIONARIES"))),
        ("template comparisons on a code (hard)",
         len(_violations("TEMPLATE_COMPARISONS"))),
        ("loose string comparisons in .py (hard)", len(_violations("LOOSE_STRINGS"))),
        # Derived from PERMANENT and not from a list of names: this row was
        # written with two dictionaries in it, phase 3 added a third, and the
        # number silently stayed behind. A table that is measured must be
        # measured from the same place the gate reads.
        ("permanent exceptions — not our vocabulary (counted, not capped)",
         sum(len(_permanent(name)) for name in PERMANENT)),
        # The twelfth gate is a guard and not a sample, so its count is zero by
        # construction — every member that reaches the output raises. What is
        # worth reading is the second number: how many values the guard saw in
        # this run. Zero there would mean it ran nowhere, which reads exactly
        # like "found nothing" (#678).
        ("enum members rendered into a template (guard, raises)", 0),
        ("values the enum guard inspected so far in this run",
         kernel_codes.rendered_under_the_guard),
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

@pytest.mark.parametrize("name", [n for n in HARD if n in PERMANENT])
def test_every_hard_gate_looks_somewhere(name):
    """#678 again, for a gate at zero: "found nothing" must not be the same as
    "looked nowhere". With the frozen list gone, the proof is the exemptions —
    a text gate that still finds each of them is still reading the right files
    in the right way."""
    found = set(COLLECTORS[name]())
    exempt = set(_permanent(name))
    assert exempt, f"`{name}` has no exemption left to prove its walk with"
    assert found >= exempt, (
        f"`{name}` no longer finds its own exemptions — the collector has fallen "
        f"silent: {sorted(exempt - found)}")


def test_the_enum_gate_looks_somewhere():
    """The enum gate has no exemption dict, so it proves its walk by counting
    the enum classes it recognised: at least one per `CodeList` with an enum."""
    seen: list[str] = []
    collect_enums_without_list(seen)
    load_all_models()
    in_lists = sum(1 for lst in registry().values() if lst.enum is not None)
    assert len(seen) >= in_lists > 10, (
        f"the enum walk recognised {len(seen)} enum classes, fewer than the "
        f"{in_lists} code lists with an enum — it has fallen silent")


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
