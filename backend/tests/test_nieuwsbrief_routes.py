"""The newsletter along its ROUTES, the way a board member and a visitor use it (#984).

`test_nieuwsbrief.py` checks the rules through the service. This file walks the
screens over HTTP, with CSRF: write a letter, insert an activity, send a test,
send it for real, read the archive; manage subscribers and the import; and the
public side — sign up, confirm, unsubscribe — without a login.
"""
from datetime import date, timedelta

import pytest

from app.domains.activities.api import Activity, ActivityDate
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.newsletter.models import (
    DELIVERY_SENT,
    LETTER_SENDING,
    LETTER_SENT,
    SUBSCRIBER_CONFIRMED,
    SUBSCRIBER_PENDING,
    SUBSCRIBER_UNSUBSCRIBED,
    Delivery,
    Newsletter,
    Subscriber,
)
from app.domains.newsletter import service as nb
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client) -> dict:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value), "HX-Request": "true"}


@pytest.fixture
def mailbox(monkeypatch):
    sent = []

    def fake(to_email, subject, body_html, *, email_type, reply_to=None,
             unsubscribe_url=None, body_text=None):
        sent.append({"to": to_email, "subject": subject, "body": body_html,
                     "reply_to": reply_to, "unsubscribe_url": unsubscribe_url,
                     "body_text": body_text})
        return "sent"

    monkeypatch.setattr("app.domains.mail.api.send_campaign_mail", fake)
    return sent


@pytest.fixture
def confirmations(monkeypatch):
    sent = []
    monkeypatch.setattr("app.domains.mail.api.send_newsletter_confirmation",
                        lambda to, name, url: sent.append((to, url)) or "sent")
    return sent


def _activity(db, name, day, location="Miloheem"):
    activity = Activity(name=name, location=location, slug=name.lower().replace(" ", "-"))
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=day))
    db.flush()
    return activity


def _subscriber(db, email, status=SUBSCRIBER_CONFIRMED):
    row = Subscriber(email=email, status=status, source="admin",
                     unsubscribe_token=f"tok-{email}")
    db.add(row)
    db.flush()
    return row


def _latest(db) -> Newsletter:
    return db.query(Newsletter).order_by(Newsletter.id.desc()).first()


# ── The board member's path ──────────────────────────────────────────────────

