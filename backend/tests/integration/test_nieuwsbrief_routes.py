"""The newsletter along its ROUTES, the way a board member and a visitor use it (#984).

`test_nieuwsbrief.py` checks the rules through the service. This file walks the
screens over HTTP, with CSRF: write a letter, insert an activity, send a test,
send it for real, read the archive; manage subscribers and the import; and the
public side — sign up, confirm, unsubscribe — without a login.
"""

import json
import re
from datetime import timedelta

import pytest

from app.domains.activities.api import Activity, ActivityDate
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.newsletter import service as nb
from app.domains.newsletter.api import Audience
from app.domains.newsletter.models import (
    Delivery,
    LetterStatus,
    Newsletter,
    Subscriber,
    SubscriberStatus,
)
from app.kernel.clock import belgian_today
from tests._letter import letter_doc
from tests.conftest import SEEDED_ADMIN_EMAIL, form_guard_fields

pytestmark = pytest.mark.ui_serverrendered


def _login(client) -> dict:
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value), "HX-Request": "true"}


@pytest.fixture
def mailbox(monkeypatch):
    sent = []

    def fake(
        to_email,
        subject,
        body_html,
        *,
        email_type,
        reply_to=None,
        unsubscribe_url=None,
        body_text=None,
    ):
        sent.append(
            {
                "to": to_email,
                "subject": subject,
                "body": body_html,
                "reply_to": reply_to,
                "unsubscribe_url": unsubscribe_url,
                "body_text": body_text,
            }
        )
        return "sent"

    monkeypatch.setattr("app.domains.mail.api.send_campaign_mail", fake)
    return sent


@pytest.fixture
def confirmations(monkeypatch):
    sent = []
    monkeypatch.setattr(
        "app.domains.mail.api.send_newsletter_confirmation",
        lambda to, name, url: sent.append((to, url)) or "sent",
    )
    return sent


def _activity(db, name, day, location="Miloheem"):
    activity = Activity(name=name, location=location, slug=name.lower().replace(" ", "-"))
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=day))
    db.flush()
    return activity


