"""Gezinsscherm: een deelactie raakt alleen haar eigen kaart, en een nieuw gezin
kan een adres krijgen (#1111).

Gemeten op 20 september 2026 naar aanleiding van Koens melding. Twee losse
problemen op één scherm:

1. **Elke deelactie wiste je getypte tekst.** Persoon bewerken, adres opslaan,
   persoon toevoegen, bestuurslid kiezen, lidmaatschap toevoegen: alle vijf
   postten naar `#leden-detail` met `innerHTML`, en de server antwoordde met het
   hele blok, opnieuw uit de databank. Typ een adres, klik "Persoon toevoegen",
   en de adresvelden halen hun waarde weer uit de databank — waar niets staat.
   Het Alpine-`edit` reset mee, dus het vlak klapt ook dicht.
2. **Een via de backoffice aangemaakt gezin kon geen adres krijgen.**
   `update_person_address` gaf 404 zodra er nog geen adresrij was, en
   `create_member` maakt er nooit een. De beheerder zag de algemene
   "er ging iets mis"-banner. Geen test dekte dat pad.

Wat hier bewezen wordt, in de volgorde van het issue:

1. adres op een gezin zonder adresrij: opslaan, en het staat in de databank;
2. getypte tekst overleeft een andere deelactie — de serverkant ervan: het
   antwoord op "persoon toevoegen" bevat de adreskaart niet, dus htmx kan ze niet
   vervangen (de browserkant staat in `tests_e2e/test_gezinsscherm_tekst_overleeft.py`);
3. elke deelactie richt zich op haar eigen kaart — het doel van elke vorm, niet
   alleen een 200;
4. een naamswijziging verandert mee in de kop en in de bestuurslidlijst (oob);
5. de postcodelijst toont geen waarde wanneer het gezin er geen heeft.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden (gemeten):
"persoon toevoegen" weer het hele blok laten antwoorden (`_detail_response`) → 2
valt om, want de adreskaart zit weer in het antwoord; de aanmaak van een adres in
`update_person_address` weggehaald → 1 valt om met de 404 van vroeger.
"""
from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.mdm.api import Address, Person, PostalCode
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client) -> str:
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return csrf_token_for(waarde)


def _postcode(db) -> PostalCode:
    pc = db.query(PostalCode).filter(PostalCode.postal_code == "2400").first()
    if pc is None:
        pc = PostalCode(postal_code="2400", municipality="Mol")
        db.add(pc)
        db.flush()
    return pc


def _gezin_zonder_adres(db) -> int:
    """Een gezin met een hoofdlid en **geen adresrij**.

    Rechtstreeks opgebouwd en niet via het aanmaakscherm: sinds #1110 vraagt dat
    scherm het adres meteen mee. Zo'n gezin bestaat nog volop — de ledenimport en
    oudere records leveren er op — en het is precies de toestand waarin het adres
    voor het eerst bewaard moet kunnen worden.
    """
    from tests.conftest import create_test_family

    member, _persoon = create_test_family(db, email="gezin1111@example.com")
    db.flush()
    return member.id


def _hoofdlid_id(db, family_id: int) -> int:
    from app.domains.membership.api import get_family

    return next(m.id for m in get_family(db, family_id).members
                if m.relation_type == "HOOFDLID")


# ── 1. Adres op een nieuw gezin ──────────────────────────────────────────────

def test_een_nieuw_gezin_krijgt_een_adres(client, db_session):
    _postcode(db_session)
    csrf = _login(client)
    gezin = _gezin_zonder_adres(db_session)
    hoofdlid = _hoofdlid_id(db_session, gezin)
    assert db_session.query(Address).filter(Address.person_id == hoofdlid).first() is None, (
        "voorwaarde: het aangemaakte gezin heeft nog geen adresrij")

    antwoord = client.post(f"/admin/leden/gezin/{gezin}/adres",
                           data={"street": "Nieuwstraat", "house_number": "7",
                                 "bus_number": "", "postal_code": "2400"},
                           headers={"X-CSRF-Token": csrf})
    assert antwoord.status_code == 200, antwoord.text[:300]

    db_session.expire_all()
    adres = db_session.query(Address).filter(Address.person_id == hoofdlid).one()
    assert (adres.street, adres.house_number) == ("Nieuwstraat", "7")
    assert adres.postal_code.postal_code == "2400"
    # De adreskaart in het antwoord toont het, en de kop reist oob mee.
    assert 'id="adres-kaart"' in antwoord.text and "Nieuwstraat 7" in antwoord.text
    assert 'id="gezin-recordkop" hx-swap-oob="true"' in antwoord.text


