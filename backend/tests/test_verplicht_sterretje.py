"""#646 — de rode `*` markeert precies de verplichte velden, en niets anders.

Op `/lid-worden` (het scherm dat Koen "Word lid" noemt) stonden twee kleuren
sterretje naast elkaar: Voornaam/Achternaam rood, E-mail/GSM grijs. Oorzaak was
niet de `label()`-macro maar vier aanroepen in `person_fields` die het sterretje
in de *labeltekst* plakten, waar het `text-gray-700` van het label erfde.

Deze test vergelijkt daarom niet met een verwachte string, maar toetst de
invariant zelf: **de verzameling velden met een rood sterretje is exact de
verzameling verplichte velden.** Zo vangt hij beide richtingen — een verplicht
veld zonder rode markering (de bug van #646) én een rode markering bij een veld
dat niet verplicht is, wat de gebruiker even hard misleidt.

De koppeling loopt via `label for=` ↔ `control id=`, niet via een telling: twee
even grote verzamelingen kunnen nog altijd de verkeerde velden bevatten.
"""
import re

from tests.conftest import seed_postal_code

# Het sterretje zoals de B2-conventie het voorschrijft (docs/ui-conventies.md:383).
ROOD_STERRETJE = re.compile(r'class="text-red-600">\s*\*')
LABEL = re.compile(r'<label\s+for="([^"]+)"[^>]*>(.*?)</label>', re.S)
CONTROL = re.compile(r'<(input|select|textarea)\s([^>]*)>', re.S)
ID_ATTR = re.compile(r'\bid="([^"]+)"')


def _gemarkeerd(html: str) -> set[str]:
    """Veld-id's waarvan het label een rood sterretje draagt."""
    return {for_id for for_id, inhoud in LABEL.findall(html)
            if ROOD_STERRETJE.search(inhoud)}


def _verplicht(html: str) -> set[str]:
    """Veld-id's van formuliervelden met het HTML-attribuut `required`."""
    ids = set()
    for _tag, attrs in CONTROL.findall(html):
        treffer = ID_ATTR.search(attrs)
        if treffer and re.search(r'(?:^|\s)required(?:[\s=>]|$)', attrs):
            ids.add(treffer.group(1))
    return ids


NAME_ATTR = re.compile(r'\bname="([^"]+)"')


def _radiogroepen(html: str) -> set[str]:
    """Namen van radiogroepen.

    Een radiogroep draagt geen `required` en heeft geen enkelvoudige `id`: het
    label wijst naar de groep als geheel (`Betaalwijze`, met "online" voorgevinkt).
    Zo'n groep is per constructie altijd ingevuld, dus een rood sterretje erbij is
    correct en mag de vergelijking hieronder niet doen struikelen. De keerzijde:
    op radiogroepen toetst deze test de markering niet.
    """
    namen = set()
    for _tag, attrs in CONTROL.findall(html):
        treffer = NAME_ATTR.search(attrs)
        if treffer and re.search(r'type="radio"', attrs):
            namen.add(treffer.group(1))
    return namen


def _controleer(html: str, *, minstens: set[str]) -> None:
    gemarkeerd, verplicht = _gemarkeerd(html), _verplicht(html)
    assert minstens <= verplicht, (
        f"velden die verplicht horen te zijn, zijn het niet: {sorted(minstens - verplicht)}")
    assert verplicht - gemarkeerd == set(), (
        "verplicht veld zonder rood sterretje (#646): "
        f"{sorted(verplicht - gemarkeerd)}")
    assert gemarkeerd - verplicht - _radiogroepen(html) == set(), (
        "rood sterretje bij een veld dat niet verplicht is: "
        f"{sorted(gemarkeerd - verplicht - _radiogroepen(html))}")


def test_hoofdlid_elk_verplicht_veld_draagt_het_rode_sterretje(client, db_session):
    """Het gemelde scherm: hoofdlid + adres, in één render."""
    seed_postal_code(db_session, code="2400", municipality="Mol")
    resp = client.get("/lid-worden")
    assert resp.status_code == 200
    # E-mail en GSM zijn de twee velden uit de melding; voornaam/achternaam
    # deden het al goed en horen mee in dezelfde vergelijking.
    _controleer(resp.text,
                minstens={"m0_first_name", "m0_last_name", "m0_email", "m0_mobile"})


def test_bijkomend_lid_geboortedatum_en_geslacht_dragen_het_rode_sterretje(client, db_session):
    """De rij die htmx bijlaadt: daar zijn geboortedatum en geslacht verplicht
    (#551) en e-mail/GSM juist niet — de omgekeerde verdeling van het hoofdlid,
    wat meteen bewijst dat de markering de vlag volgt en niet het veld."""
    rij = client.get("/lid-worden/persoon-rij?index=1")
    assert rij.status_code == 200
    _controleer(rij.text, minstens={"m1_date_of_birth", "m1_gender_code"})
    assert "m1_email" not in _verplicht(rij.text)
    assert "m1_mobile" not in _gemarkeerd(rij.text)


def test_geen_grijs_sterretje_meer_in_de_labeltekst(client, db_session):
    """De concrete regressie: een `*` in de labeltekst erft `text-gray-700`.
    Elk sterretje in een label hoort in de rode span te zitten."""
    seed_postal_code(db_session, code="2400", municipality="Mol")
    for html in (client.get("/lid-worden").text,
                 client.get("/lid-worden/persoon-rij?index=1").text):
        for for_id, inhoud in LABEL.findall(html):
            zonder_rode_span = re.sub(r'<span class="text-red-600">.*?</span>', "",
                                      inhoud, flags=re.S)
            assert "*" not in zonder_rode_span, (
                f"sterretje buiten de rode span in het label van {for_id}")