def _subscriber(db, email, status=SubscriberStatus.CONFIRMED):
    row = Subscriber(email=email, status=status, source="admin", unsubscribe_token=f"tok-{email}")
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
    rum = _activity(db_session, "Rumproefavond", belgian_today() + timedelta(days=20))

    # 1. The list, and the menu item.
    lijst = client.get("/admin/nieuwsbrieven")
    assert lijst.status_code == 200
    assert 'href="/admin/nieuwsbrieven"' in lijst.text

    # 2. A new draft opens as its own page.
    nieuw = client.post("/admin/nieuwsbrieven", headers=headers)
    assert nieuw.status_code == 204
    letter = _latest(db_session)
    assert nieuw.headers["HX-Redirect"] == f"/admin/nieuwsbrieven/{letter.id}?bewerken=1"
    scherm = client.get(f"/admin/nieuwsbrieven/{letter.id}")
    assert scherm.status_code == 200
    assert 'id="nb-editor"' in scherm.text
    # The audience is four radio buttons on the page (#2183), none chosen on a new draft.
    radios = re.findall(r'<input type="radio" name="audience" value="([^"]*)"([^>]*)>', scherm.text)
    assert [value for value, _rest in radios] == ["members", "non_members", "both", "participants"]
    assert not any("checked" in rest for _value, rest in radios)

    # 3. "Blok invoegen › Activiteit" offers the letter's FEATURED activities: the
    # editor's configuration carries them, and the block it inserts is a REFERENCE
    # (#984, #2023) that the mail turns into the block when the letter is sent.
    config = json.loads(
        re.search(r"data-config='([^']*)'", scherm.text).group(1).replace("&#34;", '"')
    )
    assert [a["id"] for a in config["activity"]["activities"]] == [rum.id]
    assert "Rumproefavond" in config["activity"]["activities"][0]["label"]
    assert "calendar" in config["insert"] and "closing" in config["insert"]
    kiezer = client.get(f"/admin/nieuwsbrieven/{letter.id}/activiteiten?purpose=featured&q=rum")
    assert "Rumproefavond" in kiezer.text

    # 4. One Opslaan stores the subject, the preview text, the audience and the text, and
    # sends the browser back to the page (#2183).
    bewaard = client.post(
        f"/admin/nieuwsbrieven/{letter.id}/bewaren",
        headers=headers,
        data={
            "subject": "Het najaar",
            "preview_text": "Wat komt er",
            "audience": "non_members",
            "body": json.dumps(
                letter_doc(f"<div>Beste,</div><div>[[activiteit:{rum.id}|Rumproefavond]]</div>")
            ),
        },
    )
    assert bewaard.status_code == 204
    assert bewaard.headers["HX-Redirect"] == f"/admin/nieuwsbrieven/{letter.id}"
    db_session.refresh(letter)
    assert (letter.subject, letter.preview_text, letter.audience) == (
        "Het najaar",
        "Wat komt er",
        Audience.NON_MEMBERS,
    )

    # 5. The test mail goes to the signed-in admin only.
    test = client.post(f"/admin/nieuwsbrieven/{letter.id}/testmail", headers=headers)
    assert "Testmail verstuurd" in test.text
    assert [m["to"] for m in mailbox] == [SEEDED_ADMIN_EMAIL]

    # 6. The send screen repeats audience and count; sending starts the queue.
    stap = client.get(f"/admin/nieuwsbrieven/{letter.id}/versturen")
    assert "Abonnees · 1 adres<" in stap.text and "Verstuur naar 1 abonnee<" in stap.text
    verstuurd = client.post(
        f"/admin/nieuwsbrieven/{letter.id}/versturen", headers=headers, data={"reply_to": "sender"}
    )
    assert verstuurd.status_code == 204
    db_session.refresh(letter)
    assert letter.status == LetterStatus.SENDING
    assert letter.reply_to_address == SEEDED_ADMIN_EMAIL

    nb.send_batch(db_session, letter.id)
    db_session.refresh(letter)
    assert letter.status == LetterStatus.SENT
    assert [m["to"] for m in mailbox][-1] == "piet@example.org"

    # 7. The same address now opens the archive, not the editor.
    archief = client.get(f"/admin/nieuwsbrieven/{letter.id}")
    assert 'id="nb-editor"' not in archief.text
    assert "piet@example.org" in archief.text
    assert "Kopiëren naar een nieuw concept" in archief.text
    filter_ = client.get(
        f"/admin/nieuwsbrieven/{letter.id}?status=failed",
        headers={"HX-Request": "true", "X-Raak-Filter": "1"},
    )
    assert "piet@example.org" not in filter_.text

    # 8. A sent letter cannot be saved over.
    geweigerd = client.post(
        f"/admin/nieuwsbrieven/{letter.id}/bewaren",
        headers=headers,
        data={"subject": "Anders", "audience": "non_members", "body": "x"},
    )
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
    poging = client.post(
        f"/admin/nieuwsbrieven/{letter.id}/versturen",
        headers=headers,
        data={"reply_to": "association"},
    )
    assert "Kies eerst voor wie" in poging.text
    assert db_session.query(Delivery).count() == 0


def test_met_een_plaatshouder_toont_het_scherm_de_zin_en_geen_verzendknop(
    client, db_session, mailbox
):
    """Broken on purpose: `not blocked` taken out of `_nb_versturen.html` →
    the button is back and this test fails."""
    headers = _login(client)
    _subscriber(db_session, "piet@example.org")
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    nb.update_draft(
        db_session,
        letter,
        subject="Het najaar",
        audience="non_members",
        body_html="<div>Inschrijven via [e-mailadres].</div>",
    )

    stap = client.get(f"/admin/nieuwsbrieven/{letter.id}/versturen")
    assert "Er staat nog een plaatshouder" in stap.text
    assert "«Inschrijven via [e-mailadres].»" in stap.text
    assert "Verstuur naar 1 abonnee" not in stap.text
    poging = client.post(
        f"/admin/nieuwsbrieven/{letter.id}/versturen",
        headers=headers,
        data={"reply_to": "association"},
    )
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
    # #2172: the request is made by the edit bar's button now; its whole tag carries both.
    at = html.index(f'hx-post="/admin/nieuwsbrieven/{letter.id}/verwijderen"')
    tag = html[html.rindex("<", 0, at) : html.index(">", at)]
    assert "data-confirm" in tag and "data-form-delete" in tag