def test_de_hele_weg_van_een_nieuwsbrief(client, db_session, mailbox):
    """List → new draft → text and audience → insert → test mail → send → archive."""
    headers = _login(client)
    _subscriber(db_session, "piet@example.org")
    rum = _activity(db_session, "Rumproefavond", date.today() + timedelta(days=20))

    # 1. The list, and the menu item.
    lijst = client.get("/admin/nieuwsbrieven")
    assert lijst.status_code == 200
    assert 'href="/admin/nieuwsbrieven"' in lijst.text

    # 2. A new draft opens as its own page.
    nieuw = client.post("/admin/nieuwsbrieven", headers=headers)
    assert nieuw.status_code == 204
    letter = _latest(db_session)
    assert nieuw.headers["HX-Redirect"] == f"/admin/nieuwsbrieven/{letter.id}"
    scherm = client.get(f"/admin/nieuwsbrieven/{letter.id}")
    assert scherm.status_code == 200
    assert 'id="nb-trix"' in scherm.text
    assert 'name="audience"' in scherm.text and " checked" not in scherm.text.split('name="audience"')[1][:40]

    # 3. "Activiteit invoegen" delivers a REFERENCE (#984, 19 September 2026):
    # the block itself is built when the letter is sent, because Trix keeps no
    # table and no class. The calendar is still a line per activity.
    regel = client.get(f"/admin/nieuwsbrieven/{letter.id}/invoegen/activiteit/{rum.id}")
    assert regel.status_code == 200
    assert "Rumproefavond" in regel.text
    assert f"[[activiteit:{rum.id}|" in regel.text
    kalender = client.get(f"/admin/nieuwsbrieven/{letter.id}/invoegen/kalender")
    assert "Rumproefavond" in kalender.text
    kiezer = client.get(f"/admin/nieuwsbrieven/{letter.id}/activiteiten?q=rum")
    assert "Rumproefavond" in kiezer.text

    # 4. Autosave.
    bewaard = client.post(f"/admin/nieuwsbrieven/{letter.id}/bewaren", headers=headers,
                          data={"subject": "Het najaar", "audience": "non_members",
                                "body_html": f"<div>Beste,</div>{regel.text}"})
    assert bewaard.status_code == 200
    assert "Bewaard om" in bewaard.text
    db_session.refresh(letter)
    assert (letter.subject, letter.audience) == ("Het najaar", "non_members")

    # 5. The test mail goes to the signed-in admin only.
    test = client.post(f"/admin/nieuwsbrieven/{letter.id}/testmail", headers=headers)
    assert "Testmail verstuurd" in test.text
    assert [m["to"] for m in mailbox] == [SEEDED_ADMIN_EMAIL]

    # 6. The send screen repeats audience and count; sending starts the queue.
    stap = client.get(f"/admin/nieuwsbrieven/{letter.id}/versturen")
    assert "Niet-leden · 1 adressen" in stap.text
    verstuurd = client.post(f"/admin/nieuwsbrieven/{letter.id}/versturen",
                            headers=headers, data={"reply_to": "sender"})
    assert verstuurd.status_code == 204
    db_session.refresh(letter)
    assert letter.status == LETTER_SENDING
    assert letter.reply_to_address == SEEDED_ADMIN_EMAIL

    nb.send_batch(db_session, letter.id)
    db_session.refresh(letter)
    assert letter.status == LETTER_SENT
    assert [m["to"] for m in mailbox][-1] == "piet@example.org"

    # 7. The same address now opens the archive, not the editor.
    archief = client.get(f"/admin/nieuwsbrieven/{letter.id}")
    assert 'id="nb-trix"' not in archief.text
    assert "piet@example.org" in archief.text
    assert "Kopiëren naar een nieuw concept" in archief.text
    filter_ = client.get(f"/admin/nieuwsbrieven/{letter.id}?status=failed",
                         headers={"HX-Request": "true", "X-Raak-Filter": "1"})
    assert "piet@example.org" not in filter_.text

    # 8. A sent letter cannot be saved over.
    geweigerd = client.post(f"/admin/nieuwsbrieven/{letter.id}/bewaren", headers=headers,
                            data={"subject": "Anders", "audience": "non_members",
                                  "body_html": "x"})
    assert "al verstuurd" in geweigerd.text
    db_session.refresh(letter)
    assert letter.subject == "Het najaar"

    # 9. Copying makes a new draft without audience.
    kopie = client.post(f"/admin/nieuwsbrieven/{letter.id}/kopieren", headers=headers)
    nieuwe = _latest(db_session)
    assert kopie.headers["HX-Redirect"] == f"/admin/nieuwsbrieven/{nieuwe.id}"
    assert (nieuwe.subject, nieuwe.audience) == ("Het najaar", None)


def test_versturen_zonder_doelgroep_toont_de_reden(client, db_session, mailbox):
    headers = _login(client)
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    stap = client.get(f"/admin/nieuwsbrieven/{letter.id}/versturen")
    assert "Kies eerst voor wie" in stap.text
    poging = client.post(f"/admin/nieuwsbrieven/{letter.id}/versturen", headers=headers,
                         data={"reply_to": "association"})
    assert "Kies eerst voor wie" in poging.text
    assert db_session.query(Delivery).count() == 0


def test_met_een_plaatshouder_toont_het_scherm_de_zin_en_geen_verzendknop(
        client, db_session, mailbox):
    """Broken on purpose: `not blocked` taken out of `_nb_versturen.html` →
    the button is back and this test fails."""
    headers = _login(client)
    _subscriber(db_session, "piet@example.org")
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    nb.update_draft(db_session, letter, subject="Het najaar", audience="non_members",
                    body_html="<div>Inschrijven via [e-mailadres].</div>")

    stap = client.get(f"/admin/nieuwsbrieven/{letter.id}/versturen")
    assert "Er staat nog een plaatshouder" in stap.text
    assert "«Inschrijven via [e-mailadres].»" in stap.text
    assert "Versturen (1)" not in stap.text
    poging = client.post(f"/admin/nieuwsbrieven/{letter.id}/versturen", headers=headers,
                         data={"reply_to": "association"})
    assert "Er staat nog een plaatshouder" in poging.text
    assert db_session.query(Delivery).count() == 0

    test = client.post(f"/admin/nieuwsbrieven/{letter.id}/testmail", headers=headers)
    assert "Testmail verstuurd" in test.text


def test_een_concept_verwijderen_vraagt_bevestiging_op_het_formulier(client, db_session):
    """htmx reads `data-confirm` on the element that makes the request — for a
    form that is the form, not the button inside it (measured in htmx's source).

    Broken on purpose: the confirmation moved to the button (`confirm=` on
    `btn_danger`) → this test fails.
    """
    _login(client)
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    html = client.get(f"/admin/nieuwsbrieven/{letter.id}").text
    form = html.split(f'hx-post="/admin/nieuwsbrieven/{letter.id}/verwijderen"')[1].split(">")[0]
    assert "data-confirm" in form


