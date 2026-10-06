"""#663 — de twee publieke schermen uit de sweep renderen nog (en juist).

`inschrijven.html` (the modal `_inschrijf_form.html` until CR-14 phase 1) en
`lid_worden.html` vallen buiten de render-gate van
#622, die de beheerkant dekt. Ze zijn wel de twee schermen waar een bezoeker
komt, dus een maatwijziging is daar meteen zichtbaar — en een Jinja-fout in een
omgezette macro-aanroep zou er stil renderen als een leeg veld.

Deze test kijkt niet naar klassen (dat breekt bij elke herstyling) maar naar wat
een formulier bruikbaar maakt: de velden bestaan, dragen hun naam, en de
verplichte zijn verplicht.
"""

import pytest

from tests.conftest import form_fields, seed_activity_with_product, seed_postal_code

pytestmark = pytest.mark.ui_serverrendered


def test_word_lid_heeft_zijn_velden_nog(client, db_session):
    seed_postal_code(db_session, code="2400", municipality="Mol")
    html = client.get("/lid-worden").text

    # #1590: the names are the contract of `membership.signup_form`.
    for naam in (
        "h.n0.first_name",
        "h.n0.last_name",
        "h.n0.date_of_birth",
        "h.n0.gender_code",
        "h.n0.mobile",
        "e.n0e.value",
        "address.street",
        "address.house_number",
        "address.bus_number",
        "address.postal_code",
        "payment_method",
    ):
        assert f'name="{naam}"' in html, f"veld {naam} is verdwenen"
    # De postcode blijft een dropdown (vaste UI-beslissing), met echte opties.
    at = html.index('name="address.postal_code"')
    assert html.rindex("<", 0, at) == html.rindex("<select", 0, at), "the postal code is no select"
    assert '<option value="2400"' in html[at : html.index("</select>", at)]
    # Verplichte velden zijn nog verplicht.
    for naam in ("address.street", "address.house_number", "h.n0.first_name", "e.n0e.value"):
        blok = html[html.index(f'name="{naam}"') :]
        assert " required" in blok[: blok.index(">")], f"{naam} is zijn required kwijt"


def test_the_word_lid_page_sends_what_the_reader_reads(client, db_session):
    """The page and `signup_from_form` agree on every name: the form as the
    browser would send it, with the visitor's values typed into the fields the
    PAGE names, creates the household. A field the template renames is then
    missing from this post, and the sign-up is refused."""
    from app.domains.auth.api import SESSION_COOKIE, make_session_value

    seed_postal_code(db_session, code="2400", municipality="Mol")
    fields = form_fields(client.get("/lid-worden").text, "lid-worden-form")
    assert fields["h_order"] == ["n0"] and fields["e_order.n0"] == ["n0e"]
    assert fields["payment_method"] == "online", "online is the default (fixed decision)"
    typed = {
        "h.n0.first_name": "Veldnaam",
        "h.n0.last_name": "Proef",
        "h.n0.date_of_birth": "1980-01-01",
        "h.n0.mobile": "0470000000",
        "e.n0e.value": "veldnaam.proef@example.com",
        "address.street": "Dorpsstraat",
        "address.house_number": "1",
        "address.postal_code": "2400",
        "payment_method": "transfer",
    }
    assert set(typed) <= set(fields), f"the page has no field {sorted(set(typed) - set(fields))}"
    # #1632: the gender is a select; on an empty page it stands on "— kies —"
    # and the browser sends it empty.
    assert fields["h.n0.gender_code"] == ""

    resp = client.post("/lid-worden", data={**fields, **typed, "h.n0.gender_code": "F"})
    assert resp.status_code == 200, resp.text[:400]
    # Read back the way the new member would: signed in, on Mijn gezin.
    client.cookies.set(SESSION_COOKIE, make_session_value("veldnaam.proef@example.com"))
    portal = client.get("/leden/gezin")
    assert portal.status_code == 200, "the address the form sent does not sign in"
    for value in (
        # #1632: the main member stands in the section "Hoofdlid", no row title.
        ">Hoofdlid</h2>",
        "Veldnaam",
        "Proef",
        "01-01-1980",
        "Vrouw",
        # typed as 0470000000; the portal reads a number in groups (#1675)
        "0470 00 00 00",
        "mailto:veldnaam.proef@example.com",
        "Dorpsstraat",
        "2400",
    ):
        assert value in portal.text, f"{value} did not reach the household"


def test_inschrijven_heeft_zijn_velden_nog(client, db_session):
    activity, component, product = seed_activity_with_product(db_session)
    html = client.get(f"/activiteiten/{activity.id}/inschrijven/{component.id}").text
    assert html.strip(), "het inschrijfformulier rendert leeg"

    for naam in ("contact_name", "contact_email", "phone", "remarks"):
        assert f'name="{naam}"' in html, f"veld {naam} is verdwenen"
    # Het aantalveld per product draagt zijn htmx-koppeling naar de totaalregel:
    # die attributen gingen bij de omzetting door `attrs` en zijn makkelijk kwijt.
    assert f'name="product_{product.id}"' in html
    blok = html[html.index(f'name="product_{product.id}"') :]
    for stuk in ("hx-post=", "/totaal", "hx-include=", "hx-trigger="):
        assert stuk in blok[:900], f"het aantalveld mist {stuk} — geen live totaal meer"