def test_zonder_aanmelding_geen_toegang(client, db_session):
    antwoord = client.get("/admin/nieuwsbrieven", follow_redirects=False)
    assert antwoord.status_code in (302, 303, 401, 403)
    csrfloos = client.post("/admin/nieuwsbrieven", follow_redirects=False)
    assert csrfloos.status_code in (302, 303, 401, 403)
    assert db_session.query(Newsletter).count() == 0


# ── Subscribers and the import ───────────────────────────────────────────────


def test_abonnees_beheren(client, db_session):
    headers = _login(client)
    toegevoegd = client.post(
        "/admin/nieuwsbrieven/abonnees",
        headers=headers,
        data={"subscriber_email": "Nora@example.org", "first_name": "Nora"},
    )
    # #2109: "+ Adres" is a page of its own; success goes back to the list, naming the address.
    assert toegevoegd.status_code == 204
    assert toegevoegd.headers["HX-Redirect"] == (
        "/admin/nieuwsbrieven/abonnees?toegevoegd=nora%40example.org"
    )
    terug = client.get(toegevoegd.headers["HX-Redirect"])
    assert "nora@example.org staat op de lijst" in terug.text
    nora = nb.subscriber_by_email(db_session, "nora@example.org")

    dubbel = client.post(
        "/admin/nieuwsbrieven/abonnees",
        headers=headers,
        data={"subscriber_email": "nora@example.org"},
    )
    assert dubbel.status_code == 422 and "staat al op de lijst" in dubbel.text
    assert dubbel.headers["HX-Retarget"] == "#abonnee-melding"

    client.post(f"/admin/nieuwsbrieven/abonnees/{nora.id}/uitschrijven", headers=headers)
    db_session.refresh(nora)
    assert nora.status == SubscriberStatus.UNSUBSCRIBED

    gefilterd = client.get(
        "/admin/nieuwsbrieven/abonnees/lijst?status=confirmed",
        headers={"HX-Request": "true", "X-Raak-Filter": "1"},
    )
    assert "nora@example.org" not in gefilterd.text

    # Removing an address that unsubscribed keeps the opt-out (CR-36, C4.4): the row stays
    # with its address and its status, the name and the tokens go.
    client.post(f"/admin/nieuwsbrieven/abonnees/{nora.id}/verwijderen", headers=headers)
    kept = nb.subscriber_by_email(db_session, "nora@example.org")
    assert kept is not None and kept.status == SubscriberStatus.UNSUBSCRIBED
    assert kept.first_name is None


def test_de_import_via_het_scherm(client, db_session):
    headers = _login(client)
    _subscriber(db_session, "weg@example.org", status=SubscriberStatus.UNSUBSCRIBED)
    inhoud = b"nieuw@example.org\r\nweg@example.org\r\ngeen adres\r\n"

    stap2 = client.post(
        "/admin/nieuwsbrieven/abonnees/import",
        headers=headers,
        files={"file": ("adressen.txt", inhoud, "text/plain")},
    )
    assert stap2.status_code == 200
    assert "Importeren (1)" in stap2.text
    # Koen, 17 September 2026: no notice about a first-letter explanation.
    assert "geen bevestigingsmail" not in stap2.text
    assert db_session.query(Subscriber).count() == 1, "de voorvertoning schrijft niets"

    tekst = stap2.text.split('<textarea name="text"')[1].split(">", 1)[1].split("</textarea>")[0]
    klaar = client.post(
        "/admin/nieuwsbrieven/abonnees/import/bevestigen",
        headers=headers,
        data={"text": tekst.replace("&#13;", "\r")},
    )
    assert klaar.status_code == 204
    assert (
        nb.subscriber_by_email(db_session, "nieuw@example.org").status == SubscriberStatus.CONFIRMED
    )
    assert (
        nb.subscriber_by_email(db_session, "weg@example.org").status
        == SubscriberStatus.UNSUBSCRIBED
    )


