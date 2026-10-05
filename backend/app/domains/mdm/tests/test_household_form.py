"""The household's form is read by name, and what is no date is noted at its field (#1590)."""

from datetime import date

from starlette.datastructures import FormData

from app.domains.mdm.household_form import household_from_form
from app.domains.mdm.household_save import AddressRow, EmailRow


def _form(*pairs) -> FormData:
    return FormData(list(pairs))


def test_the_rows_are_read_in_the_order_of_their_order_fields():
    form = _form(
        ("h_order", "12"),
        ("h.12.first_name", " An "),
        ("h.12.last_name", "Voorbeeld"),
        ("h.12.date_of_birth", "1980-01-01"),
        ("h.12.gender_code", "F"),
        ("h.12.mobile", "0470 00 00 00"),
        ("e_order.12", "7"),
        ("e.7.value", "an@example.com"),
        ("e_order.12", "nx1"),
        ("e.nx1.value", "an.werk@example.com"),
        ("e_primary.12", "nx1"),
        ("h_order", "nb2"),
        ("h.nb2.first_name", "Cas"),
        ("h.nb2.last_name", "Voorbeeld"),
    )
    found = household_from_form(form)
    assert [p.key for p in found.persons] == ["12", "nb2"]
    an, cas = found.persons
    assert (an.first_name, an.date_of_birth, an.gender_code) == ("An", date(1980, 1, 1), "F")
    assert an.mobile == "0470 00 00 00" and an.phone == ""
    assert an.emails == [
        EmailRow("7", "an@example.com", primary=False),
        EmailRow("nx1", "an.werk@example.com", primary=True),
    ]
    assert (cas.date_of_birth, cas.gender_code, cas.emails) == (None, None, [])
    assert found.errors == [] and found.address is None, "no address field, no address"


def test_the_address_is_read_only_when_the_form_carries_it():
    found = household_from_form(
        _form(
            ("address.street", "Dorpsstraat"),
            ("address.house_number", "1"),
            ("address.postal_code", "2400"),
        )
    )
    assert found.address == AddressRow("Dorpsstraat", "1", "", "2400")
    assert found.persons == []


def test_a_birth_date_that_is_no_date_is_noted_at_its_field_and_the_reading_goes_on():
    """Until #1590 this was a 500: `date.fromisoformat` raised a `ValueError` no
    door caught."""
    found = household_from_form(
        _form(
            ("h_order", "12"),
            ("h.12.first_name", "An"),
            ("h.12.date_of_birth", "31/02/1980"),
            ("h_order", "13"),
            ("h.13.first_name", "Bert"),
            ("h.13.date_of_birth", "1981-02-02"),
        )
    )
    assert [(e.field, e.message) for e in found.errors] == [
        ("h.12.date_of_birth", "Ongeldige geboortedatum.")
    ]
    assert found.persons[0].date_of_birth is None
    assert found.persons[1].date_of_birth == date(1981, 2, 2), "the next row is still read"
