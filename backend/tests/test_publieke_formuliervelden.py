"""#663 — de twee publieke schermen uit de sweep renderen nog (en juist).

`_inschrijf_form.html` en `lid_worden.html` vallen buiten de render-gate van
#622, die de beheerkant dekt. Ze zijn wel de twee schermen waar een bezoeker
komt, dus een maatwijziging is daar meteen zichtbaar — en een Jinja-fout in een
omgezette macro-aanroep zou er stil renderen als een leeg veld.

Deze test kijkt niet naar klassen (dat breekt bij elke herstyling) maar naar wat
een formulier bruikbaar maakt: de velden bestaan, dragen hun naam, en de
verplichte zijn verplicht.
"""
import pytest

from tests.conftest import seed_activity_with_product, seed_postal_code

pytestmark = pytest.mark.ui_serverrendered


def test_word_lid_heeft_zijn_velden_nog(client, db_session):
    seed_postal_code(db_session, code="2400", municipality="Mol")
    html = client.get("/lid-worden").text

    for naam in ("m0_first_name", "m0_last_name", "m0_email", "m0_mobile",
                 "street", "house_number", "bus_number", "postal_code"):
        assert f'name="{naam}"' in html, f"veld {naam} is verdwenen"
    # De postcode blijft een dropdown (vaste UI-beslissing), met echte opties.
    assert "<select" in html and "2400" in html
    # Verplichte velden zijn nog verplicht — dat attribuut zat vóór de omzetting
    # in de handgeschreven tag.
    for naam in ("street", "house_number"):
        blok = html[html.index(f'name="{naam}"'):]
        assert " required" in blok[:400], f"{naam} is zijn required kwijt"


def test_inschrijven_heeft_zijn_velden_nog(client, db_session):
    activity, component, product = seed_activity_with_product(db_session)
    html = client.get(f"/activiteiten/{activity.id}/inschrijven/{component.id}").text
    assert html.strip(), "het inschrijfformulier rendert leeg"

    for naam in ("contact_name", "contact_email", "phone", "remarks"):
        assert f'name="{naam}"' in html, f"veld {naam} is verdwenen"
    # Het aantalveld per product draagt zijn htmx-koppeling naar de totaalregel:
    # die attributen gingen bij de omzetting door `attrs` en zijn makkelijk kwijt.
    assert f'name="product_{product.id}"' in html
    blok = html[html.index(f'name="product_{product.id}"'):]
    for stuk in ("hx-post=", "/totaal", "hx-include=", "hx-trigger="):
        assert stuk in blok[:900], f"het aantalveld mist {stuk} — geen live totaal meer"
