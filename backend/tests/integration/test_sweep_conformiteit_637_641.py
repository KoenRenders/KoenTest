"""Vier bevindingen uit de design-conformiteitssweep van 4 sep 2026.

Elk van deze schermen zag er goed uit tot je erop klikte, of gebruikte een tweede
kopie van iets dat de kit al doet. De gate-regels in `test_ui_conventions_gate.py`
houden de klasse tegen; deze tests leggen het concrete gedrag vast.
"""

import re
from pathlib import Path

import pytest

from tests._sites import at_tenant

pytestmark = pytest.mark.ui_serverrendered

APP = Path(__file__).resolve().parents[2] / "app"


# ── #639: adres bewerken houdt zijn knop ─────────────────────────────────────


def test_de_adresknop_toont_beide_standen(client, db_session):
    """Gerenderd, niet alleen in de template: het scherm moet allebei bevatten."""
    from app.domains.auth.api import SESSION_COOKIE, make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL, create_test_family, seed_postal_code

    seed_postal_code(db_session)
    member, _person = create_test_family(db_session, email="adres@example.com")
    at_tenant(db_session, member)  # CR-26 F9
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    html = client.get(f"/admin/leden/gezin/{member.id}").text

    assert "Bewerken" in html and "Annuleren" in html


# ── #640: e-maillogpreview, sinds #1925 op de eigen pagina van een mail ──────


def test_email_log_heeft_geen_eigen_overlay():
    """#640 took the preview's own overlay away for `ui.modal()`; #1925 gave a mail
    a page of its own (`record_header`), so neither the list nor the page holds an
    overlay of its own."""
    templates = APP / "domains" / "mail" / "templates"
    for name in ("_email_log_lijst.html", "email_log.html", "email_record.html"):
        assert "fixed inset-0" not in (templates / name).read_text(), name
    assert "ui.record_header(" in (templates / "email_record.html").read_text()


def test_de_preview_behoudt_de_opmaak_van_523(client, db_session):
    """#523 legde de koptekst vast: onderwerp groot, meta klein. De omzetting mag
    daar niets aan veranderen — zichtbaar verschil = mislukte omzetting."""
    from app.domains.auth.api import SESSION_COOKIE, make_session_value
    from app.domains.mail.models import EmailLog
    from tests.conftest import SEEDED_ADMIN_EMAIL

    db_session.add(
        EmailLog(
            recipient="ann@example.com", subject="Bevestiging", status="sent", body="<p>Dag Ann</p>"
        )
    )
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    log = db_session.query(EmailLog).filter(EmailLog.recipient == "ann@example.com").one()
    html = client.get(f"/admin/e-maillog/{log.id}").text

    # #1925: the subject is the page's title, the recipient a fact under it.
    assert re.search(r"<h1[^>]*>\s*Bevestiging\s*</h1>", html), "the subject is the title"
    assert "Aan: ann@example.com" in html
    assert 'srcdoc="&lt;p&gt;Dag Ann&lt;/p&gt;"' in html


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
    db_session.add(
        FormField(form_id=formulier.id, label="Toelichting", field_type="textarea", position=1)
    )
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))

    html = client.get(f"/admin/formulieren/{formulier.id}").text

    assert "Lange tekst" in html
    assert ">textarea<" not in html  # niet als badge- of optietekst
    assert 'value="textarea"' in html  # de code blijft wél de waarde