def test_zonder_aanmelding_geen_toegang(client, db_session):
    antwoord = client.get("/admin/nieuwsbrieven", follow_redirects=False)
    assert antwoord.status_code in (302, 303, 401, 403)
    csrfloos = client.post("/admin/nieuwsbrieven", follow_redirects=False)
    assert csrfloos.status_code in (302, 303, 401, 403)
    assert db_session.query(Newsletter).count() == 0


# ── Subscribers and the import ───────────────────────────────────────────────

def test_abonnees_beheren(client, db_session):
    headers = _login(client)
    toegevoegd = client.post("/admin/nieuwsbrieven/abonnees", headers=headers,
                             data={"subscriber_email": "Nora@example.org",
                                   "first_name": "Nora"})
    assert "nora@example.org staat op de lijst" in toegevoegd.text
    nora = nb.subscriber_by_email(db_session, "nora@example.org")

    dubbel = client.post("/admin/nieuwsbrieven/abonnees", headers=headers,
                         data={"subscriber_email": "nora@example.org"})
    assert "staat al op de lijst" in dubbel.text

    client.post(f"/admin/nieuwsbrieven/abonnees/{nora.id}/uitschrijven", headers=headers)
    db_session.refresh(nora)
    assert nora.status == SUBSCRIBER_UNSUBSCRIBED

    gefilterd = client.get("/admin/nieuwsbrieven/abonnees?status=confirmed",
                           headers={"HX-Request": "true", "X-Raak-Filter": "1"})
    assert "nora@example.org" not in gefilterd.text

    client.post(f"/admin/nieuwsbrieven/abonnees/{nora.id}/verwijderen", headers=headers)
    assert nb.subscriber_by_email(db_session, "nora@example.org") is None


def test_de_import_via_het_scherm(client, db_session):
    headers = _login(client)
    _subscriber(db_session, "weg@example.org", status=SUBSCRIBER_UNSUBSCRIBED)
    inhoud = b"nieuw@example.org\r\nweg@example.org\r\ngeen adres\r\n"

    stap2 = client.post("/admin/nieuwsbrieven/abonnees/import", headers=headers,
                        files={"file": ("adressen.txt", inhoud, "text/plain")})
    assert stap2.status_code == 200
    assert "Importeren (1)" in stap2.text
    # Koen, 17 September 2026: no notice about a first-letter explanation.
    assert "geen bevestigingsmail" not in stap2.text
    assert db_session.query(Subscriber).count() == 1, "de voorvertoning schrijft niets"

    tekst = stap2.text.split('<textarea name="text"')[1].split(">", 1)[1].split("</textarea>")[0]
    klaar = client.post("/admin/nieuwsbrieven/abonnees/import/bevestigen", headers=headers,
                        data={"text": tekst.replace("&#13;", "\r")})
    assert klaar.status_code == 204
    assert nb.subscriber_by_email(db_session, "nieuw@example.org").status == SUBSCRIBER_CONFIRMED
    assert nb.subscriber_by_email(db_session, "weg@example.org").status == SUBSCRIBER_UNSUBSCRIBED


def test_de_instellingen(client, db_session):
    headers = _login(client)
    from app.kernel.tenant_config import (tenant_newsletter_daily_cap,
                                          tenant_newsletter_house_style)

    client.post("/admin/nieuwsbrieven/instellingen", headers=headers,
                data={"house_style": "Warm, jij-vorm.", "daily_cap": "120"})
    assert tenant_newsletter_house_style(db_session) == "Warm, jij-vorm."
    assert tenant_newsletter_daily_cap(db_session) == 120

    fout = client.post("/admin/nieuwsbrieven/instellingen", headers=headers,
                       data={"house_style": "", "daily_cap": "0"})
    assert "groter dan nul" in fout.text
    assert tenant_newsletter_daily_cap(db_session) == 120


# ── The public side ──────────────────────────────────────────────────────────

