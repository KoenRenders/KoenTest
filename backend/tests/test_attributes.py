"""The attribute register of the kernel: key, label and classification rules (CR-33 T1).

Each test can go red for its own reason: two entries with one key accepted, two
labels in one entity accepted, an empty help accepted, an unclassified entry
accepted, a lookup that names no known keys, a technical rule that reads a name.
Proven by adding the violation (an additive proof, never by breaking an entry
that exists), 15 October 2026.
"""

import pytest
import sqlalchemy as sa

from app.kernel import attributes as reg
from app.kernel.attributes import AiExposure, Attribute


@pytest.fixture(autouse=True)
def _isolated_registry(monkeypatch):
    """The tests add entries; the real registry must not see them."""
    monkeypatch.setattr(reg, "_REGISTRY", dict(reg._REGISTRY))


def _attr(key="probe.person.first_name", label="Voornaam", **over):
    fields = dict(
        key=key,
        columns=("probe.person.first_name",),
        label=label,
        name_en="First name",
        help="The first name of a person.",
        ai_exposure=AiExposure.TOKENISED,
    )
    fields.update(over)
    return Attribute(**fields)


def test_two_entries_with_one_key_are_refused_and_the_identical_one_is_not():
    first = _attr()
    assert _attr() == first, "re-importing the same declaration is a no-op"
    with pytest.raises(ValueError, match="probe.person.first_name"):
        _attr(label="Naam")


def test_two_labels_in_one_entity_are_refused_but_two_entities_may_share_one():
    _attr(key="probe.person.name", label="Naam")
    with pytest.raises(ValueError, match="both labelled 'Naam'"):
        _attr(key="probe.person.contact_name", label="Naam")
    _attr(key="probe.registration.contact_name", label="Naam")  # another entity: fine
    _attr(key="probe.person.nickname_a", label=None)  # no label yet: never a clash
    _attr(key="probe.person.nickname_b", label=None)


def test_an_entry_needs_help_and_a_classification():
    with pytest.raises(ValueError, match="no help line"):
        _attr(key="probe.person.nohelp", label=None, help="  ")
    with pytest.raises(TypeError, match="AiExposure"):
        _attr(key="probe.person.nolevel", label=None, ai_exposure="internal")


def test_a_key_names_domain_entity_and_field():
    with pytest.raises(ValueError, match="<domain>.<entity>.<field>"):
        _attr(key="probe.first_name", label=None)


def test_an_unknown_key_names_the_known_keys_of_its_domain():
    _attr()
    with pytest.raises(LookupError, match="probe.person.first_name"):
        reg.attribute("probe.person.surname")


def test_the_label_text_is_the_catalogue_sentence_or_the_english_name():
    assert _attr().text == "Voornaam"
    assert _attr(key="probe.person.unshown", label=None, name_en="Unshown").text == "Unshown"


def test_technical_is_read_from_the_metadata_not_from_the_name():
    """A foreign key to a code list is a datum; an unkeyed `external_id` is a datum;
    a keyed id, `tenant_id` and the timestamps are not."""
    meta = sa.MetaData()
    sa.Table("kinds_codes", meta, sa.Column("code", sa.String, primary_key=True), schema="probe")
    sa.Table("owners", meta, sa.Column("id", sa.Integer, primary_key=True), schema="probe")
    sa.Table(
        "things",
        meta,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("tenant_id", sa.Integer),
        sa.Column("owner_id", sa.Integer, sa.ForeignKey("probe.owners.id")),
        sa.Column("external_id", sa.String),
        sa.Column("kind", sa.String, sa.ForeignKey("probe.kinds_codes.code")),
        sa.Column("created_by", sa.String),
        sa.Column("created_at", sa.DateTime),
        sa.Column("deleted_at", sa.DateTime),
        schema="probe",
    )
    business = reg.business_columns(meta)
    assert business == ["probe.things.external_id", "probe.things.kind", "probe.things.created_by"]
    assert not any("codes" in c or "owners" in c for c in business), "code tables hold no datum"


def test_the_code_label_and_history_tables_are_no_business_tables():
    meta = sa.MetaData()
    for name in ("x_codes", "x_labels", "x_history", "x"):
        sa.Table(
            name, meta, sa.Column("id", sa.Integer, primary_key=True), sa.Column("v", sa.String)
        )
    assert reg.business_columns(meta) == ["public.x.v"]