def test_de_instellingen(client, db_session):
    headers = _login(client)
    from app.kernel.tenant_config import tenant_newsletter_daily_cap, tenant_newsletter_house_style

    client.post(
        "/admin/nieuwsbrieven/instellingen",
        headers=headers,
        data={"house_style": "Warm, jij-vorm.", "daily_cap": "120"},
    )
    assert tenant_newsletter_house_style(db_session) == "Warm, jij-vorm."
    assert tenant_newsletter_daily_cap(db_session) == 120

    fout = client.post(
        "/admin/nieuwsbrieven/instellingen",
        headers=headers,
        data={"house_style": "", "daily_cap": "0"},
    )
    assert "groter dan nul" in fout.text
    assert tenant_newsletter_daily_cap(db_session) == 120


# ── The public side ──────────────────────────────────────────────────────────


def test_inschrijven_bevestigen_en_uitschrijven_zonder_login(client, db_session, confirmations):
    """Opening a link never acts; the button does (mail scanners open links).

    Broken on purpose: confirming on the GET → the pending assertion after the
    GET fails.
    """
    pagina = client.get("/nieuwsbrief")
    assert pagina.status_code == 200 and 'name="email"' in pagina.text

    ingeschreven = client.post(
        "/nieuwsbrief", data={**form_guard_fields(), "email": "an@example.org", "first_name": "An"}
    )
    assert "Kijk in je mailbox" in ingeschreven.text
    an = nb.subscriber_by_email(db_session, "an@example.org")
    assert an.status == SubscriberStatus.PENDING
    link = confirmations[0][1]
    pad = link[link.index("/nieuwsbrief/") :]

    geopend = client.get(pad)
    assert "Ja, ik wil de nieuwsbrief" in geopend.text
    db_session.refresh(an)
    assert an.status == SubscriberStatus.PENDING, "de link openen bevestigt niets"

    bevestigd = client.post(pad)
    assert "Je bent ingeschreven" in bevestigd.text
    db_session.refresh(an)
    assert an.status == SubscriberStatus.CONFIRMED

    uit = f"/nieuwsbrief/uitschrijven/{an.unsubscribe_token}"
    assert "Uitschrijven" in client.get(uit).text
    db_session.refresh(an)
    assert an.status == SubscriberStatus.CONFIRMED, "de link openen schrijft niet uit"
    assert "Je bent uitgeschreven" in client.post(uit).text
    db_session.refresh(an)
    assert an.status == SubscriberStatus.UNSUBSCRIBED

    opnieuw = client.post(f"/nieuwsbrief/opnieuw/{an.unsubscribe_token}")
    assert "Je bent ingeschreven" in opnieuw.text


def test_uitschrijven_met_een_klik_vanuit_het_mailprogramma(client, db_session):
    """RFC 8058: the mail client POSTs `List-Unsubscribe=One-Click`."""
    piet = _subscriber(db_session, "piet@example.org")
    antwoord = client.post(
        f"/nieuwsbrief/uitschrijven/{piet.unsubscribe_token}",
        data={"List-Unsubscribe": "One-Click"},
    )
    assert antwoord.status_code == 200 and antwoord.text == "ok"
    db_session.refresh(piet)
    assert piet.status == SubscriberStatus.UNSUBSCRIBED


def test_de_testlink_verandert_niets(client, db_session):
    piet = _subscriber(db_session, "piet@example.org")
    assert "Dit was een testmail" in client.get("/nieuwsbrief/uitschrijven/test").text
    assert "Dit was een testmail" in client.post("/nieuwsbrief/uitschrijven/test").text
    db_session.refresh(piet)
    assert piet.status == SubscriberStatus.CONFIRMED