def test_een_adres_zonder_straat_op_een_nieuw_gezin_wordt_geweigerd(client, db_session):
    """Aanmaken is geen reden om minder te eisen dan bewerken."""
    _postcode(db_session)
    csrf = _login(client)
    gezin = _gezin_zonder_adres(db_session)
    antwoord = client.post(f"/admin/leden/gezin/{gezin}/adres",
                           data={"street": "", "house_number": "7", "postal_code": "2400"},
                           headers={"X-CSRF-Token": csrf})
    assert antwoord.status_code == 422
    assert db_session.query(Address).filter(
        Address.person_id == _hoofdlid_id(db_session, gezin)).first() is None


# ── 2 en 3. Een deelactie raakt alleen haar eigen kaart ──────────────────────

def _forms_met_doel(html: str) -> list[tuple[str, str, str]]:
    """(hx-post, hx-target, hx-swap) van elke vorm en knop binnen het detail."""
    gevonden = []
    for tag in re.findall(r"<(?:form|button)\b[^>]*hx-post=[^>]*>", html):
        attrs = dict(re.findall(r'(hx-[a-z-]+)="([^"]*)"', tag))
        gevonden.append((attrs.get("hx-post", ""), attrs.get("hx-target", ""),
                         attrs.get("hx-swap", "")))
    return gevonden


def test_elke_deelactie_richt_zich_op_haar_eigen_kaart(client, db_session):
    _postcode(db_session)
    csrf = _login(client)
    gezin = _gezin_zonder_adres(db_session)
    client.post(f"/admin/leden/gezin/{gezin}/lidmaatschappen", data={"year": "2030"},
                headers={"X-CSRF-Token": csrf})
    hoofdlid = _hoofdlid_id(db_session, gezin)

    html = client.get(f"/admin/leden/gezin/{gezin}").text
    doelen = _forms_met_doel(html)
    assert len(doelen) >= 6, doelen

    verwacht = {
        f"/persoon/{hoofdlid}": f"#persoon-{hoofdlid}",
        "/adres": "#adres-kaart",
        "/personen": "#persoon-toevoegen",
        "/bestuurslid": "#bestuurslid-kaart",
        "/lidmaatschappen": "#lidmaatschappen-kaart",
        "/lidmaatschappen/": "#lidmaatschappen-kaart",   # verwijderknop
    }
    for post, target, swap in doelen:
        if re.fullmatch(r"/admin/leden/gezin/\d+/verwijderen", post):
            continue   # het gezin zelf verwijderen (kop) — geen kaartactie
        assert target != "#leden-detail", f"{post} vervangt nog het hele blok"
        assert swap == "outerHTML", f"{post}: {swap!r}"
        past = [doel for staart, doel in verwacht.items() if staart in post]
        assert past and target == past[-1], f"{post} → {target}"


def test_persoon_toevoegen_raakt_de_adreskaart_niet(client, db_session):
    """De serverkant van "getypte tekst overleeft": wat niet in het antwoord zit,
    kan htmx niet vervangen."""
    _postcode(db_session)
    csrf = _login(client)
    gezin = _gezin_zonder_adres(db_session)

    antwoord = client.post(f"/admin/leden/gezin/{gezin}/personen",
                           data={"first_name": "Partner", "last_name": "Erbij",
                                 "date_of_birth": "1985-05-05", "gender_code": "F",
                                 "relation_type": "PARTNER"},
                           headers={"X-CSRF-Token": csrf})
    assert antwoord.status_code == 200, antwoord.text[:300]
    assert "Partner Erbij" in antwoord.text
    assert 'id="persoon-toevoegen"' in antwoord.text, "de toevoegkaart komt vers terug"
    assert 'id="adres-kaart"' not in antwoord.text and 'id="adres-form"' not in antwoord.text, (
        "het antwoord bevat de adreskaart: htmx vervangt ze en de getypte tekst is weg")
    assert 'id="leden-detail"' not in antwoord.text
    # De bestuurslidlijst noemt elke persoon en reist daarom oob mee.
    assert 'id="bestuurslid-kaart"' in antwoord.text and 'hx-swap-oob="true"' in antwoord.text
    assert "Erbij Partner" in antwoord.text


