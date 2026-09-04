"""Vier bevindingen uit de design-conformiteitssweep van 4 sep 2026.

Elk van deze schermen zag er goed uit tot je erop klikte, of gebruikte een tweede
kopie van iets dat de kit al doet. De gate-regels in `test_ui_conventions_gate.py`
houden de klasse tegen; deze tests leggen het concrete gedrag vast.
"""
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_serverrendered

APP = Path(__file__).resolve().parents[1] / "app"


# ── #639: adres bewerken houdt zijn knop ─────────────────────────────────────

def test_adres_bewerken_houdt_zijn_knop_tijdens_het_bewerken():
    """De knop zat binnen `x-show="!edit"` en verdween zodra je begon te bewerken.

    §2.8: verbergen geeft layout-shift én je hebt geen weg terug. De invariant die
    telt is dat de adressectie beide standen kent — "Bewerken" en "Annuleren" —
    zoals de personenlijst in hetzelfde bestand al deed.
    """
    tekst = (APP / "domains" / "mdm" / "templates" / "_leden_detail.html").read_text()
    adresblok = tekst.split('/adres"')[0].rsplit("{# Adres", 1)[-1]

    assert "ui.edit_toggle" in adresblok, "de adressectie gebruikt de kit-toggle niet"
    assert 'x-show="!edit"' not in adresblok.split("ui.edit_toggle")[0].rsplit("<div", 1)[-1], (
        "de knop staat weer in een blok dat door de bewerkmodus verborgen wordt")


def test_de_adresknop_toont_beide_standen(client, db_session):
    """Gerenderd, niet alleen in de template: het scherm moet allebei bevatten."""
    from tests.conftest import create_test_family, seed_postal_code
    from app.domains.auth.api import SESSION_COOKIE, make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    seed_postal_code(db_session)
    member, _person = create_test_family(db_session, email="adres@example.com")
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    html = client.get(f"/admin/leden/gezin/{member.id}").text

    assert "Bewerken" in html and "Annuleren" in html


# ── #640: e-maillogpreview via de kit-modal ──────────────────────────────────

def test_email_log_gebruikt_de_kit_modal():
    """Een tweede kopie van de overlay-markup loopt stil uit de pas met het
    gedeelde gedrag (klik-buiten, Escape, aria-label op de sluitknop)."""
    tekst = (APP / "domains" / "mail" / "templates" / "_email_log_lijst.html").read_text()

    assert "ui.modal(" in tekst
    assert "fixed inset-0" not in tekst, "nog een eigen overlay naast ui.modal()"


def test_de_preview_behoudt_de_opmaak_van_523(client, db_session):
    """#523 legde de koptekst vast: onderwerp groot, meta klein. De omzetting mag
    daar niets aan veranderen — zichtbaar verschil = mislukte omzetting."""
    from app.domains.auth.api import SESSION_COOKIE, make_session_value
    from app.domains.mail.models import EmailLog
    from tests.conftest import SEEDED_ADMIN_EMAIL

    db_session.add(EmailLog(recipient="ann@example.com", subject="Bevestiging",
                            status="sent", body="<p>Dag Ann</p>"))
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    html = client.get("/admin/e-maillog").text

    assert "Bevestiging" in html
    assert "text-lg font-semibold" in html            # onderwerp (via ui.modal)
    assert "text-sm text-gray-500 leading-relaxed" in html   # meta-regel
    assert "ann@example.com" in html
    assert 'srcdoc="&lt;p&gt;Dag Ann&lt;/p&gt;"' in html or "srcdoc=" in html


# ── #641: submit-microcopy en het veldtype in gewone taal ────────────────────

def test_de_form_builder_zegt_gewoon_opslaan(client, db_session):
    from app.domains.auth.api import SESSION_COOKIE, make_session_value
    from app.domains.forms.models import Form
    from tests.conftest import SEEDED_ADMIN_EMAIL

    formulier = Form(title="Microcopy", share_token="tok-microcopy", status="draft")
    db_session.add(formulier)
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    html = client.get(f"/admin/formulieren/{formulier.id}").text

    for oud in ("Veld opslaan", "Instellingen opslaan", "Sectie opslaan"):
        assert oud not in html, f"{oud!r} staat er nog"
    assert ">Opslaan<" in html


def test_het_veldtype_staat_in_gewone_taal(client, db_session):
    """§2.12: nooit een rauwe DB-waarde op het scherm.

    Bewuste afweging (#641 punt 3): dit is form-builder-jargon, maar de codes zijn
    Engels (`textarea`, `radio`) en de builder wordt bediend door een bestuurslid,
    niet door een ontwikkelaar. De keuzelijst waarmee je een veld toevoegt toonde
    dezelfde codes, dus het scherm spreekt nu overal dezelfde taal.
    """
    from app.domains.auth.api import SESSION_COOKIE, make_session_value
    from app.domains.forms.models import Form, FormField
    from tests.conftest import SEEDED_ADMIN_EMAIL

    formulier = Form(title="Veldtypes", share_token="tok-veldtypes", status="draft")
    db_session.add(formulier)
    db_session.flush()
    db_session.add(FormField(form_id=formulier.id, label="Toelichting",
                             field_type="textarea", position=1))
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    html = client.get(f"/admin/formulieren/{formulier.id}").text

    assert "Lange tekst" in html
    assert ">textarea<" not in html            # niet als badge- of optietekst
    assert 'value="textarea"' in html          # de code blijft wél de waarde


def test_lidmaatschapsjaar_toevoegen_heet_toevoegen(client, db_session):
    from tests.conftest import create_test_family, seed_postal_code
    from app.domains.auth.api import SESSION_COOKIE, make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    seed_postal_code(db_session)
    member, _person = create_test_family(db_session, email="jaar@example.com")
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    html = client.get(f"/admin/leden/gezin/{member.id}").text

    assert "Lid maken" not in html
    assert ">Toevoegen<" in html