def test_een_onbekende_link_zegt_dat_ze_niet_meer_werkt(client, db_session):
    assert "werkt niet meer" in client.get("/nieuwsbrief/bevestigen/onzin").text
    assert "werkt niet meer" in client.post("/nieuwsbrief/uitschrijven/onzin").text


def test_de_honingpot_slaat_niets_op(client, db_session, confirmations):
    antwoord = client.post(
        "/nieuwsbrief",
        data={**form_guard_fields(), "email": "bot@example.org", "website": "http://spam.example"},
    )
    assert "Kijk in je mailbox" in antwoord.text
    assert db_session.query(Subscriber).count() == 0
    assert confirmations == []


def test_een_ongeldig_adres_blijft_op_het_formulier(client, db_session, confirmations):
    antwoord = client.post(
        "/nieuwsbrief",
        data={**form_guard_fields(), "email": "geen-adres"},
        headers={"HX-Request": "true"},
    )
    assert "geen geldig e-mailadres" in antwoord.text
    assert 'name="email"' in antwoord.text


def test_nothing_of_the_letter_saves_itself(client, db_session):
    """#2183: the letter is one record page. Its form has no trigger of its own — the
    autosave of the text is gone — and every field belongs to it by its `form`
    attribute.

    Broken on purpose: `hx-trigger="change"` back on the form → this test fails."""
    _login(client)
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    html = client.get(f"/admin/nieuwsbrieven/{letter.id}").text
    formulier = html.split('id="nb-formulier"')[1].split(">")[0]
    assert "hx-trigger" not in formulier and "data-record-form" in formulier
    for name in ("subject", "preview_text", "body", "csrf_token"):
        assert re.search(rf'name="{name}"[^>]*form="nb-formulier"', html), name


def test_de_nieuwsbrief_staat_alleen_als_link_in_de_voet(client, db_session):
    """Koen, 19 September 2026: the signup block stood under every public page,
    a sent contact form included. The form lives on `/nieuwsbrief` only.

    #1588 (CR-11 pilot B) moved the call from the home page (`#nb-home-link`)
    to the footer of every public page: one link, `#nb-voet-link`, in the
    newsletter column — a link, never the form.

    Broken on purpose: the include put back in `site_base.html` → the form is on
    every page again and the `nb-voet` assertions fail.
    """
    home = client.get("/").text
    assert 'id="nb-home-link"' not in home, "the call left the home page (#1588)"
    for pad in ("/", "/activiteiten", "/lid-worden", "/berichten"):
        html = client.get(pad).text
        assert 'id="nb-voet"' not in html, f"geen inschrijfformulier in de voet: {pad}"
        footer = html[html.index("<footer") : html.index("</footer>")]
        column = footer[footer.index("data-footer-newsletter") : footer.index("</section>")]
        assert column.count('id="nb-voet-link" href="/nieuwsbrief"') == 1, pad
        assert html.count('id="nb-voet-link"') == 1, pad
        assert "<form" not in footer and 'name="email"' not in footer, pad

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

    antwoord = client.post(
        f"/admin/nieuwsbrieven/{letter.id}/bijlage",
        headers=headers,
        files={"file": ("Het_programma.pdf", pdf, "application/pdf")},
    )

    assert antwoord.status_code == 200, antwoord.text
    asset = db_session.query(MediaAsset).filter(MediaAsset.kind == "newsletter_file").one()
    assert f"/api/v1/media/{asset.id}" in antwoord.text
    assert "Download Het programma (pdf)" in antwoord.text
    publiek = client.get(f"/api/v1/media/{asset.id}", cookies={})
    assert publiek.status_code == 200 and publiek.content == pdf


def test_een_verkeerd_bestand_wordt_geweigerd_met_de_reden(client, db_session):
    headers = _login(client)
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    antwoord = client.post(
        f"/admin/nieuwsbrieven/{letter.id}/bijlage",
        headers=headers,
        files={"file": ("macro.docm", b"PK...", "application/vnd.ms-word")},
    )
    assert antwoord.status_code == 400
    assert "PDF of een afbeelding" in antwoord.text


