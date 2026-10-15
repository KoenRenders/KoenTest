"""The universe derives its names and descriptions from the attribute register (CR-33 T4, T5, T11).

Each test can go red for its own reason: an object whose attribute does not exist (the
lookup names it), a date grain on an attribute that is no date (proved with an added object in
`test_a_grain_on_an_attribute_that_is_no_date_is_refused`), an object that carries its own
`name` or `description` again (the field list is checked), a name that stopped reading the
register (the composed names are compared with the entry).
"""

import dataclasses

import sqlalchemy as sa

from app.database import Base
from app.domains.reporting.universe import BY_KEY, OBJECTS, Grain, UniverseObject
from app.kernel.attributes import attribute

#: Dates that are derived by a report view and have no stored column (their entry names none).
DERIVED_DATES = {"reporting.activities.activity_date", "reporting.activities.year_first_date"}


def test_every_object_names_an_attribute_that_exists():
    assert len(OBJECTS) > 100, "the gate found no universe"
    for obj in OBJECTS:
        entry = attribute(obj.attribute)  # a LookupError names the object's key below
        assert entry.label, f"{obj.key}: attribute {obj.attribute} has no label to be called by"
        assert obj.name and obj.description, obj.key


def _grain_problems(objects) -> list[str]:
    problems = []
    for obj in objects:
        if obj.grain is None:
            continue
        entry = attribute(obj.attribute)
        if entry.key in DERIVED_DATES:
            continue
        kinds = []
        for column in entry.columns:
            schema, table, name = column.split(".")
            kinds.append(Base.metadata.tables[f"{schema}.{table}"].columns[name].type)
        if not (kinds and all(isinstance(k, (sa.Date, sa.DateTime)) for k in kinds)):
            problems.append(f"{obj.key}: a grain of {obj.attribute}, which is no date ({kinds})")
    return problems


def test_a_grain_stands_on_a_date():
    """The date's entry names a date column (or is a derived date of the report views)."""
    assert len([o for o in OBJECTS if o.grain is not None]) >= 48, "no grain objects found"
    assert not _grain_problems(OBJECTS)


def test_a_grain_on_an_attribute_that_is_no_date_is_refused():
    """The gate can go red: an added object with a grain on an activity's name."""
    wrong = dataclasses.replace(
        BY_KEY["registration_date_year"], attribute="activities.activity.name"
    )
    assert _grain_problems([wrong]) and "no date" in _grain_problems([wrong])[0]


def test_a_grain_object_reads_the_dates_label_and_the_grain_word():
    obj = BY_KEY["registration_date_year"]
    assert obj.name == f"{attribute(obj.attribute).label} › {Grain.YEAR.word}"
    assert obj.description.endswith("Opgerold tot jaar.")
    assert obj.description.startswith(attribute(obj.attribute).help)


def test_a_qualifier_and_a_note_compose_into_the_name_and_the_description():
    obj = BY_KEY["address_municipality"]
    assert obj.name == "Gemeente (adres)"
    assert obj.description == f"{attribute(obj.attribute).help} {obj.note}"
    assert BY_KEY["member_municipality"].attribute == obj.attribute, "one datum, two roles"


def test_an_object_carries_no_name_or_description_of_its_own():
    fields = {f.name for f in dataclasses.fields(UniverseObject)}
    assert "name" not in fields and "description" not in fields, (
        "a universe object takes its name and description from its attribute (CR-33 F4)"
    )
    assert "attribute" in fields


def test_the_relation_word_is_the_registers():
    """F9: *Relatietype* became *Relatie*, in the register and so in the report."""
    assert BY_KEY["person_relation_type"].name == "Relatie"
