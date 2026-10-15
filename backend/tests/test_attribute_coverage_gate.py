"""Refuses a stored business column that no attribute names, and an attribute that names a column that does not exist · hard · since #2007.

The register starts from the data model (CR-33 C4.0): a classification can only be
complete against a closed set, and the stored columns are one (the ORM metadata).
Every column of every table that is no code, label or history table is either
technical by what the metadata says (`kernel.attributes.is_technical`) or named by
at least one entry of the register.

Proven red (15 October 2026), by ADDING the violation: a column `probe_nickname`
added to `mdm.Person` fails `test_every_business_column_has_an_attribute` with
`mdm.persons.probe_nickname` in the message (then removed). The gate also asserts it
found more than 300 business columns before it judges, so a changed glob or an
emptied metadata cannot turn it green for the wrong reason.
"""

import sqlalchemy as sa

from app.database import Base
from app.domains.registry import load_all_models
from app.kernel import attributes as reg

load_all_models()


def _uncovered(metadata, covered) -> list[str]:
    return [c for c in reg.business_columns(metadata) if c not in covered]


def test_every_business_column_has_an_attribute():
    business = reg.business_columns(Base.metadata)
    assert len(business) > 300, f"the gate found only {len(business)} business columns"
    missing = _uncovered(Base.metadata, reg.covered_columns())
    assert not missing, (
        "these columns have no attribute: add each to its domain's attributes.py with "
        "its classification (the file of the table's domain; the kernel's tables in "
        "kernel/data_attributes.py):\n  " + "\n  ".join(missing)
    )


def test_a_column_without_an_entry_is_named_with_its_file():
    """The gate can go red: a throw-away table with one column and an empty register."""
    meta = sa.MetaData()
    sa.Table(
        "probe_things",
        meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("colour", sa.String),
        schema="probe",
    )
    assert _uncovered(meta, set()) == ["probe.probe_things.colour"]
    assert _uncovered(meta, {"probe.probe_things.colour"}) == []


def test_an_unkeyed_id_is_business():
    """`external_id` and `provider_payment_id` carry no foreign key: they are data."""
    business = set(reg.business_columns(Base.metadata))
    assert "mdm.external_numbers.external_id" in business
    assert "payment.gateway_payments.provider_payment_id" in business
    assert "mdm.contact_details.contact_type_code" in business, "a code column is a datum"
    assert "activities.registrations.id" not in business and not any(
        c.endswith(".tenant_id") or c.endswith(".created_at") for c in business
    )


def test_an_entry_naming_a_column_that_does_not_exist_is_refused():
    """A typo in `columns` would leave the real column uncovered and the gate silent
    about the entry; every named column is checked against the metadata."""
    real = {
        f"{(t.schema or 'public')}.{t.name}.{c.name}"
        for t in Base.metadata.tables.values()
        for c in t.columns
    }
    unknown = sorted(
        f"{key}: {column}"
        for key, attr in reg.registry().items()
        for column in attr.columns
        if column not in real
    )
    assert not unknown, "entries name columns that do not exist:\n  " + "\n  ".join(unknown)