def test_de_bijlagen_staan_niet_in_de_mediabibliotheek(client, db_session):
    from app.domains.media.api import VALID_KINDS

    assert "newsletter_file" not in VALID_KINDS


def test_het_voorbeeld_toont_de_brief_zoals_hij_aankomt(client, db_session):
    """Sinds de activiteit als markering in de brief staat (#984, 19 september
    2026) moet de schrijver het resultaat kunnen zien zonder te mailen.

    Broken on purpose: `render_body` uit `render_mail` → het voorbeeld toont
    de rauwe markering en deze test faalt.
    """
    _login(client)
    rum = _activity(db_session, "Rumproefavond", belgian_today() + timedelta(days=10))
    rum.description = "We proeven acht rums."
    db_session.flush()  # the seed is the test's own write, before the app commits (#1885 gate 2)
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    nb.update_draft(
        db_session,
        letter,
        subject="Het najaar",
        audience="members",
        body_html=f"<div>Beste,</div><div>[[activiteit:{rum.id}|Rumproefavond]]</div>",
    )

    voorbeeld = client.get(f"/admin/nieuwsbrieven/{letter.id}/voorbeeld")

    assert voorbeeld.status_code == 200
    assert "[[activiteit:" not in voorbeeld.text, "de markering hoort een blok te zijn"
    assert "We proeven acht rums." in voorbeeld.text
    assert "Rumproefavond" in voorbeeld.text
    assert 'class="nb-blok-titel" style=' in voorbeeld.text, "de opmaak staat erop"


def test_de_kalender_is_de_kalendergroep_van_de_brief(client, db_session):
    """Koen, 19 september 2026: de kalender blijft compacte regels, maar je kiest
    wat erin staat. Since #1562 that choice is the letter's own calendar group —
    the group the page shows — and the calendar block of the letter renders exactly
    it, when the letter is sent (#2023).

    Broken on purpose: `mail_blocks` handing no ids to `calendar_html` → the calendar
    ignores the group and this test fails on the activity that was taken out.
    """
    headers = _login(client)
    dichtbij = _activity(db_session, "Rumproefavond", belgian_today() + timedelta(days=10))
    ver = _activity(db_session, "Kerstmarkt", belgian_today() + timedelta(days=120))
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)

    calendar = {"type": "doc", "content": [{"type": "calendar"}]}
    nb.update_draft(db_session, letter, subject="x", body=calendar, audience="members")

    def rendered() -> str:
        return nb.render_body(db_session, letter, base_url="https://raak.example")

    standaard = rendered()
    assert "Rumproefavond" in standaard and "Kerstmarkt" in standaard, (
        "a new letter's calendar holds the next nine, however far"
    )

    weg = client.post(
        f"/admin/nieuwsbrieven/{letter.id}/keuzes/calendar/{ver.id}/weg", headers=headers
    )
    assert weg.status_code == 200
    gekozen = rendered()
    assert "Rumproefavond" in gekozen and "Kerstmarkt" not in gekozen

    kiezer = client.get(f"/admin/nieuwsbrieven/{letter.id}/activiteiten?purpose=calendar")
    assert kiezer.status_code == 200 and "nb-kal-vinkje" not in kiezer.text
    assert f'name="activity_id" value="{ver.id}"' in kiezer.text
    assert f'hx-post="/admin/nieuwsbrieven/{letter.id}/keuzes/calendar"' in kiezer.text
    client.post(
        f"/admin/nieuwsbrieven/{letter.id}/keuzes/calendar",
        headers=headers,
        data={"activity_id": str(ver.id)},
    )
    assert "Kerstmarkt" in rendered()
    assert dichtbij.id in nb.choices_of(db_session, letter).calendar