def test_persoon_verwijderen_laat_de_kaart_verdwijnen(client, db_session):
    _postcode(db_session)
    csrf = _login(client)
    gezin = _gezin_zonder_adres(db_session)
    client.post(f"/admin/leden/gezin/{gezin}/personen",
                data={"first_name": "Weg", "last_name": "Ermee", "date_of_birth": "1985-05-05",
                      "gender_code": "F", "relation_type": "PARTNER"},
                headers={"X-CSRF-Token": csrf})
    partner = db_session.query(Person).filter(Person.first_name == "Weg").one()

    antwoord = client.post(f"/admin/leden/gezin/{gezin}/persoon/{partner.id}/verwijderen",
                           headers={"X-CSRF-Token": csrf})
    assert antwoord.status_code == 200
    assert f'id="persoon-{partner.id}"' not in antwoord.text, "de kaart hoort te verdwijnen"
    assert 'id="bestuurslid-kaart"' in antwoord.text and "Ermee Weg" not in antwoord.text


# ── 4. Een naam die elders staat, verandert daar mee ─────────────────────────

def test_een_naamswijziging_reist_oob_naar_kop_en_bestuurslidlijst(client, db_session):
    _postcode(db_session)
    csrf = _login(client)
    gezin = _gezin_zonder_adres(db_session)
    hoofdlid = _hoofdlid_id(db_session, gezin)

    antwoord = client.post(f"/admin/leden/gezin/{gezin}/persoon/{hoofdlid}",
                           data={"first_name": "Rita", "last_name": "Nieuwnaam",
                                 "date_of_birth": "1980-01-01", "gender_code": "M",
                                 "relation_type": "HOOFDLID"},
                           headers={"X-CSRF-Token": csrf})
    assert antwoord.status_code == 200
    assert f'id="persoon-{hoofdlid}"' in antwoord.text
    kop = antwoord.text.index('id="gezin-recordkop" hx-swap-oob="true"')
    assert "Nieuwnaam" in antwoord.text[kop:]
    lijst = antwoord.text.index('id="bestuurslid-kaart"')
    assert 'hx-swap-oob="true"' in antwoord.text[lijst:lijst + 200]
    assert "Nieuwnaam Rita" in antwoord.text[lijst:]


# ── 5. De postcodelijst liegt niet ───────────────────────────────────────────

def _postcode_opties(html: str) -> list[tuple[str, bool]]:
    select = re.search(r'<select[^>]*name="postal_code"[\s\S]*?</select>', html).group(0)
    return [(waarde, "selected" in tag) for tag, waarde in
            re.findall(r'(<option value="([^"]*)"[^>]*>)', select)]


def test_de_postcodelijst_toont_geen_waarde_zonder_adres(client, db_session):
    _postcode(db_session)
    csrf = _login(client)
    gezin = _gezin_zonder_adres(db_session)

    opties = _postcode_opties(client.get(f"/admin/leden/gezin/{gezin}").text)
    assert opties[0] == ("", True), opties[:3]
    assert not any(gekozen for waarde, gekozen in opties if waarde), (
        "een postcode staat als gekozen terwijl het gezin er geen heeft")

    client.post(f"/admin/leden/gezin/{gezin}/adres",
                data={"street": "Nieuwstraat", "house_number": "7", "postal_code": "2400"},
                headers={"X-CSRF-Token": csrf})
    opties = _postcode_opties(client.get(f"/admin/leden/gezin/{gezin}").text)
    assert ("2400", True) in opties and ("", False) in opties