def test_inschrijven_bevestigen_en_uitschrijven_zonder_login(client, db_session,
                                                              confirmations):
    """Opening a link never acts; the button does (mail scanners open links).

    Broken on purpose: confirming on the GET → the pending assertion after the
    GET fails.
    """
    pagina = client.get("/nieuwsbrief")
    assert pagina.status_code == 200 and 'name="email"' in pagina.text

    ingeschreven = client.post("/nieuwsbrief", data={"email": "an@example.org",
                                                     "first_name": "An"})
    assert "Kijk in je mailbox" in ingeschreven.text
    an = nb.subscriber_by_email(db_session, "an@example.org")
    assert an.status == SUBSCRIBER_PENDING
    link = confirmations[0][1]
    pad = link[link.index("/nieuwsbrief/"):]

    geopend = client.get(pad)
    assert "Ja, ik wil de nieuwsbrief" in geopend.text
    db_session.refresh(an)
    assert an.status == SUBSCRIBER_PENDING, "de link openen bevestigt niets"

    bevestigd = client.post(pad)
    assert "Je bent ingeschreven" in bevestigd.text
    db_session.refresh(an)
    assert an.status == SUBSCRIBER_CONFIRMED

    uit = f"/nieuwsbrief/uitschrijven/{an.unsubscribe_token}"
    assert "Uitschrijven" in client.get(uit).text
    db_session.refresh(an)
    assert an.status == SUBSCRIBER_CONFIRMED, "de link openen schrijft niet uit"
    assert "Je bent uitgeschreven" in client.post(uit).text
    db_session.refresh(an)
    assert an.status == SUBSCRIBER_UNSUBSCRIBED

    opnieuw = client.post(f"/nieuwsbrief/opnieuw/{an.unsubscribe_token}")
    assert "Je bent ingeschreven" in opnieuw.text


def test_uitschrijven_met_een_klik_vanuit_het_mailprogramma(client, db_session):
    """RFC 8058: the mail client POSTs `List-Unsubscribe=One-Click`."""
    piet = _subscriber(db_session, "piet@example.org")
    antwoord = client.post(f"/nieuwsbrief/uitschrijven/{piet.unsubscribe_token}",
                           data={"List-Unsubscribe": "One-Click"})
    assert antwoord.status_code == 200 and antwoord.text == "ok"
    db_session.refresh(piet)
    assert piet.status == SUBSCRIBER_UNSUBSCRIBED


def test_de_testlink_verandert_niets(client, db_session):
    piet = _subscriber(db_session, "piet@example.org")
    assert "Dit was een testmail" in client.get("/nieuwsbrief/uitschrijven/test").text
    assert "Dit was een testmail" in client.post("/nieuwsbrief/uitschrijven/test").text
    db_session.refresh(piet)
    assert piet.status == SUBSCRIBER_CONFIRMED


def test_een_onbekende_link_zegt_dat_ze_niet_meer_werkt(client, db_session):
    assert "werkt niet meer" in client.get("/nieuwsbrief/bevestigen/onzin").text
    assert "werkt niet meer" in client.post("/nieuwsbrief/uitschrijven/onzin").text


def test_de_honingpot_slaat_niets_op(client, db_session, confirmations):
    antwoord = client.post("/nieuwsbrief", data={"email": "bot@example.org",
                                                 "website": "http://spam.example"})
    assert "Kijk in je mailbox" in antwoord.text
    assert db_session.query(Subscriber).count() == 0
    assert confirmations == []


def test_een_ongeldig_adres_blijft_op_het_formulier(client, db_session, confirmations):
    antwoord = client.post("/nieuwsbrief", data={"email": "geen-adres"},
                           headers={"HX-Request": "true"})
    assert "geen geldig e-mailadres" in antwoord.text
    assert 'name="email"' in antwoord.text


def test_automatisch_bewaren_maakt_het_formulier_niet_onklikbaar(client, db_session):
    """The shell greys out and blocks the element that makes a request
    (`.htmx-request`). The autosave form points its indicator at the status
    line, so typing never blocks the editor.

    Broken on purpose: `hx-indicator` removed → this test fails (and the e2e
    click on "Leden" lands on a div).
    """
    _login(client)
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    html = client.get(f"/admin/nieuwsbrieven/{letter.id}").text
    formulier = html.split('id="nb-formulier"')[1].split(">")[0]
    assert 'hx-indicator="#nb-bewaard"' in formulier


def test_de_nieuwsbrief_staat_alleen_als_link_op_de_homepagina(client, db_session):
    """Koen, 19 September 2026: the signup block stood under every public page,
    a sent contact form included. Only the home page links to the newsletter.

    Broken on purpose: the include put back in `site_base.html` → the form is on
    every page again and the first two assertions fail.
    """
    home = client.get("/").text
    assert 'id="nb-home-link"' in home
    assert 'id="nb-voet"' not in home, "geen inschrijfformulier in de voet"
    for pad in ("/activiteiten", "/lid-worden", "/berichten"):
        assert 'id="nb-voet"' not in client.get(pad).text, pad

    pagina = client.get("/nieuwsbrief").text
    assert pagina.count('name="email"') == 1


