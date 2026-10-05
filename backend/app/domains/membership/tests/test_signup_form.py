"""The "Word lid" form is read by name into a `FamilyCreate` (#1590).

`signup_from_form` reads what the public page sends — the household as a
repeating group, the address, the payment method — and either answers the
household to create or says, at its field, everything that stands in the way.
No database: the form is a plain `FormData`, as the route hands it over.

Each refusal is asked with its exact place, because the place is what the page
marks: a refusal named at another field (or at none) would still be a refusal,
and the visitor would look for it in the wrong row. Every refusal test starts
from the same complete form with one thing taken out, and
`test_a_complete_household_is_read` proves that form is accepted — so the one
thing taken out is the cause.
"""

from __future__ import annotations

from datetime import date

import pytest
from starlette.datastructures import FormData

from app.domains.membership.signup_form import signup_from_form

MAIN = "an.voorbeeld@example.com"
WORK = "an.werk@example.com"


def _pairs(**changes) -> list[tuple[str, str]]:
    """A complete sign-up of one main member; `changes` replace a field by name,
    and `None` takes the field out of the form."""
    fields: dict[str, str | None] = {
        "h.n0.first_name": "An",
        "h.n0.last_name": "Voorbeeld",
        "h.n0.date_of_birth": "1980-01-01",
        "h.n0.gender_code": "F",
        "h.n0.mobile": "0470 00 00 00",
        "e.n0e.value": MAIN,
        "e_primary.n0": "n0e",
        "address.street": "Dorpsstraat",
        "address.house_number": "1",
        "address.bus_number": "",
        "address.postal_code": "2400",
        "payment_method": "transfer",
    }
    fields.update(changes)
    order = [("h_order", "n0"), ("e_order.n0", "n0e")]
    return order + [(name, value) for name, value in fields.items() if value is not None]


def _person(key: str, first_name: str, **fields) -> list[tuple[str, str]]:
    """One more person row, complete unless `fields` say otherwise."""
    row = {
        "first_name": first_name,
        "last_name": "Voorbeeld",
        "date_of_birth": "2010-03-03",
        "gender_code": "M",
        **fields,
    }
    return [("h_order", key)] + [(f"h.{key}.{name}", value) for name, value in row.items()]


def _read(pairs):
    return signup_from_form(FormData(pairs))


def _refusals(pairs) -> list[tuple[str, str]]:
    data, errors = _read(pairs)
    assert data is None, "a refused form answers no household"
    return [(e.field, e.message) for e in errors]


# ── What a good form becomes ─────────────────────────────────────────────────


def test_a_complete_household_is_read():
    """The main member first, with what only they carry; the address and the
    payment method beside the persons."""
    data, errors = _read(
        _pairs(**{"address.bus_number": "b"})
        + _person("n1", "Bert", relation_type="PARTNER")
        + _person("n2", "Cas", relation_type="KIND")
    )
    assert errors == []
    assert [(m.first_name, m.relation_type.value) for m in data.members] == [
        ("An", "HOOFDLID"),
        ("Bert", "PARTNER"),
        ("Cas", "KIND"),
    ]
    head = data.members[0]
    assert (head.last_name, head.date_of_birth, head.gender_code) == (
        "Voorbeeld",
        date(1980, 1, 1),
        "F",
    )
    assert (head.email, head.extra_emails, head.mobile) == (MAIN, [], "0470 00 00 00")
    assert head.phone is None, "an empty phone is no phone"
    assert (data.street, data.house_number, data.bus_number, data.postal_code) == (
        "Dorpsstraat",
        "1",
        "b",
        "2400",
    )
    assert data.payment_method == "transfer"


def test_the_first_row_is_the_main_member_whatever_relation_it_sends():
    data, errors = _read(_pairs(**{"h.n0.relation_type": "KIND"}))
    assert errors == []
    assert data.members[0].relation_type.value == "HOOFDLID"


def test_the_marked_address_is_the_main_one_and_the_others_are_extra():
    """The mark decides, not the order of the rows: the second row is marked."""
    third = "an.derde@example.com"
    data, errors = _read(
        _pairs(**{"e_primary.n0": "x1", "e.x1.value": WORK, "e.x2.value": third})
        + [("e_order.n0", "x1"), ("e_order.n0", "x2")]
    )
    assert errors == []
    head = data.members[0]
    assert head.email == WORK
    assert head.extra_emails == [MAIN, third], "the others keep the order of the form"


def test_an_empty_e_mail_row_is_no_address():
    data, errors = _read(_pairs(**{"e.x1.value": "  "}) + [("e_order.n0", "x1")])
    assert errors == []
    assert (data.members[0].email, data.members[0].extra_emails) == (MAIN, [])


def test_an_untouched_extra_person_row_is_dropped():
    """A row the visitor added and left alone is not a person — and not a
    refusal. Its preselected relation and its empty e-mail row do not count as
    touching it."""
    data, errors = _read(
        _pairs()
        + [
            ("h_order", "n1"),
            ("h.n1.first_name", ""),
            ("h.n1.last_name", " "),
            ("h.n1.date_of_birth", ""),
            ("h.n1.relation_type", "KIND"),
            ("e_order.n1", "n1e"),
            ("e.n1e.value", ""),
        ]
        + _person("n2", "Cas")
    )
    assert errors == []
    assert [m.first_name for m in data.members] == ["An", "Cas"]
    assert data.members[1].relation_type.value == "PARTNER", (
        "the dropped row does not count as the partner either"
    )