def test_de_abonneeslijst_staat_op_de_kit(client, db_session):
    """#2109 (§5.1): drie cijfers in de titelrij, vier segmenten, zoeken op adres en
    voornaam, sorteren op 'sinds', een pagina van vijftig, en het toevoegformulier
    onder de tabel is weg — '+ Adres' opent een eigen pagina."""
    headers = _login(client)
    for i in range(52):
        _subscriber(db_session, f"lijst{i:02d}@example.org")
    _subscriber(db_session, "wacht@example.org", status=SubscriberStatus.PENDING)
    _subscriber(db_session, "weg@example.org", status=SubscriberStatus.UNSUBSCRIBED)
    pagina = client.get("/admin/nieuwsbrieven/abonnees").text
    assert "data-list-page" in pagina and "Adres toevoegen" not in pagina
    assert "/admin/nieuwsbrieven/abonnees/nieuw" in pagina and "Lijst importeren" in pagina
    for woord in ("Bevestigd", "Wachten", "Uitgeschreven"):
        assert f">{woord}<" in pagina, woord
    balk = pagina.split("data-status-filter", 1)[1].split("</fieldset>", 1)[0]
    assert [x.strip() for x in re.findall(r"<span[^>]*>([^<]+)</span>", balk)] == [
        "Alle",
        "Bevestigd",
        "Wachten",
        "Uitgeschreven",
    ]
    assert pagina.count("data-subscriber-row") == 50, "one page of fifty"
    hx = {**headers, "HX-Request": "true"}
    tweede = client.get("/admin/nieuwsbrieven/abonnees/lijst?page=2", headers=hx).text
    assert 0 < tweede.count("data-subscriber-row") <= 50
    wacht = client.get("/admin/nieuwsbrieven/abonnees/lijst?status=pending", headers=hx).text
    assert "wacht@example.org" in wacht and "lijst00@example.org" not in wacht
    zoek = client.get("/admin/nieuwsbrieven/abonnees/lijst?q=lijst07", headers=hx).text
    assert "lijst07@example.org" in zoek and "lijst08@example.org" not in zoek
    nieuw = client.get("/admin/nieuwsbrieven/abonnees/nieuw")
    assert nieuw.status_code == 200 and 'name="subscriber_email"' in nieuw.text


def test_the_subject_and_the_preview_text_are_stored_with_the_letter(client, db_session):
    """#2183: Opslaan stores the subject and the preview text, whatever else the form
    holds, and a letter that was saved with them reads them back.

    Broken on purpose: `subject` / `preview_text` left out of `newsletter_save` → red."""
    headers = _login(client)
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    saved = client.post(
        f"/admin/nieuwsbrieven/{letter.id}/bewaren",
        headers=headers,
        data={"subject": "Het najaar", "preview_text": "Wat komt er", "audience": "members"},
    )
    assert saved.status_code == 204
    page = client.get(f"/admin/nieuwsbrieven/{letter.id}").text
    field = re.search(r'<input[^>]*id="nb-onderwerp"[^>]*>', page).group(0)
    assert 'value="Het najaar"' in field
    assert "Wat komt er" in page


def test_an_unknown_audience_is_refused_on_the_message_line_and_nothing_is_stored(
    client, db_session
):
    headers = _login(client)
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    refused = client.post(
        f"/admin/nieuwsbrieven/{letter.id}/bewaren",
        headers=headers,
        data={"subject": "Anders", "audience": "iedereen-op-aarde"},
    )
    assert refused.status_code == 422
    assert refused.headers["HX-Retarget"] == "#nb-melding"
    assert "Onbekende doelgroep" in refused.text
    db_session.refresh(letter)
    assert letter.subject == ""


def test_versturen_refuses_a_letter_without_a_subject_or_an_audience(client, db_session):
    headers = _login(client)
    letter = nb.create_newsletter(db_session, created_by=SEEDED_ADMIN_EMAIL)
    first = client.post(f"/admin/nieuwsbrieven/{letter.id}/versturen", headers=headers, data={})
    assert "Kies eerst voor wie deze nieuwsbrief is." in first.text
    nb.update_draft(db_session, letter, subject="", audience="members")
    second = client.post(f"/admin/nieuwsbrieven/{letter.id}/versturen", headers=headers, data={})
    assert "Geef de nieuwsbrief eerst een onderwerp." in second.text
    db_session.refresh(letter)
    assert letter.status == LetterStatus.DRAFT