# ── Attachments as links (Koen, 17 September 2026) ───────────────────────────

def test_een_bijlage_wordt_een_link_op_de_cursor(client, db_session):
    """Upload a PDF → a public media file and the link that goes at the cursor.

    Broken on purpose: the newsletter kind left out of `DOCUMENT_KINDS` → the
    upload is refused and this test fails.
    """
    from app.domains.media.api import MediaAsset

    headers = _login(client)
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    pdf = b"%PDF-1.4 het programma"

    antwoord = client.post(f"/admin/nieuwsbrieven/{letter.id}/bijlage", headers=headers,
                           files={"file": ("Het_programma.pdf", pdf, "application/pdf")})

    assert antwoord.status_code == 200, antwoord.text
    asset = db_session.query(MediaAsset).filter(MediaAsset.kind == "newsletter_file").one()
    assert f"/api/v1/media/{asset.id}" in antwoord.text
    assert "Download Het programma (pdf)" in antwoord.text
    publiek = client.get(f"/api/v1/media/{asset.id}", cookies={})
    assert publiek.status_code == 200 and publiek.content == pdf


def test_een_verkeerd_bestand_wordt_geweigerd_met_de_reden(client, db_session):
    headers = _login(client)
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    antwoord = client.post(f"/admin/nieuwsbrieven/{letter.id}/bijlage", headers=headers,
                           files={"file": ("macro.docm", b"PK...", "application/vnd.ms-word")})
    assert antwoord.status_code == 400
    assert "PDF of een afbeelding" in antwoord.text


def test_de_bijlagen_staan_niet_in_de_mediabibliotheek(client, db_session):
    from app.domains.media.api import VALID_KINDS

    assert "newsletter_file" not in VALID_KINDS


def test_het_voorbeeld_toont_de_brief_zoals_hij_aankomt(client, db_session):
    """Sinds de activiteit als markering in de brief staat (#984, 19 september
    2026) moet de schrijver het resultaat kunnen zien zonder te mailen.

    Broken on purpose: `expand_blocks` uit `render_mail` → het voorbeeld toont
    de rauwe markering en deze test faalt.
    """
    _login(client)
    rum = _activity(db_session, "Rumproefavond", date.today() + timedelta(days=10))
    rum.description = "We proeven acht rums."
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    nb.update_draft(db_session, letter, subject="Het najaar", audience="members",
                    body_html=f"<div>Beste,</div><div>[[activiteit:{rum.id}|Rumproefavond]]</div>")

    voorbeeld = client.get(f"/admin/nieuwsbrieven/{letter.id}/voorbeeld")

    assert voorbeeld.status_code == 200
    assert "[[activiteit:" not in voorbeeld.text, "de markering hoort een blok te zijn"
    assert "We proeven acht rums." in voorbeeld.text
    assert "Rumproefavond" in voorbeeld.text
    assert 'class="nb-blok-titel" style=' in voorbeeld.text, "de opmaak staat erop"


def test_de_kalender_neemt_alleen_wat_je_aanvinkt(client, db_session):
    """Koen, 19 september 2026: de kalender blijft compacte regels, maar je
    kiest wat erin staat — een activiteit verderop mag mee.

    Broken on purpose: `ids` niet doorgegeven aan `calendar_html` → de kalender
    negeert de keuze en deze test faalt op de tweede activiteit.
    """
    _login(client)
    dichtbij = _activity(db_session, "Rumproefavond", date.today() + timedelta(days=10))
    ver = _activity(db_session, "Kerstmarkt", date.today() + timedelta(days=120))
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)

    kiezer = client.get(f"/admin/nieuwsbrieven/{letter.id}/activiteiten?purpose=calendar")
    assert kiezer.status_code == 200
    assert "nb-kal-vinkje" in kiezer.text, "de kalenderkeuze staat op vinkjes"
    vinkjes = kiezer.text.split('class="nb-kal-vinkje"')
    assert f'value="{dichtbij.id}"' in kiezer.text and f'value="{ver.id}"' in kiezer.text
    assert len(vinkjes) == 3, "beide activiteiten staan in de lijst"

    gekozen = client.get(f"/admin/nieuwsbrieven/{letter.id}/invoegen/kalender"
                         f"?ids={dichtbij.id},{ver.id}")
    assert "Rumproefavond" in gekozen.text and "Kerstmarkt" in gekozen.text

    standaard = client.get(f"/admin/nieuwsbrieven/{letter.id}/invoegen/kalender")
    assert "Rumproefavond" in standaard.text
    assert "Kerstmarkt" not in standaard.text, "zonder keuze alleen de komende weken"
