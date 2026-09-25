"""One shape for every fixed vocabulary: a code table, a label table, an Enum.

CR-12, `docs/change_request_12_codes_and_enums.md`. A fixed vocabulary — a
payment status, a meeting status, a relation type — used to live in whichever
shape its author reached for: a module constant, a bare string with a comment,
a dictionary of Dutch labels in a screen, sometimes a table without a foreign
key. Five shapes for one idea, so nothing could be checked and every screen
picked its own word.

This module is the one shape. Per list:

- **`<schema>.<name>_codes`** says which values exist and is the target of a
  foreign key from every column that stores one. Retiring a value is
  `is_active = false`, never a delete, so history rows keep a valid target.
- **`<schema>.<name>_labels`**, keyed on `(code, language)`, carries the human
  text. Two rows per code, `nl` and `en`, and a third language is a row for a
  translator rather than a release for a developer.
- **A plain `Enum`**, only where Python branches on the value. Plain, not
  `str, Enum`: with a `str` subclass `status == "paid"` stays quietly true and
  the mistake never surfaces.

`CodeList` ties the three together and registers itself, so the gates in
`backend/tests/test_codes_gate.py` can iterate over every list that exists
instead of over a list someone maintains by hand.

**Why `code_label` and not `label`.** `_macros.html` already has a
`label(text, for_id)` macro for form fields. A filter and a macro do not
collide technically, but a reader should not have to know that.

**Labels are data, not copy.** `app.i18n._()` stays for sentences — screen
text, messages. The label of a code is a fact about the code: it is queryable
(reports read the same words the screens show) and it belongs next to the
code. The boundary is exactly that: codes go through `code_label()`,
everything else through `_()`.

**One deviation from the API table in §B4.9**, written down rather than left
to be discovered: `create_code_list()` takes no separate `labels` argument.
One `CodeSeed` per code carries its code, its sort order and its two labels,
so a call site cannot add a code and forget its label — the two tables are
written from one list. Every other name in that table is as the CR spells it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Sequence

import sqlalchemy as sa
from sqlalchemy.types import String, TypeDecorator

logger = logging.getLogger(__name__)

#: The language every active code must have a label in. A screen may render in
#: another language; it may never render blank because a translation is missing.
FALLBACK_LANGUAGE = "nl"

#: The tone a badge falls back to when a list registered none. The gate holds
#: that a registered mapping is total, so this is for a list with no mapping at
#: all, not for a member somebody forgot.
FALLBACK_TONE = "gray"


# ── Enums that are deliberately not a code list ──────────────────────────────

class TechnicalEnum(Enum):
    """A technical distinction that is never stored and never shown.

    The reporting engine's `Operator` and `Direction` are the shape: they name
    what the code may do, not what the world contains. Subclass this and say in
    the docstring why, and the enum gate stops asking for a table.
    """


class ExternalVocabulary(Enum):
    """Someone else's list, mapped to ours at the edge.

    Mollie's payment statuses are the shape (§B4.10). Mollie can add a value
    without our migration, so a code table would turn their release into our
    webhook failure. The adapter knows the values it knows, maps them to our
    enum, and handles the unknown one explicitly.
    """


# ── The declaration ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CodeSeed:
    """One code and everything the two tables need to know about it.

    `nl` is mandatory because a screen must never render blank; `en` is
    mandatory because this change seeds both languages for every list and a
    gate that allows "later" gets "later" forever.
    """

    code: str
    nl: str
    en: str
    sort_order: int = 0
    description_nl: str | None = None
    description_en: str | None = None
    is_active: bool = True

    def label(self, language: str) -> str:
        return self.nl if language == "nl" else self.en

    def description(self, language: str) -> str | None:
        return self.description_nl if language == "nl" else self.description_en


@dataclass(frozen=True)
class CodeList:
    """One list, declared in the owning domain's `codes.py`.

    `fk_from` names the columns that store a value of this list, as
    `"schema.table.column"`. It is what the FK gate checks against the
    database, so it is the registry — not a comment.
    """

    name: str
    schema: str
    #: De twee ORM-klassen van de tabellen. `type[Any]` en niet `type`: de
    #: modellen gebruiken de oude `Column()`-stijl, dus mypy ziet hun kolommen
    #: hoe dan ook niet (§B4.8). Strakker annoteren zou een precisie suggereren
    #: die de typechecker hier niet kan waarmaken.
    codes: type[Any]
    labels: type[Any]
    enum: type[Enum] | None = None
    fk_from: tuple[str, ...] = ()
    #: A list with no storing column of its own (§B5.3 note 4): the FK gate
    #: expects nothing, the label gate still does.
    derived: bool = False
    tones: dict[str, str] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        register(self)

    @property
    def codes_table(self) -> str:
        return f"{self.schema}.{self.name}_codes"

    @property
    def labels_table(self) -> str:
        return f"{self.schema}.{self.name}_labels"


_REGISTRY: dict[str, CodeList] = {}


def register(code_list: CodeList) -> None:
    """Add a list to the registry the gates iterate over.

    A second list under the same name is refused: `code_label("status")` must
    mean one thing. Re-registering the identical declaration is a no-op, since
    a module can be imported twice through two paths.
    """
    existing = _REGISTRY.get(code_list.name)
    if existing is not None and existing != code_list:
        raise ValueError(
            f"two different code lists are called {code_list.name!r}: "
            f"{existing.codes_table} and {code_list.codes_table}. A list name is "
            f"how `code_label()` finds it, so it has to be unique.")
    _REGISTRY[code_list.name] = code_list


def registry() -> dict[str, CodeList]:
    """Every declared list. Import the domains first — `load_all_code_lists()`."""
    return dict(_REGISTRY)


def code_list(name: str) -> CodeList:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise LookupError(
            f"no code list called {name!r}. Declare it in the owning domain's "
            f"codes.py and export it through its api.py; known lists: "
            f"{sorted(_REGISTRY)}") from None


def register_tones(name: str, tones: dict[Any, str]) -> None:
    """Attach the badge tones of a list, from the UI module that owns them.

    A tone is a design-system decision, not a translation: it changes with the
    house style and not with the language (§B4.5). So it stays in Python, next
    to the screen that draws the badge, and the code table keeps no `tone`
    column where a translator would find one.
    """
    target = code_list(name).tones
    target.clear()
    target.update({_code_of(code): badge for code, badge in tones.items()})


# ── The column type ──────────────────────────────────────────────────────────

class EnumColumn(TypeDecorator):
    """Stores `member.value`, reads the member back. Never the member name.

    This is the whole reason the type exists. `sa.Enum(SomeEnum)` stores the
    member **name** by default, so a column declared against `PaymentStatus`
    would hold `PAID` where every query, export and report expects `paid` — and
    nothing raises. The corruption is silent and it is in the data, which is
    the expensive kind.

    A value that is in the column but in no member raises on read rather than
    yielding a bare string: a bare string compares false against every member,
    which is the same silent failure one layer up.
    """

    impl = String
    cache_ok = True

    def __init__(self, enum_cls: type[Enum], length: int | None = None, **kw: Any):
        self.enum_cls = enum_cls
        super().__init__(length=length, **kw)

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, self.enum_cls):
            return str(value.value)
        if isinstance(value, str):
            # A raw code is accepted — a migration or a form may hand one over —
            # but only when it really is a code of this list.
            return str(self.enum_cls(value).value)
        raise TypeError(
            f"{self.enum_cls.__name__}: cannot store {value!r} ({type(value).__name__}); "
            f"pass a member or its code")

    def process_result_value(self, value: Any, dialect: Any) -> Enum | None:
        if value is None:
            return None
        try:
            return self.enum_cls(value)
        except ValueError:
            raise ValueError(
                f"{self.enum_cls.__name__}: the database holds {value!r}, which is "
                f"not one of {[m.value for m in self.enum_cls]}. A retired code stays "
                f"a member (§B4.3), so this is corrupt data, not a rendering case."
            ) from None


def _code_of(value: Any) -> str:
    """The stored code of an enum member, a `CodeSeed` or a plain string."""
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, CodeSeed):
        return value.code
    return str(value)


# ── Labels ───────────────────────────────────────────────────────────────────

_label_cache: dict[tuple[str, str], dict[str, str]] = {}
_active_cache: dict[str, list[str]] = {}
_missing_logged: set[tuple[str, str]] = set()


def reset_label_cache() -> None:
    """Drop the process cache. For tests, and for the management screen of R7."""
    _label_cache.clear()
    _active_cache.clear()
    _missing_logged.clear()


def _language() -> str:
    """The language part of the active locale: `nl_BE` → `nl`."""
    from app.i18n import current_locale

    return (current_locale.get() or FALLBACK_LANGUAGE).replace("-", "_").split("_")[0]


def _labels_of(name: str, language: str) -> dict[str, str]:
    key = (name, language)
    if key not in _label_cache:
        from app.database import SessionLocal

        lst = code_list(name)
        with SessionLocal() as db:
            rows = db.execute(
                sa.select(lst.labels.code, lst.labels.value)
                .where(lst.labels.language == language)
            ).all()
        _label_cache[key] = {code: value for code, value in rows}
    return _label_cache[key]


def _active_of(name: str) -> list[str]:
    if name not in _active_cache:
        from app.database import SessionLocal

        lst = code_list(name)
        with SessionLocal() as db:
            rows = db.execute(
                sa.select(lst.codes.code)
                .where(lst.codes.is_active.is_(True))
                .order_by(lst.codes.sort_order, lst.codes.code)
            ).all()
        _active_cache[name] = [row[0] for row in rows]
    return _active_cache[name]


def code_label(name: str, code: Any, language: str | None = None) -> str:
    """The human text of one code, in the active language.

    Falls back to `nl`, and then to the code itself so a screen never renders
    blank under `StrictUndefined`; the fallback is logged once per (list, code)
    rather than per render.

    Jobs have no request and therefore no locale (§B4.4): mail, newsletter
    sending and workflow runs pass `language=` explicitly, or an English tenant
    reads Dutch labels in its own e-mail and no gate can see it.
    """
    if code is None or code == "":
        return ""
    wanted = language or _language()
    stored = _code_of(code)
    for candidate in (wanted, FALLBACK_LANGUAGE):
        text = _labels_of(name, candidate).get(stored)
        if text:
            return text
    if (name, stored) not in _missing_logged:
        _missing_logged.add((name, stored))
        logger.warning("no label for code %r in list %r (language %r); showing the code",
                       stored, name, wanted)
    return stored


def code_labels(name: str, language: str | None = None) -> list[tuple[str, str]]:
    """The `(code, label)` pairs of the **active** codes, in `sort_order`.

    This is what a select list and a report dimension iterate over — the last
    place where a Python list decided in which order a user sees the options.
    """
    return [(code, code_label(name, code, language)) for code in _active_of(name)]


def tone(name: str, code: Any) -> str:
    """The badge tone of a code, from the mapping the UI module registered."""
    if code is None or code == "":
        return FALLBACK_TONE
    return code_list(name).tones.get(_code_of(code), FALLBACK_TONE)


def install_jinja_codes(env: Any) -> None:
    """Register `code_label` and `tone` as filters, next to `install_jinja_i18n`.

    `{{ meeting.status | code_label("meeting_status") }}` is the only way a
    template turns a code into text. A template that reaches for a dictionary
    instead trips the label-dictionary gate; one that compares the code to a
    literal trips the template gate.
    """
    env.filters["code_label"] = lambda code, name, language=None: code_label(
        name, code, language)
    env.filters["tone"] = lambda code, name: tone(name, code)


# ── The migration helper ─────────────────────────────────────────────────────

def _inspector(op: Any) -> Any:
    return sa.inspect(op.get_bind())


def _has_table(op: Any, schema: str, table: str) -> bool:
    return _inspector(op).has_table(table, schema=schema)


def _has_fk(op: Any, schema: str, table: str, name: str) -> bool:
    return any(fk.get("name") == name
               for fk in _inspector(op).get_foreign_keys(table, schema=schema))


def create_code_list(
    op: Any,
    schema: str,
    name: str,
    codes: Sequence[CodeSeed],
    fk_from: Iterable[str] = (),
    code_length: int = 50,
    value_length: int = 150,
) -> None:
    """Create one list — both tables, the seed rows and the foreign keys.

    One call per list, so forty-nine lists are forty-nine calls and not
    forty-nine hand-written migrations that each get the shape slightly wrong.
    Idempotent on all four environments: the tables are created only when
    absent and the rows are upserted.

    **The rows are checked before the foreign key goes on.** A column that
    holds a value this list does not know aborts the migration, naming the
    values and their counts, instead of failing on the constraint with
    Postgres's own wording. Two ways a foreign key on existing data trips, and
    this is the second one; the first is a writer nobody looked for — the
    public form, the JSON API, the import — and that one is a reading job, not
    something a helper can do for you.

    The count is over **the whole table**. `deleted_at` is a column, not a
    filter the database knows, so a soft-deleted row needs a valid target like
    any other.
    """
    bind = op.get_bind()
    codes_table = f"{name}_codes"
    labels_table = f"{name}_labels"

    if not _has_table(op, schema, codes_table):
        op.create_table(
            codes_table,
            sa.Column("code", sa.String(code_length), primary_key=True),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            schema=schema,
        )
    if not _has_table(op, schema, labels_table):
        op.create_table(
            labels_table,
            sa.Column("code", sa.String(code_length), primary_key=True),
            sa.Column("language", sa.String(5), primary_key=True),
            sa.Column("value", sa.String(value_length), nullable=False),
            sa.Column("description", sa.String(255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["code"], [f"{schema}.{codes_table}.code"],
                                    name=f"fk_{name}_labels_code"),
            sa.ForeignKeyConstraint(["language"], ["mdm.language_codes.code"],
                                    name=f"fk_{name}_labels_language"),
            schema=schema,
        )

    # Every code first, then every label. The order matters and the language
    # list is where it shows: `mdm.language_labels.language` points at
    # `mdm.language_codes.code`, so writing the labels of `nl` before the row
    # for `en` exists fails on that very foreign key. Which is the list working
    # as intended — but it makes the loop order part of the contract.
    for seed in codes:
        bind.execute(
            sa.text(f"INSERT INTO {schema}.{codes_table} "
                    f"(code, sort_order, is_active, created_at) "
                    f"VALUES (:code, :sort_order, :is_active, :now) "
                    f"ON CONFLICT (code) DO NOTHING"),
            {"code": seed.code, "sort_order": seed.sort_order,
             "is_active": seed.is_active, "now": _now()},
        )
    for seed in codes:
        for language in ("nl", "en"):
            bind.execute(
                sa.text(f"INSERT INTO {schema}.{labels_table} "
                        f"(code, language, value, description, created_at, updated_at) "
                        f"VALUES (:code, :language, :value, :description, :now, :now) "
                        f"ON CONFLICT (code, language) DO NOTHING"),
                {"code": seed.code, "language": language,
                 "value": seed.label(language),
                 "description": seed.description(language), "now": _now()},
            )

    known = {seed.code for seed in codes}
    for column in fk_from:
        add_code_fk(op, column, schema, name, known)


def add_code_fk(op: Any, column: str, schema: str, name: str,
                known: set[str] | None = None) -> None:
    """Point one storing column at a code table, after proving the data fits.

    `column` is `"schema.table.column"` — the same spelling the gate and the
    ratchet baseline use, so the three read alike.
    """
    col_schema, table, col = column.split(".")
    constraint = f"fk_{table}_{col}_code"
    if _has_fk(op, col_schema, table, constraint):
        return

    bind = op.get_bind()
    stray = bind.execute(sa.text(
        f'SELECT "{col}" AS value, count(*) AS n FROM {col_schema}.{table} '
        f'WHERE "{col}" IS NOT NULL '
        f'  AND "{col}" NOT IN (SELECT code FROM {schema}.{name}_codes) '
        f'GROUP BY "{col}" ORDER BY n DESC')).all()
    if stray:
        found = ", ".join(f"{row.value!r}×{row.n}" for row in stray)
        raise RuntimeError(
            f"{column} holds {sum(row.n for row in stray)} row(s) whose value is not in "
            f"{schema}.{name}_codes: {found}. Add the code, map the value, or retire it "
            f"— the foreign key would fail on these rows, soft-deleted ones included. "
            f"Known codes: {sorted(known) if known else 'see the table'}.")

    op.create_foreign_key(constraint, table, f"{name}_codes",
                          [col], ["code"],
                          source_schema=col_schema, referent_schema=schema)


def retire_code(op: Any, schema: str, name: str, code: str,
                used_by: Iterable[str] = ()) -> None:
    """Flip a code to inactive and log how many rows still carry it.

    Never a delete: a history row and an old record keep a valid target, and
    the enum keeps the member so the value never reads back as a bare string.
    """
    bind = op.get_bind()
    bind.execute(sa.text(f"UPDATE {schema}.{name}_codes SET is_active = false "
                         f"WHERE code = :code"), {"code": code})
    for column in used_by:
        col_schema, table, col = column.split(".")
        count = bind.execute(sa.text(
            f'SELECT count(*) FROM {col_schema}.{table} WHERE "{col}" = :code'),
            {"code": code}).scalar_one()
        logger.info("retired %s.%s_codes.%s — %s still carries it in %s row(s)",
                    schema, name, code, column, count)


def _now() -> Any:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def load_all_code_lists() -> None:
    """Import every domain's `codes.py` so the registry is complete.

    The gates iterate over the registry, so a list that is never imported is a
    list that is never checked. `app.domains.registry.load_all_models` calls
    this after the models, since a declaration names its two ORM classes.
    """
    import importlib
    from pathlib import Path

    domains = Path(__file__).resolve().parents[1] / "domains"
    for module in sorted(domains.glob("*/codes.py")):
        importlib.import_module(f"app.domains.{module.parent.name}.codes")
