"""The attribute register: one name and one AI classification per stored datum.

CR-33, `docs/change_request_33_attribute_register.md`. A datum used to be named
where each screen showed it and classified for a model only where the reporting
universe knew it. This module is the one place: every domain declares its data
in its own `attributes.py`, beside its `codes.py`, and every reader — the kit's
fields, the changes list, the import's check, the reports, the AI port — asks
the kernel by key.

It copies the form of `kernel/codes.py` on purpose: a frozen declaration in the
owning domain that registers itself, a registry the gates iterate, a lookup by
name that refuses a wrong key, and `columns` naming the storing columns as
`"schema.table.column"` so a gate can check the register against the database.

**Model-first.** The register starts from the ORM, not from the screens: the
coverage gate (`backend/tests/test_attribute_coverage_gate.py`) refuses a
business column that no entry names. A label is what a datum gets once a screen
shows it, so `label` may be `None` and the classification may not.

**Technical is what the metadata says, never a name** (build read B3): the
primary key, a column with a foreign key to a table that is no code list,
`tenant_id` and the three timestamps. Those need no entry, but may have one when
a report or a screen shows them. `external_id`, `provider_payment_id` and the
author columns (`created_by`, `sent_by`) carry no foreign key and are data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.kernel.codes import TechnicalEnum


class AiExposure(str, TechnicalEnum):
    """How far a datum may travel towards a language model (CR-07 §5.1, CR-33 C4.4).

    `TechnicalEnum` (CR-12 §B4.9): a classification of our own code, never stored
    and never shown. The Dutch words the user reads are *publiek*, *intern*,
    *token* and *nooit*.

    **No default, on purpose.** A flag somebody can forget is the wrong default
    on an outgoing AI channel: forgetting would decide what goes to the provider.
    An `Attribute` without a classification does not import.
    """

    #: The public assistant may say it (an activity's name, a shop price).
    PUBLIC = "public"
    #: The back-office assistant only (`PLAIN` of the reporting universe, renamed).
    INTERNAL = "internal"
    #: Points at a person. The back-office assistant sees the entity token
    #: (`persoon-90`), never the value.
    TOKENISED = "tokenised"
    #: No model, ever.
    NONE = "none"


#: Tables that hold no business data of their own: the values of a code list,
#: the labels of those values, and the history of a record.
_NON_BUSINESS_SUFFIXES = ("_codes", "_labels", "_history")

_TIMESTAMPS = frozenset({"created_at", "updated_at", "deleted_at"})


@dataclass(frozen=True)
class Attribute:
    """One stored business datum, declared in the owning domain's `attributes.py`.

    - `key` names the datum: `<domain>.<entity>.<field>`, unique.
    - `columns` are the storing columns as `"schema.table.column"`: one for a
      plain field, several for a composite, the same column in several entries
      for a column that holds several data (`mdm.contact_details.value`), none
      for a derived datum (a measure, an age group).
    - `label` is the Dutch word the user reads, as a sentence of the translation
      catalogue; `None` until a screen shows the datum. Unique within an entity.
    - `name_en` is the datum's English name (ISO/IEC 11179: name and definition
      are separate).
    - `help` is one line saying what the datum is; never empty.
    - `ai_exposure` is the classification, never defaulted.
    """

    key: str
    columns: tuple[str, ...]
    label: str | None
    name_en: str
    help: str
    ai_exposure: AiExposure

    def __post_init__(self) -> None:
        parts = self.key.split(".")
        if len(parts) != 3 or not all(parts):
            raise ValueError(f"attribute key {self.key!r} must read <domain>.<entity>.<field>")
        if not self.help.strip():
            raise ValueError(f"attribute {self.key!r} has no help line")
        if not isinstance(self.ai_exposure, AiExposure):
            raise TypeError(f"attribute {self.key!r} has no AiExposure classification")
        register(self)

    @property
    def domain(self) -> str:
        return self.key.split(".")[0]

    @property
    def entity(self) -> str:
        return self.key.split(".")[1]

    @property
    def text(self) -> str:
        """The label as the user reads it (the catalogue's translation), or the
        English name for a datum no screen shows."""
        if self.label is None:
            return self.name_en
        from app.i18n import _

        return _(self.label)


_REGISTRY: dict[str, Attribute] = {}
_LOADED = False


def register(attr: Attribute) -> None:
    """Add an entry to the registry the gates iterate over.

    Two entries with one key are refused, and so are two non-empty labels within
    one entity: a screen that reads `attribute(key).label` must mean one thing.
    Re-registering the identical declaration is a no-op (a module can be imported
    through two paths).
    """
    existing = _REGISTRY.get(attr.key)
    if existing is not None:
        if existing != attr:
            raise ValueError(
                f"two different attributes are called {attr.key!r}: a key is how "
                f"`attribute()` finds the datum, so it has to be unique."
            )
        return
    if attr.label:
        for other in _REGISTRY.values():
            if (
                other.domain == attr.domain
                and other.entity == attr.entity
                and other.label == attr.label
            ):
                raise ValueError(
                    f"{attr.key!r} and {other.key!r} are both labelled {attr.label!r} "
                    f"within {attr.domain}.{attr.entity}: one label, one datum."
                )
    _REGISTRY[attr.key] = attr


def registry() -> dict[str, Attribute]:
    """Every declared entry. Import the domains first — `load_all_attributes()`."""
    return dict(_REGISTRY)


def attribute(key: str) -> Attribute:
    """The entry of `key`. A wrong key is a programming error and raises
    everywhere, PROD included; the template gate resolves every key a template
    names before it can reach a screen."""
    try:
        return _REGISTRY[key]
    except KeyError:
        if not _LOADED:
            # A caller that ran before the domains were imported (a script, a unit
            # test): load the declarations once, as the app's start does.
            load_all_attributes()
            return attribute(key)
        domain = key.split(".")[0]
        known = sorted(k for k in _REGISTRY if k.split(".")[0] == domain)
        raise LookupError(
            f"no attribute called {key!r}. Declare it in the owning domain's "
            f"attributes.py; known keys of {domain!r}: {known or sorted(_REGISTRY)}"
        ) from None


def field_label(key: str | None, label: str | None) -> str | None:
    """The label of a kit field (CR-33 F2): `attribute=` reads it from the register, a
    typed `label` stays for a field that is no datum (a search box). Both at once is
    refused, and so is an entry no screen has a label for. Raised everywhere, PROD
    included: the template gate resolves every key before it can reach a screen
    (`tests/integration/test_field_labels_ratchet.py`)."""
    if key is None:
        return label
    if label is not None:
        raise ValueError(
            f"a kit field gets its label from `attribute={key!r}` or from `label=`, not both"
        )
    entry = attribute(key)
    if entry.label is None:
        raise ValueError(f"attribute {key!r} has no label: add one in its attributes.py")
    return entry.text


def covered_columns() -> set[str]:
    """Every `schema.table.column` some entry names."""
    return {column for attr in _REGISTRY.values() for column in attr.columns}


def is_business_table(table: Any) -> bool:
    """A table that holds data of its own: no code list, no label list, no history."""
    return not table.name.endswith(_NON_BUSINESS_SUFFIXES)


def is_technical(column: Any) -> bool:
    """The one rule, read from the metadata (CR-33 F10): the primary key, a column
    with a foreign key to a table that is no code list, `tenant_id` and the
    timestamps. A name decides nothing but those four, and a code column keeps
    its entry because its key points at a code list."""
    if column.primary_key or column.name == "tenant_id" or column.name in _TIMESTAMPS:
        return True
    return any(not key.column.table.name.endswith("_codes") for key in column.foreign_keys)


def column_path(column: Any) -> str:
    """`schema.table.column` as `Attribute.columns` and the gates spell it."""
    table = column.table
    return f"{table.schema or 'public'}.{table.name}.{column.name}"


def business_columns(metadata: Any) -> list[str]:
    """Every `schema.table.column` the coverage gate expects an entry for."""
    found: list[str] = []
    for table in metadata.sorted_tables:
        if not is_business_table(table):
            continue
        found.extend(column_path(c) for c in table.columns if not is_technical(c))
    return found


def load_all_attributes() -> None:
    """Import every domain's `attributes.py` so the registry is complete, as
    `load_all_code_lists()` does for the code lists."""
    import importlib
    from pathlib import Path

    global _LOADED
    _LOADED = True
    # The kernel's own tables (jobs, tenant settings) are declared beside it.
    importlib.import_module("app.kernel.data_attributes")
    domains = Path(__file__).resolve().parents[1] / "domains"
    for module in sorted(domains.glob("*/attributes.py")):
        importlib.import_module(f"app.domains.{module.parent.name}.attributes")