def test_a_person_without_a_relation_gets_partner_then_child():
    data, errors = _read(
        _pairs() + _person("n1", "Bert") + _person("n2", "Cas") + _person("n3", "Dora")
    )
    assert errors == []
    assert [m.relation_type.value for m in data.members] == [
        "HOOFDLID",
        "PARTNER",
        "KIND",
        "KIND",
    ]


def test_a_chosen_relation_counts_for_the_default_of_the_next_row():
    """A child chosen by hand, then a row without a relation: there is no
    partner yet, so that one is the partner."""
    data, errors = _read(
        _pairs() + _person("n1", "Cas", relation_type="KIND") + _person("n2", "Bert")
    )
    assert errors == []
    assert [m.relation_type.value for m in data.members] == ["HOOFDLID", "KIND", "PARTNER"]


# ── Each refusal at its place ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "changes, place, message",
    [
        ({"h.n0.first_name": " "}, "h.n0.first_name", "Voornaam en achternaam zijn verplicht."),
        ({"h.n0.last_name": ""}, "h.n0.last_name", "Voornaam en achternaam zijn verplicht."),
        ({"h.n0.date_of_birth": "31/02/1980"}, "h.n0.date_of_birth", "Ongeldige geboortedatum."),
        ({"e.n0e.value": "geen adres"}, "e.n0e.value", "Vul een geldig e-mailadres in."),
        (
            {"e.n0e.value": ""},
            "e.n0e.value",
            "E-mailadres is verplicht voor het hoofdgezinslid.",
        ),
        (
            {"h.n0.mobile": ""},
            "h.n0.mobile",
            "Mobiel nummer is verplicht voor het hoofdgezinslid.",
        ),
        (
            {"address.postal_code": ""},
            "address.postal_code",
            "Selecteer een geldige postcode uit de lijst.",
        ),
        ({"address.street": " "}, "address.street", "Vul de straat in."),
        ({"address.house_number": ""}, "address.house_number", "Vul het huisnummer in."),
        ({"payment_method": None}, "payment_method", "Kies een betaalwijze."),
        ({"payment_method": "cash"}, "payment_method", "Kies een betaalwijze."),
    ],
)
def test_one_thing_missing_is_refused_at_its_field(changes, place, message):
    """The complete form with one thing changed: exactly one refusal, at the
    field the page marks, in these words."""
    assert _refusals(_pairs(**changes)) == [(place, message)]


@pytest.mark.parametrize(
    "changes, place",
    [
        ({"h.n0.date_of_birth": ""}, "h.n0.date_of_birth"),
        ({"h.n0.gender_code": None}, "h.n0.gender_code"),
        ({"h.n0.gender_code": "  "}, "h.n0.gender_code"),
    ],
)
def test_birth_date_and_gender_are_required_at_their_field(changes, place):
    """The rule itself is `MemberPerson.require_details` (#681), and its words
    are its own: only the place is this module's."""
    found = _refusals(_pairs(**changes))
    assert [field for field, _message in found] == [place]
    assert found[0][1].strip(), "a refusal without words"


def test_an_extra_person_is_held_to_the_same_details_at_its_own_row():
    found = _refusals(_pairs() + _person("n1", "Cas", date_of_birth=""))
    assert [field for field, _message in found] == ["h.n1.date_of_birth"]


def test_an_extra_person_needs_neither_e_mail_nor_mobile():
    """The other half of the main member's two refusals: without it, a reader
    that asked them of everyone would pass the tests above."""
    data, errors = _read(_pairs() + _person("n1", "Cas"))
    assert errors == []
    assert (data.members[1].email, data.members[1].mobile) == (None, None)


def test_an_invalid_address_of_an_extra_person_is_refused_at_its_row():
    found = _refusals(
        _pairs() + _person("n1", "Bert") + [("e_order.n1", "x7"), ("e.x7.value", "bert@")]
    )
    assert found == [("e.x7.value", "Vul een geldig e-mailadres in.")]


def test_the_main_member_without_an_e_mail_row_is_refused_at_the_person():
    """No row to point at: the refusal stands at the person's row."""
    pairs = [p for p in _pairs(**{"e.n0e.value": None}) if p[0] != "e_order.n0"]
    assert _refusals(pairs) == [("h.n0", "E-mailadres is verplicht voor het hoofdgezinslid.")]


def test_an_invalid_main_address_is_one_refusal_not_two():
    """An address that is no address is not also "missing"."""
    found = _refusals(_pairs(**{"e.n0e.value": "an@"}))
    assert [field for field, _message in found] == ["e.n0e.value"]


def test_an_unknown_relation_is_refused_at_its_field():
    found = _refusals(_pairs() + _person("n1", "Bert", relation_type="BUUR"))
    assert found == [("h.n1.relation_type", "Kies een relatie uit de lijst.")]


def test_a_form_without_an_address_is_refused_at_the_three_address_fields():
    pairs = [p for p in _pairs() if not p[0].startswith("address.")]
    assert [field for field, _message in _refusals(pairs)] == [
        "address.postal_code",
        "address.street",
        "address.house_number",
    ]


def test_several_refusals_come_back_together_each_at_its_place():
    """Everything at once: the visitor corrects the form in one go. In the order
    of the page — the persons, the address, the payment."""
    found = _refusals(
        _pairs(
            **{
                "h.n0.first_name": "",
                "h.n0.mobile": "",
                "e.n0e.value": "an@",
                "address.street": "",
                "address.postal_code": "",
                "payment_method": None,
            }
        )
        + _person("n1", "Cas", gender_code="")
    )
    assert [field for field, _message in found] == [
        "h.n0.first_name",
        "e.n0e.value",
        "h.n0.mobile",
        "h.n1.gender_code",
        "address.postal_code",
        "address.street",
        "payment_method",
    ]
