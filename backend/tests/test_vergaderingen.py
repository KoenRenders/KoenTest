"""CR-09 (#258) — de vergadermodule: agenda genereren, notuleren, versturen.

De invarianten die ertoe doen, en per stuk het scenario dat ze kan breken:

1. **De agenda splitst juist.** Evaluatie is wat sinds de vorige vergadering liep
   of startte (lopende activiteiten inbegrepen), volgende is alles wat daarna
   gepland staat. Loopt die grens fout, dan mist het bestuur ofwel de evaluatie
   van een activiteit ofwel een aankondiging.
2. **Chronologisch invoegen.** Een punt dat tijdens de vergadering wordt
   toegevoegd, schuift op zijn datum tússen de bestaande punten — niet onderaan.
3. **De bestandsgrendel.** Een bijlage van een verstuurde vergadering kan niet
   verwijderd worden. Bewezen door de overtreding echt te maken: versturen, dan
   proberen te verwijderen, en de benoemde weigering controleren.
4. **Fail-closed downloaden.** Een vergaderbestand is niet op te halen zonder
   beheersessie — dát is de reden dat deze bestanden geen media-assets zijn.
5. **Versturen.** Eén mail, iedereen in To, Reply-To naar wie verstuurt, de PDF
   als bijlage én gearchiveerd.
6. **Heropenen.** Opnieuw versturen bewaart een tweede PDF; de eerste blijft.
7. **De ledenkop** volgt de hernieuwingscyclus.

De tests draaien tegen een echte Postgres via de gewone fixtures; de e-mail gaat
door een dubbel, zodat er geen SMTP aan te pas komt.
"""
import base64
from datetime import date, time, timedelta

import pytest

from app.domains.activities.api import Activity, ActivityDate
from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for,
                                  make_session_value)
from app.domains.mdm.api import (ContactDetail, Organization, OrganizationPerson,
                                 Person)
from app.domains.meetings.api import (
    ATTENDANCE_PRESENT,
    FILE_SENT_PDF,
    MeetingError,
    add_file,
    add_item,
    create_meeting,
    delete_file,
    document_of,
    files_of,
    get_meeting,
    items_of,
    section_label,
    sections_of,
    send_meeting_mail,
    set_attendance,
)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


# ── Hulpstukken ──────────────────────────────────────────────────────────────

def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _activity(db, naam: str, start: date, eind: date | None = None,
              locatie: str = "Miloheem") -> Activity:
    activity = Activity(name=naam, location=locatie)
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=start, end_date=eind))
    db.flush()
    return activity


def _person(db, voornaam: str, achternaam: str, email: str | None = None) -> Person:
    person = Person(first_name=voornaam, last_name=achternaam)
    db.add(person)
    db.flush()
    if email:
        db.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL",
                             value=email))
        db.flush()
    return person


def _in_circle(db, person: Person) -> OrganizationPerson:
    organization = db.query(Organization).first()
    if organization is None:
        organization = Organization(name="Raak Millegem", code="raakmillegem")
        db.add(organization)
        db.flush()
    relation = OrganizationPerson(person_id=person.id,
                                  organization_id=organization.id,
                                  relation_type="BOARD_MEETING",
                                  start_date=date(2020, 1, 1))
    db.add(relation)
    db.flush()
    return relation


class _Mailbox:
    """Een dubbel voor `send_with_attachments` dat onthoudt wat er zou vertrekken."""

    def __init__(self):
        self.sent = []

    def __call__(self, **kwargs):
        self.sent.append(kwargs)


@pytest.fixture
def mailbox(monkeypatch):
    box = _Mailbox()
    monkeypatch.setattr("app.domains.mail.api.send_with_attachments", box)
    monkeypatch.setattr("app.domains.mail.service.send_with_attachments", box,
                        raising=False)
    return box


# ── 1. De agenda splitst juist ───────────────────────────────────────────────

def test_de_agenda_scheidt_evaluatie_van_wat_komt(db_session):
    """Lopend telt als evaluatie, toekomstig als 'volgende' — de grens is de
    vergaderdatum, met de vorige vergadering als achterwand.

    Wat dit zou moeten vangen: een grens op `>=` in plaats van `>` laat een
    activiteit in twee secties tegelijk staan, of in geen enkele.
    """
    vandaag = date(2026, 10, 1)
    vorige = create_meeting(db_session, meeting_date=date(2026, 9, 3))
    vorige.report_sent_at = vorige.created_at
    db_session.flush()

    _activity(db_session, "Comedy Festival", date(2026, 9, 11))
    _activity(db_session, "Fotozoektocht", date(2026, 6, 1), date(2026, 9, 30))
    _activity(db_session, "Rumproefavond", date(2026, 10, 2))
    _activity(db_session, "Kerstherberg", date(2026, 12, 25))
    _activity(db_session, "Wandeling lang geleden", date(2026, 5, 4))

    meeting = create_meeting(db_session, meeting_date=vandaag)
    secties = {s.kind: s for s in document_of(db_session, meeting)}

    evaluatie = [i.label for i in secties["EVALUATION"].items]
    volgende = [i.label for i in secties["UPCOMING"].items]

    assert "Comedy Festival" in evaluatie
    assert "Fotozoektocht" in evaluatie, "een lopende activiteit hoort bij de evaluatie"
    assert "Wandeling lang geleden" not in evaluatie, "van vóór de vorige vergadering"
    # De seed-migratie brengt eigen demo-activiteiten mee; wat hier bewezen moet
    # worden is de SCHEIDING en de VOLGORDE van onze drie, niet de hele lijst.
    assert "Rumproefavond" in volgende and "Kerstherberg" in volgende
    assert "Comedy Festival" not in volgende, "wat al geweest is, staat niet bij wat komt"
    assert volgende.index("Rumproefavond") < volgende.index("Kerstherberg")


def test_ideeen_gaan_mee_naar_de_volgende_agenda(db_session):
    """Wat onder Programma-ideeën staat, staat op de volgende agenda opnieuw —
    anders is de overdracht weer handwerk."""
    vorige = create_meeting(db_session, meeting_date=date(2026, 9, 3))
    ideeen = next(s for s in sections_of(db_session, vorige) if s.kind == "IDEAS")
    add_item(db_session, vorige, ideeen, title="Bezoek Molen Ezaart",
             notes="Koen en Wim bekijken het bakhuisje.")
    vorige.report_sent_at = vorige.created_at
    db_session.flush()

    volgende = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    sectie = next(s for s in document_of(db_session, volgende) if s.kind == "IDEAS")
    labels = [i.label for i in sectie.items]
    assert "Bezoek Molen Ezaart" in labels
    assert "bakhuisje" in sectie.items[0].notes


# ── 2. Chronologisch invoegen ────────────────────────────────────────────────

def test_een_punt_tijdens_de_vergadering_schuift_ertussen(db_session):
    """Koens geval: tijdens de vergadering blijkt een activiteit toch besproken te
    moeten worden. Ze hoort op haar datum te landen, niet onderaan.

    Zonder de sorteersleutel zou ze achteraan komen — en dan leest het verslag
    alsof ze na de kerstherberg valt.
    """
    _activity(db_session, "Rumproefavond", date(2026, 10, 2))
    _activity(db_session, "Kerstherberg", date(2026, 12, 25))
    tussendoor = _activity(db_session, "Bowlen", date(2026, 11, 15))

    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    sectie_model = next(s for s in sections_of(db_session, meeting)
                        if s.kind == "UPCOMING")
    # Haal 'Bowlen' er eerst af, zoals de secretaris zou doen die het punt niet
    # nodig achtte, en voeg het daarna tijdens de vergadering alsnog toe.
    for item in items_of(db_session, sectie_model):
        if item.activity_id == tussendoor.id:
            db_session.delete(item)
    db_session.flush()

    add_item(db_session, meeting, sectie_model, activity_id=tussendoor.id)

    sectie = next(s for s in document_of(db_session, meeting) if s.kind == "UPCOMING")
    labels = [i.label for i in sectie.items]
    assert labels.index("Rumproefavond") < labels.index("Bowlen") < labels.index("Kerstherberg"), \
        "het toegevoegde punt schuift op zijn datum ertussen, niet achteraan"


def test_een_vrij_punt_komt_achteraan_en_draagt_geen_bron(db_session):
    """Een vrij punt heeft geen datum en dus geen plaats in de reeks; het sluit
    aan. En het krijgt geen bron-chip, want er is geen bron om naartoe te gaan."""
    _activity(db_session, "Rumproefavond", date(2026, 10, 2))
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    sectie_model = next(s for s in sections_of(db_session, meeting)
                        if s.kind == "UPCOMING")
    add_item(db_session, meeting, sectie_model, title="Sofie Walk and Run")

    sectie = next(s for s in document_of(db_session, meeting) if s.kind == "UPCOMING")
    assert sectie.items[-1].label == "Sofie Walk and Run"
    assert sectie.items[-1].kind == "free"
    assert sectie.items[-1].source_url is None


# ── 3. De bestandsgrendel ────────────────────────────────────────────────────

def test_een_bijlage_van_een_verstuurde_vergadering_kan_niet_weg(db_session, mailbox,
                                                                 monkeypatch):
    """De overtreding wordt hier écht gemaakt: versturen, dan verwijderen.

    Kapotgemaakt om de test te toetsen: met de guard uitgeschakeld verdwijnt het
    bestand zonder melding — precies het scenario waarin een bestuurslid de mail
    opent en de bijlage niet meer kan opvragen.
    """
    monkeypatch.setattr("app.domains.meetings.service.send_with_attachments",
                        mailbox, raising=False)
    persoon = _person(db_session, "Mon", "Essers", "mon@example.org")
    _in_circle(db_session, persoon)
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    bijlage = add_file(db_session, meeting, filename="draaiboek.pdf",
                       content_type="application/pdf", data=b"%PDF-1.4 draaiboek")

    send_meeting_mail(db_session, meeting, kind="report", subject="Verslag",
                      body_html="Hoi", reply_to="secretaris@example.org",
                      pdf=b"%PDF-1.4 verslag", pdf_filename="verslag.pdf")

    with pytest.raises(MeetingError) as gevangen:
        delete_file(db_session, meeting, bijlage.id)
    assert "meegestuurd" in str(gevangen.value)
    assert any(f.id == bijlage.id for f in files_of(db_session, meeting))


def test_een_verstuurde_pdf_blijft_altijd_bewaard(db_session, mailbox, monkeypatch):
    """Ook vóór het versturen van het verslag: een gearchiveerde PDF is geschiedenis."""
    monkeypatch.setattr("app.domains.meetings.service.send_with_attachments",
                        mailbox, raising=False)
    persoon = _person(db_session, "Steven", "Paepen", "steven@example.org")
    _in_circle(db_session, persoon)
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    send_meeting_mail(db_session, meeting, kind="agenda", subject="Agenda",
                      body_html="Hallo", reply_to="secretaris@example.org",
                      pdf=b"%PDF-1.4 agenda", pdf_filename="agenda.pdf")

    pdf = files_of(db_session, meeting, purpose=FILE_SENT_PDF)[0]
    with pytest.raises(MeetingError):
        delete_file(db_session, meeting, pdf.id)


# ── 4. Fail-closed downloaden ────────────────────────────────────────────────

def test_een_vergaderbestand_is_niet_op_te_halen_zonder_sessie(client, db_session):
    """Dít is waarom vergaderbestanden geen media-assets zijn: media serveert
    publiek, hier bestaat geen publiek pad om te vergeten."""
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    bijlage = add_file(db_session, meeting, filename="gemeente.pdf",
                       content_type="application/pdf", data=b"%PDF-1.4 gemeente")

    client.cookies.clear()
    antwoord = client.get(
        f"/admin/vergaderingen/{meeting.id}/bestand/{bijlage.id}",
        follow_redirects=False)
    assert antwoord.status_code in (302, 303, 401, 403), antwoord.status_code

    _login(client)
    met_sessie = client.get(f"/admin/vergaderingen/{meeting.id}/bestand/{bijlage.id}")
    assert met_sessie.status_code == 200
    assert met_sessie.content == b"%PDF-1.4 gemeente"


# ── 5. Versturen ─────────────────────────────────────────────────────────────

def test_versturen_is_een_mail_met_iedereen_in_to(db_session, mailbox, monkeypatch):
    """Eén mail, de hele kring in To, Reply-To naar wie verstuurt, de PDF mee.

    De To-regel is een beslissing (§3.13) en geen toeval: de kring antwoordt
    elkaar. Zou dit ooit naar Bcc verschuiven, dan valt deze test om.
    """
    monkeypatch.setattr("app.domains.meetings.service.send_with_attachments",
                        mailbox, raising=False)
    _in_circle(db_session, _person(db_session, "Mon", "Essers", "mon@example.org"))
    _in_circle(db_session, _person(db_session, "Ivo", "Verwimp", "ivo@example.org"))
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    add_file(db_session, meeting, filename="draaiboek.pdf",
             content_type="application/pdf", data=b"%PDF-1.4 draaiboek")

    send_meeting_mail(db_session, meeting, kind="report", subject="Verslag 1 oktober",
                      body_html="Hoi allemaal", reply_to="secretaris@example.org",
                      pdf=b"%PDF-1.4 verslag", pdf_filename="verslag.pdf")

    assert len(mailbox.sent) == 1, "één mail, niet één per ontvanger"
    verzonden = mailbox.sent[0]
    assert set(verzonden["to_emails"]) == {"mon@example.org", "ivo@example.org"}
    assert verzonden["reply_to"] == "secretaris@example.org"
    namen = [naam for naam, _type, _data in verzonden["attachments"]]
    assert namen == ["verslag.pdf", "draaiboek.pdf"]

    ververst = get_meeting(db_session, meeting.id)
    assert ververst.report_sent_at is not None
    assert ververst.status == "sent"
    assert len(files_of(db_session, meeting, purpose=FILE_SENT_PDF)) == 1


def test_een_los_adres_gaat_mee_in_dezelfde_mail(db_session, mailbox, monkeypatch):
    """De gastspreker die één keer komt, wordt geen persoon (§3.15)."""
    from app.domains.meetings.api import add_extra_recipient

    monkeypatch.setattr("app.domains.meetings.service.send_with_attachments",
                        mailbox, raising=False)
    _in_circle(db_session, _person(db_session, "Mon", "Essers", "mon@example.org"))
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    add_extra_recipient(db_session, meeting, "gastspreker@example.org")

    send_meeting_mail(db_session, meeting, kind="agenda", subject="Agenda",
                      body_html="Hallo", reply_to="secretaris@example.org",
                      pdf=b"%PDF-1.4", pdf_filename="agenda.pdf")

    assert "gastspreker@example.org" in mailbox.sent[0]["to_emails"]


def test_zonder_ontvangers_vertrekt_er_niets(db_session, mailbox, monkeypatch):
    """Een lege kring is een fout om te melden, geen mail om te versturen."""
    monkeypatch.setattr("app.domains.meetings.service.send_with_attachments",
                        mailbox, raising=False)
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    with pytest.raises(MeetingError):
        send_meeting_mail(db_session, meeting, kind="agenda", subject="Agenda",
                          body_html="Hallo", reply_to="s@example.org",
                          pdf=b"%PDF", pdf_filename="agenda.pdf")
    assert mailbox.sent == []


# ── 6. Heropenen ─────────────────────────────────────────────────────────────

def test_heropenen_bewaart_de_eerste_pdf_naast_de_tweede(db_session, mailbox,
                                                         monkeypatch):
    """De correctie van de dag nadien mag de geschiedenis niet uitwissen."""
    from app.domains.meetings.api import reopen

    monkeypatch.setattr("app.domains.meetings.service.send_with_attachments",
                        mailbox, raising=False)
    _in_circle(db_session, _person(db_session, "Mon", "Essers", "mon@example.org"))
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    send_meeting_mail(db_session, meeting, kind="report", subject="Verslag",
                      body_html="v1", reply_to="s@example.org",
                      pdf=b"%PDF eerste", pdf_filename="verslag.pdf")

    reopen(db_session, meeting)
    assert meeting.status == "report"

    send_meeting_mail(db_session, meeting, kind="report", subject="Verslag (verbeterd)",
                      body_html="v2", reply_to="s@example.org",
                      pdf=b"%PDF tweede", pdf_filename="verslag.pdf")

    bewaard = [f.data for f in files_of(db_session, meeting, purpose=FILE_SENT_PDF)]
    assert b"%PDF eerste" in bewaard and b"%PDF tweede" in bewaard


def test_een_verstuurd_verslag_weigert_wijzigingen(db_session, mailbox, monkeypatch):
    """Het enige harde moment in de levensloop (§3.23)."""
    monkeypatch.setattr("app.domains.meetings.service.send_with_attachments",
                        mailbox, raising=False)
    persoon = _person(db_session, "Mon", "Essers", "mon@example.org")
    _in_circle(db_session, persoon)
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    send_meeting_mail(db_session, meeting, kind="report", subject="Verslag",
                      body_html="v1", reply_to="s@example.org",
                      pdf=b"%PDF", pdf_filename="verslag.pdf")

    with pytest.raises(MeetingError):
        set_attendance(db_session, meeting, person_id=persoon.id,
                       status=ATTENDANCE_PRESENT)


# ── 7. De ledenkop ───────────────────────────────────────────────────────────

def test_de_ledenkop_volgt_de_hernieuwingscyclus(db_session, monkeypatch):
    """Drie toestanden op één jaar (§3.20), met vaste datums zodat de test niet
    van de kalender afhangt."""
    from app.domains.meetings.api import member_standing

    monkeypatch.setattr("app.domains.membership.api.renewal_open",
                        lambda today=None: False)
    rustig = member_standing(db_session, today=date(2026, 6, 1))
    assert rustig.year == 2026 and rustig.renewal_running is False

    monkeypatch.setattr("app.domains.membership.api.renewal_open",
                        lambda today=None: True)
    monkeypatch.setattr("app.domains.membership.api.renewal_years",
                        lambda today=None: (2026, 2027))
    campagne = member_standing(db_session, today=date(2026, 10, 1))
    assert campagne.renewal_running is True
    assert campagne.renewal_year == 2027


# ── Het scherm ───────────────────────────────────────────────────────────────

def test_het_document_toont_de_secties_in_volgorde_met_varia_laatst(client, db_session):
    """Varia is altijd het laatste punt; een eigen sectie komt ervóór (§3.17)."""
    from app.domains.meetings.api import add_section

    _login(client)
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    add_section(db_session, meeting, "Jaarplanning 2027")

    labels = [section_label(s) for s in sections_of(db_session, meeting)]
    assert labels[-1] == "Varia"
    assert "Jaarplanning 2027" in labels
    assert labels.index("Jaarplanning 2027") == len(labels) - 2

    # Op het scherm toetsen we de KOPPEN en niet het kale woord: "Varia" staat ook
    # in de uitleg bij de knop ("komt vóór Varia"), en die zin zou de volgorde
    # verkeerd bewijzen.
    html = client.get(f"/admin/vergaderingen/{meeting.id}").text
    assert ">Jaarplanning 2027</h2>" in html
    assert html.index(">Jaarplanning 2027</h2>") < html.index(">Varia</h2>")


def test_de_activiteitregel_toont_inschrijvingen_en_geen_prijs(client, db_session):
    """Inschrijvingsaantallen staan op de regel (§3.22); prijzen niet (§3.21) —
    een activiteit kan er meerdere hebben, dus één prijsveld zou liegen."""
    from app.domains.activities.api import ActivitySubRegistration, Registration
    from decimal import Decimal

    _login(client)
    activiteit = _activity(db_session, "Rumproefavond", date(2026, 10, 2))
    onderdeel = ActivitySubRegistration(activity_id=activiteit.id, name="Deelname",
                                        price=Decimal("30.00"), max_participants=30,
                                        sort_order=1)
    db_session.add(onderdeel)
    db_session.flush()
    for i in range(3):
        db_session.add(Registration(activity_id=activiteit.id,
                                    component_id=onderdeel.id,
                                    registration_type="INDIVIDUAL",
                                    contact_name=f"Gast {i}",
                                    contact_email=f"gast{i}@example.org"))
    db_session.flush()

    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    html = client.get(f"/admin/vergaderingen/{meeting.id}").text

    assert "3/30 ingeschreven" in html
    assert "30,00" not in html and "€30" not in html


# ── 8. De PDF rendert echt ───────────────────────────────────────────────────

def test_de_pdf_wordt_echt_gerenderd(client, db_session):
    """Downloaden levert een échte PDF, niet een lege of een foutpagina.

    Deze test bestaat omdat de rest van de suite WeasyPrint nooit aanroept: de
    keten zou groen kunnen staan terwijl het Pango-systeempakket ontbreekt of de
    template ongeldige CSS draagt, en dan valt de eerste PDF pas om bij Koen.
    Hij toetst de héle weg: template → WeasyPrint → bytes met een PDF-header.
    """
    _login(client)
    _activity(db_session, "Comedy Festival", date(2026, 9, 11))
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))

    antwoord = client.get(f"/admin/vergaderingen/{meeting.id}/pdf")

    assert antwoord.status_code == 200
    assert antwoord.headers["content-type"] == "application/pdf"
    assert antwoord.content.startswith(b"%PDF-"), antwoord.content[:40]
    # Een lege PDF is ook een PDF: de omvang is het verschil tussen "gerenderd"
    # en "een leeg document teruggegeven".
    assert len(antwoord.content) > 2000, len(antwoord.content)


# ── 9. Geen dode formulieren ─────────────────────────────────────────────────

def test_elk_formulier_op_de_vergaderschermen_kan_ook_echt_verzenden():
    """Een formulier zonder verzendknop én zonder trigger is een dode knop.

    Dit is geen stijlregel maar een echte bug die hier gemaakt is: het
    bijlage-formulier had alleen een bestandsveld, dus je koos een bestand en er
    gebeurde niets — htmx verstuurt een formulier op `submit`, en zonder knop komt
    dat event nooit. De servertest zag niets: de route wérkte, ze werd alleen nooit
    aangeroepen.

    Kapotgemaakt om te toetsen: met de knop weer verwijderd valt deze test om op
    precies dat formulier.
    """
    import re
    from pathlib import Path

    map_ = Path(__file__).resolve().parents[1] / "app" / "domains" / "meetings" / "templates"
    dood = []
    for pad in sorted(map_.glob("*.html")):
        tekst = pad.read_text()
        for stuk in re.findall(r"<form\b.*?</form>", tekst, re.S):
            if "hx-post" not in stuk and "method=\"post\"" not in stuk:
                continue
            heeft_knop = 'type="submit"' in stuk or "btn_primary(" in stuk \
                or "btn_secondary(" in stuk or "btn_outline(" in stuk \
                or "action_bar(" in stuk
            heeft_trigger = "hx-trigger=" in stuk
            if not (heeft_knop or heeft_trigger):
                kop = " ".join(stuk.split())[:90]
                dood.append(f"{pad.name}: {kop}")
    assert not dood, ("Formulier zonder verzendknop of trigger:\n  " + "\n  ".join(dood))


# ── 10. Notuleren: zetten én terugnemen ──────────────────────────────────────

def test_een_genoteerde_wijkmeester_kan_ook_weer_leeg(db_session):
    """"Geen wijkmeester" kiezen moet de notitie wissen, niet genegeerd worden.

    Dit ging mis in de eerste versie: zetten en wissen liepen allebei door
    dezelfde `None`, dus de lege keuze deed niets en de verkeerde naam bleef in
    het verslag staan. Kapotgemaakt om te toetsen: met de wis-tak eruit blijft de
    tweede assert op de oude persoon staan.
    """
    from app.domains.meetings.api import set_noted_steward

    persoon = _person(db_session, "Ivo", "Verwimp")
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    sectie = next(s for s in sections_of(db_session, meeting) if s.kind == "MEMBERS")
    punt = add_item(db_session, meeting, sectie, title="Gezin Peeters – Van Dael")

    set_noted_steward(db_session, meeting, punt.id, persoon.id)
    assert db_session.get(type(punt), punt.id).noted_steward_person_id == persoon.id

    set_noted_steward(db_session, meeting, punt.id, None)
    assert db_session.get(type(punt), punt.id).noted_steward_person_id is None


def test_een_punt_zonder_activiteit_en_zonder_titel_wordt_geweigerd(db_session):
    """Anders staat er een regel "Punt" in het verslag waar niemand iets aan heeft."""
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    sectie = next(s for s in sections_of(db_session, meeting) if s.kind == "MISC")
    with pytest.raises(MeetingError):
        add_item(db_session, meeting, sectie, title="   ")


# ── 11. De kiezer volgt de sectie ────────────────────────────────────────────


def test_de_kiezer_biedt_onder_evaluatie_voorbije_activiteiten_aan(db_session):
    """Het gat dat Koen zag: onder Evaluatie bood de kiezer alleen toekomst aan,
    dus een voorbije activiteit die al in het systeem stond kon je niet toevoegen.

    Kapotgemaakt om te toetsen: met de sectie-tak eruit valt de eerste assert om —
    dan komt 'Comedy Festival' niet in de lijst voor.
    """
    from app.domains.meetings.api import addable_activities

    _activity(db_session, "Comedy Festival", date(2026, 9, 11))
    _activity(db_session, "Rumproefavond", date(2026, 10, 2))
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))

    # Haal beide punten van de agenda, zodat de kiezer ze weer mag aanbieden.
    for item in db_session.query(type(meeting).items.property.mapper.class_) \
            .filter_by(meeting_id=meeting.id).all():
        if item.activity_id:
            db_session.delete(item)
    db_session.flush()

    evaluatie = next(s for s in sections_of(db_session, meeting) if s.kind == "EVALUATION")
    volgende = next(s for s in sections_of(db_session, meeting) if s.kind == "UPCOMING")

    onder_evaluatie = [s.activity.name for s in
                       addable_activities(db_session, meeting, section_id=evaluatie.id)]
    onder_volgende = [s.activity.name for s in
                      addable_activities(db_session, meeting, section_id=volgende.id)]

    assert "Comedy Festival" in onder_evaluatie, "voorbij, dus hoort bij evaluatie"
    assert "Rumproefavond" not in onder_evaluatie, "dat komt nog"
    assert "Rumproefavond" in onder_volgende
    assert "Comedy Festival" not in onder_volgende


# ── 12. Een bijlage hoort niet altijd bij beide mails ────────────────────────

def test_een_bijlage_kan_bij_de_agenda_horen_en_niet_bij_het_verslag(db_session, mailbox,
                                                                     monkeypatch):
    """Koens geval: een draaiboek gaat met de agenda mee, een ander stuk met het
    verslag. Het model kon dat al; het scherm bood de keuze niet aan.

    Dit is het bewijs dat de keuze ook echt doorwerkt tot in de mail — een
    schakelaar die alleen het scherm kleurt, is geen keuze.
    """
    from app.domains.meetings.api import set_file_mailing

    monkeypatch.setattr("app.domains.meetings.service.send_with_attachments",
                        mailbox, raising=False)
    _in_circle(db_session, _person(db_session, "Mon", "Essers", "mon@example.org"))
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    draaiboek = add_file(db_session, meeting, filename="draaiboek.pdf",
                         content_type="application/pdf", data=b"%PDF draaiboek")
    gemeente = add_file(db_session, meeting, filename="gemeente.pdf",
                        content_type="application/pdf", data=b"%PDF gemeente")

    # Draaiboek alleen bij de agenda, het gemeentestuk alleen bij het verslag.
    set_file_mailing(db_session, meeting, draaiboek.id, mail="report")
    set_file_mailing(db_session, meeting, gemeente.id, mail="agenda")

    send_meeting_mail(db_session, meeting, kind="agenda", subject="Agenda",
                      body_html="Hallo", reply_to="s@example.org",
                      pdf=b"%PDF agenda", pdf_filename="agenda.pdf")
    bij_agenda = [naam for naam, _t, _d in mailbox.sent[-1]["attachments"]]
    assert bij_agenda == ["agenda.pdf", "draaiboek.pdf"]

    send_meeting_mail(db_session, meeting, kind="report", subject="Verslag",
                      body_html="Hoi", reply_to="s@example.org",
                      pdf=b"%PDF verslag", pdf_filename="verslag.pdf")
    bij_verslag = [naam for naam, _t, _d in mailbox.sent[-1]["attachments"]]
    assert bij_verslag == ["verslag.pdf", "gemeente.pdf"]


# ── 13. Het logo in de PDF-kop ───────────────────────────────────────────────

def test_de_pdf_gebruikt_het_verenigingslogo_als_dat_er_is(client, db_session):
    """Staat er een logo in de mediabibliotheek, dan staat dat in de kop.

    Als data-URI ingebed en niet als link: WeasyPrint haalt niets op, dus een
    verwijzing zou een lege plek opleveren. Zonder logo blijft het woordmerk
    staan — de kop mag nooit leeg zijn.
    """
    from app.domains.media.api import MediaAsset

    _login(client)
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))

    zonder = client.get(f"/admin/vergaderingen/{meeting.id}/pdf")
    assert zonder.status_code == 200 and zonder.content.startswith(b"%PDF-")

    # Een kleine echte PNG volstaat: het gaat om de weg van de bytes naar de PDF,
    # niet om het beeld.
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    db_session.add(MediaAsset(kind="tenant_logo", data=png, content_type="image/png",
                              byte_size=len(png)))
    db_session.flush()

    met = client.get(f"/admin/vergaderingen/{meeting.id}/pdf")
    assert met.status_code == 200 and met.content.startswith(b"%PDF-")
    assert len(met.content) != len(zonder.content), \
        "de PDF veranderde niet, dus het logo kwam er niet in"


# ── 14. Eén logo, twee afnemers ──────────────────────────────────────────────

def test_het_logo_verschijnt_ook_in_de_publieke_header(client, db_session):
    """Hetzelfde logo dat de PDF gebruikt, staat ook in de kop van de site.

    Dat is de reden dat het bij de media hoort en niet in de vergadermodule: de
    vereniging uploadt het één keer. Zonder logo blijft het woordmerk staan — de
    kop mag nooit leeg zijn, ook niet bij een verse tenant.
    """
    from app.domains.media.api import MediaAsset

    zonder = client.get("/").text
    assert 'aria-label="Raak"' in zonder, "zonder logo hoort het woordmerk er te staan"

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")
    logo = MediaAsset(kind="tenant_logo", data=png, content_type="image/png",
                      byte_size=len(png))
    db_session.add(logo)
    db_session.flush()

    met = client.get("/").text
    assert f"/api/v1/media/{logo.id}" in met, "de header pakte het logo niet op"
    assert 'aria-label="Raak"' not in met, "het woordmerk hoort dan te wijken"


# ── 15. Wanneer en waar, in onderwerp én tekst ───────────────────────────────

def test_onderwerp_en_tekst_dragen_uur_en_locatie(client, db_session):
    """Het bestuur schrijft "om 20u in Miloheem" — in de onderwerpregel en in de
    mail zelf. Eén hulpje voedt beide, zodat ze niet uiteen kunnen lopen.

    En een vergadering zonder uur of locatie mag niet "om None" tonen: dan valt
    het stuk gewoon weg.
    """
    _login(client)
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1),
                             start_time=time(20, 0), location="Miloheem — zaal 1")

    html = client.get(f"/admin/vergaderingen/{meeting.id}/verstuur?kind=verslag").text
    assert "om 20u" in html
    assert "Miloheem — zaal 1" in html
    # Twee keer: één keer in het onderwerp, één keer in de tekst.
    assert html.count("om 20u") >= 2, "uur hoort in onderwerp én tekst"

    kaal = create_meeting(db_session, meeting_date=date(2026, 11, 5))
    kaal.start_time = None
    kaal.location = None
    db_session.flush()
    html2 = client.get(f"/admin/vergaderingen/{kaal.id}/verstuur?kind=agenda").text
    assert "None" not in html2
    assert " om " not in html2.split("RAAK vergadering")[1][:60]


# ── 16. Een nieuwe mediasoort moet ook te uploaden zijn ──────────────────────

def test_elke_mediasoort_staat_in_de_keuzelijst_bij_uploaden(client, db_session):
    """Een soort die het filter kent maar het uploadscherm niet, is onbruikbaar.

    Precies wat hier misging: `tenant_logo` werd toegevoegd aan VALID_KINDS, het
    filter op de mediabibliotheek toonde hem, maar de keuzelijst bij "Uploaden"
    somde de soorten met de hand op — dus het logo was niet te uploaden. Koen
    merkte het op door het te proberen.

    Kapotgemaakt om te toetsen: met de lus weer vervangen door twee vaste
    `<option>`-regels valt deze test om op `tenant_logo`.
    """
    from app.domains.media.api import VALID_KINDS

    _login(client)
    html = client.get("/admin/media/nieuw").text
    ontbreekt = [k for k in VALID_KINDS if f'value="{k}"' not in html]
    assert not ontbreekt, f"niet te kiezen bij het uploaden: {sorted(ontbreekt)}"


# ── 17. Een vergadering verschuiven ──────────────────────────────────────────

def test_een_vergadering_verschuiven_stelt_de_agenda_opnieuw_samen(db_session):
    """Koens geval: de vergadering schuift een week op nadat ze al vastlag.

    Dan klopt de agenda niet meer — een activiteit die tussen de oude en de nieuwe
    datum valt, hoort ineens bij de evaluatie in plaats van bij wat komt. Wat
    iemand al getypt heeft, moet die verschuiving wél overleven: een datum
    corrigeren mag geen werk kosten.
    """
    from app.domains.meetings.api import update_meeting

    tussenin = _activity(db_session, "Rumproefavond", date(2026, 10, 5))
    _activity(db_session, "Bowlen", date(2026, 11, 15))
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1),
                             start_time=time(20, 0), location="Miloheem")

    secties = {s.kind: s for s in document_of(db_session, meeting)}
    assert "Rumproefavond" in [i.label for i in secties["UPCOMING"].items]

    # Typ iets op een punt, zodat we kunnen zien dat het blijft staan.
    punt = next(i for i in secties["UPCOMING"].items if i.label == "Bowlen")
    from app.domains.meetings.api import update_item
    update_item(db_session, meeting, punt.id, notes="Jo heeft het onder controle.")

    update_meeting(db_session, meeting, meeting_date=date(2026, 10, 8),
                   start_time=time(20, 30), location="Miloheem — zaal 2")

    assert meeting.meeting_date == date(2026, 10, 8)
    assert meeting.start_time == time(20, 30)
    assert meeting.location == "Miloheem — zaal 2"

    opnieuw = {s.kind: s for s in document_of(db_session, meeting)}
    evaluatie = [i.label for i in opnieuw["EVALUATION"].items]
    volgende = [i.label for i in opnieuw["UPCOMING"].items]
    assert "Rumproefavond" in evaluatie, "viel nu vóór de vergadering"
    assert "Rumproefavond" not in volgende

    bowlen = [i for i in opnieuw["UPCOMING"].items if i.label == "Bowlen"]
    assert len(bowlen) == 1, "geen dubbel punt na het opnieuw samenstellen"
    assert "onder controle" in bowlen[0].notes, "de notitie moet de verschuiving overleven"


def test_alleen_het_uur_wijzigen_raakt_de_agenda_niet(db_session):
    """Uur en locatie bepalen geen venster; die mogen de agenda niet omgooien."""
    from app.domains.meetings.api import update_meeting

    _activity(db_session, "Bowlen", date(2026, 11, 15))
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    voor = [i.label for s in document_of(db_session, meeting) for i in s.items]

    update_meeting(db_session, meeting, meeting_date=date(2026, 10, 1),
                   start_time=time(19, 30), location="Elders")

    na = [i.label for s in document_of(db_session, meeting) for i in s.items]
    assert voor == na


def test_een_verstuurde_vergadering_verschuift_niet_meer(db_session, mailbox, monkeypatch):
    """Na het versturen ligt het verslag vast; eerst heropenen."""
    from app.domains.meetings.api import update_meeting

    monkeypatch.setattr("app.domains.meetings.service.send_with_attachments",
                        mailbox, raising=False)
    _in_circle(db_session, _person(db_session, "Mon", "Essers", "mon@example.org"))
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    send_meeting_mail(db_session, meeting, kind="report", subject="Verslag",
                      body_html="v1", reply_to="s@example.org",
                      pdf=b"%PDF", pdf_filename="verslag.pdf")

    with pytest.raises(MeetingError):
        update_meeting(db_session, meeting, meeting_date=date(2026, 10, 8))


# ── 18. Een gast zit mee aan tafel ───────────────────────────────────────────

def test_een_gast_krijgt_de_mail_en_staat_in_de_aanwezigheid(db_session, mailbox,
                                                             monkeypatch):
    """Koens vraag: een los adres hoort in de agenda zelf, zodat je het ook op
    aanwezig of verontschuldigd kan zetten.

    Een gast wordt bewust geen persoon in de administratie, en hoort toch in het
    verslag: wie er was, was er. Deze test volgt beide paden — de mail én de
    aanwezigheidslijst — want een gast die wel post krijgt maar niet in het
    verslag staat, is het halve werk.
    """
    from app.domains.meetings.api import (add_extra_recipient, attendance_of,
                                          extra_recipients_of, set_attendance)

    monkeypatch.setattr("app.domains.meetings.service.send_with_attachments",
                        mailbox, raising=False)
    _in_circle(db_session, _person(db_session, "Mon", "Essers", "mon@example.org"))
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))

    add_extra_recipient(db_session, meeting, "spreker@example.org",
                        name="Alexander W.")
    gast = extra_recipients_of(db_session, meeting)[0]
    assert gast.name == "Alexander W."

    set_attendance(db_session, meeting, guest_id=gast.id,
                   status=ATTENDANCE_PRESENT)
    assert attendance_of(db_session, meeting) == {f"g{gast.id}": "present"}

    send_meeting_mail(db_session, meeting, kind="agenda", subject="Agenda",
                      body_html="Hallo", reply_to="s@example.org",
                      pdf=b"%PDF", pdf_filename="agenda.pdf")
    assert "spreker@example.org" in mailbox.sent[0]["to_emails"]


def test_een_aanwezigheidsrij_wijst_naar_precies_een_deelnemer(db_session):
    """Persoon óf gast, nooit allebei en nooit geen van beide.

    Een rij die naar allebei wijst is betekenisloos, en de databank weigert ze
    ook (CHECK in migratie 124). Hier wordt de servicelaag getoetst, zodat de
    fout een nette melding geeft in plaats van een databankfout.
    """
    from app.domains.meetings.api import set_attendance

    persoon = _person(db_session, "Mon", "Essers", "mon@example.org")
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))

    with pytest.raises(MeetingError):
        set_attendance(db_session, meeting, status=ATTENDANCE_PRESENT)
    with pytest.raises(MeetingError):
        set_attendance(db_session, meeting, person_id=persoon.id, guest_id=1,
                       status=ATTENDANCE_PRESENT)


# ── 19. Het uur in de PDF-kop ────────────────────────────────────────────────

def test_de_pdf_kop_draagt_het_beginuur(client, db_session):
    """De kop zei wanneer de vergadering was, maar niet hoe laat.

    Dezelfde opmaak als in de mail en op de activiteitregel — één functie, zodat
    er nooit ergens "20:00" komt te staan waar elders "20u" staat.
    """
    from app.domains.meetings.api import clock

    assert clock(time(20, 0)) == "20u"
    assert clock(time(20, 30)) == "20u30"
    assert clock(None) == ""

    _login(client)
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1),
                             start_time=time(20, 0), location="Miloheem")
    antwoord = client.get(f"/admin/vergaderingen/{meeting.id}/pdf")
    assert antwoord.status_code == 200 and antwoord.content.startswith(b"%PDF-")


# ── 20. De wijkmeester hoort in het verslag ──────────────────────────────────

def test_de_genoteerde_wijkmeester_staat_in_het_document(db_session):
    """Hij stond alleen op het scherm, als keuzelijst — dus niet in de PDF.

    Het echte verslag schrijft "Groenvinkstraat 8 → wijkmeester: Ivo Verwimp";
    zonder die regel is de notulering wel gemaakt maar nergens te lezen, en dan
    heeft ze geen enkel nut.
    """
    from app.domains.mdm.api import Member, MemberPerson
    from app.domains.meetings.api import set_noted_steward

    wijkmeester = _person(db_session, "Ivo", "Verwimp")
    # Een écht nieuw gezin, zodat de agenda het punt zelf genereert — dat is de
    # weg die in de praktijk gelopen wordt, en meteen een toets op die generatie.
    hoofdlid = _person(db_session, "An", "Peeters")
    gezin = Member()
    db_session.add(gezin)
    db_session.flush()
    db_session.add(MemberPerson(member_id=gezin.id, person_id=hoofdlid.id,
                                relation_type="HOOFDLID"))
    db_session.flush()

    meeting = create_meeting(db_session, meeting_date=date.today())
    sectie = next(s for s in document_of(db_session, meeting) if s.kind == "MEMBERS")
    assert sectie.items, "het nieuwe gezin hoort automatisch op de agenda te staan"
    punt = sectie.items[0]
    assert "An Peeters" in punt.label

    set_noted_steward(db_session, meeting, punt.id, wijkmeester.id)

    getoond = next(i for s in document_of(db_session, meeting) for i in s.items
                   if i.id == punt.id)
    assert getoond.steward_name == "Ivo Verwimp"


# ── 21. Wat op het scherm staat, hoort in het verslag ────────────────────────

def _pdf_tekst(inhoud: bytes) -> str:
    """De tekst uit een PDF, om te kunnen toetsen wat er écht op papier staat."""
    from io import BytesIO

    from pypdf import PdfReader

    return "\n".join(p.extract_text() or "" for p in PdfReader(BytesIO(inhoud)).pages)


def test_de_bijlagen_staan_in_het_verslag(client, db_session):
    """De PDF noemde nergens welke stukken er meegingen.

    Dezelfde vorm als de wijkmeester die alleen een keuzelijst was: het scherm kon
    iets wat er verderop niet uitkwam. Juist de PDF is wat een bestuurslid later
    terugleest — dan hoort er te staan wélke documenten erbij hoorden.

    Er wordt op de PDF-TEKST getoetst en niet op het view-model, want dat laatste
    zou ook groen staan met de regel weg uit de template.
    """
    from app.domains.meetings.api import set_file_mailing

    _login(client)
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    add_file(db_session, meeting, filename="draaiboek-kerstradio.pdf",
             content_type="application/pdf", data=b"%PDF draaiboek")
    alleen_agenda = add_file(db_session, meeting, filename="enkel-bij-de-agenda.pdf",
                             content_type="application/pdf", data=b"%PDF agenda")
    set_file_mailing(db_session, meeting, alleen_agenda.id, mail="report")

    verslag = client.get(f"/admin/vergaderingen/{meeting.id}/pdf?kind=verslag")
    assert verslag.status_code == 200
    tekst = _pdf_tekst(verslag.content)
    assert "draaiboek-kerstradio.pdf" in tekst
    assert "enkel-bij-de-agenda.pdf" not in tekst, \
        "een bijlage die niet met het verslag meegaat, hoort er ook niet in te staan"


def test_de_wijkmeester_staat_op_papier(client, db_session):
    """Niet alleen in het view-model: de PDF-tekst moet hem dragen.

    Toetsen op het view-model zou ook groen staan met de regel weg uit de
    template — precies de fout die de wijkmeester hier in de eerste plaats had.
    """
    from app.domains.mdm.api import Member, MemberPerson
    from app.domains.meetings.api import set_noted_steward

    _login(client)
    wijkmeester = _person(db_session, "Ivo", "Verwimp")
    hoofdlid = _person(db_session, "An", "Peeters")
    gezin = Member()
    db_session.add(gezin)
    db_session.flush()
    db_session.add(MemberPerson(member_id=gezin.id, person_id=hoofdlid.id,
                                relation_type="HOOFDLID"))
    db_session.flush()

    meeting = create_meeting(db_session, meeting_date=date.today())
    sectie = next(s for s in document_of(db_session, meeting) if s.kind == "MEMBERS")
    set_noted_steward(db_session, meeting, sectie.items[0].id, wijkmeester.id)

    tekst = _pdf_tekst(client.get(f"/admin/vergaderingen/{meeting.id}/pdf").content)
    assert "An Peeters" in tekst
    assert "wijkmeester: Ivo Verwimp" in tekst
    assert "nieuw lid" in tekst


def test_cursieve_tekst_krijgt_een_echte_cursieve_letter(client, db_session):
    """Cursief bleef rechtop staan: er was geen cursief letterbestand.

    WeasyPrint/Pango maakt géén schuine variant bij wanneer alleen een rechte
    letter bestaat — gemeten in een proefrender, niet aangenomen. Het gevolg was
    stil: de knop werkte, de tekst werd bewaard, en op papier zag je niets.

    Toetst daarom op de ingesloten lettertypes van de PDF en niet op de tekst:
    tekst blijft identiek of ze nu schuin staat of niet, dus een assertie daarop
    zou precies dit geval missen.
    """
    from io import BytesIO

    from pypdf import PdfReader

    _login(client)
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    sectie = next(s for s in sections_of(db_session, meeting) if s.kind == "MISC")
    from app.domains.meetings.api import update_item

    punt = add_item(db_session, meeting, sectie, title="Opmaak")
    update_item(db_session, meeting, punt.id, notes="<div><em>schuin</em></div>")

    inhoud = client.get(f"/admin/vergaderingen/{meeting.id}/pdf").content
    lezer = PdfReader(BytesIO(inhoud))
    namen = []
    for bladzijde in lezer.pages:
        bronnen = bladzijde.get("/Resources", {})
        for lettertype in (bronnen.get("/Font", {}) or {}).values():
            naam = str(lettertype.get_object().get("/BaseFont", ""))
            namen.append(naam)
    assert any("Italic" in n for n in namen), \
        f"geen cursief lettertype ingesloten; wel: {sorted(set(namen))}"


# ── 22. Iemand in de kring die geen lid is ───────────────────────────────────

def test_een_niet_lid_kan_in_de_vergaderkring(client, db_session):
    """De afdelingsondersteuner is geen lid en hoort toch aan tafel (CR-09 §3.2).

    Dat kon niet: élk pad naar een nieuwe persoon liep via een gezin, dus wie geen
    lid was bestond niet in de administratie — en kon dus ook niet in de kring.
    Het gat zat niet in de kring maar een laag dieper, in het aanmaken van een
    persoon.

    Toetst de hele weg: de persoon bestaat zonder gezin, staat in de kring, en
    krijgt de vergadermail.
    """
    from app.domains.mdm.api import MemberPerson, organization_circle
    from app.domains.meetings.api import recipients_for

    _login(client)
    organisatie = _organisatie(db_session)
    antwoord = client.post("/admin/vergaderingen/kring/nieuw", data={
        "csrf_token": _login(client), "first_name": "Lies",
        "last_name": "Ondersteuner", "person_email": "lies@raak-nationaal.example"},
        headers={"X-CSRF-Token": _login(client)})
    assert antwoord.status_code == 200, antwoord.text[:200]

    kring = organization_circle(db_session)
    erbij = [e for e in kring if e.person.last_name == "Ondersteuner"]
    assert len(erbij) == 1, "de nieuwe persoon staat niet in de kring"
    assert erbij[0].email == "lies@raak-nationaal.example"

    # En bewust zonder gezin: een niet-lid hoort in geen enkel gezin te belanden.
    koppelingen = (db_session.query(MemberPerson)
                   .filter(MemberPerson.person_id == erbij[0].person.id).all())
    assert koppelingen == [], "een niet-lid hoort aan geen enkel gezin te hangen"

    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))
    assert "lies@raak-nationaal.example" in recipients_for(db_session, meeting).emails


def _organisatie(db):
    """De organisatie waaraan de kring hangt; maak er een als ze ontbreekt."""
    from app.domains.mdm.api import Organization

    org = db.query(Organization).first()
    if org is None:
        org = Organization(name="Raak Millegem", code="raakmillegem")
        db.add(org)
        db.flush()
    return org


# ── 23. De lijst volgt de conventie van de andere lijstschermen ──────────────

def test_de_vergaderlijst_kan_gezocht_worden(client, db_session):
    """Zoeken op wat er STAAT, niet op wat er in de kolom zit.

    Een bestuurder typt "oktober", geen datum in ISO-notatie. Daarom filtert het
    scherm op het getoonde label; een test op de kolom zou die keuze niet vangen.
    """
    _login(client)
    oktober = create_meeting(db_session, meeting_date=date(2026, 10, 1),
                             location="Miloheem")
    november = create_meeting(db_session, meeting_date=date(2026, 11, 5),
                              location="Café Christiane")

    alles = client.get("/admin/vergaderingen").text
    assert "1 oktober 2026" in alles and "5 november 2026" in alles

    op_maand = client.get("/admin/vergaderingen?q=oktober").text
    assert "1 oktober 2026" in op_maand
    assert "5 november 2026" not in op_maand

    op_locatie = client.get("/admin/vergaderingen?q=christiane").text
    assert "5 november 2026" in op_locatie
    assert "1 oktober 2026" not in op_locatie


def test_zoeken_staat_boven_het_aanmaken_van_een_niet_lid(client, db_session):
    """De volgorde op het kringscherm is de volgorde van de handeling.

    Eerst kijken of de persoon al in de administratie staat — in verreweg de
    meeste gevallen is dat zo. Stond het aanmaakformulier bovenaan, dan maak je
    een tweede persoon aan voor iemand die er al was, en dat is niet terug te
    draaien zonder samenvoegen.
    """
    _login(client)
    html = client.get("/admin/vergaderingen/kring").text
    zoeken = html.index("Iemand toevoegen<")
    aanmaken = html.index("Iemand toevoegen die geen lid is")
    assert zoeken < aanmaken, "het aanmaakformulier hoort ONDER het zoeken te staan"


# ── 24. Iemand uit de kring halen ────────────────────────────────────────────

def test_wie_je_uit_de_kring_haalt_is_er_meteen_uit(db_session):
    """Verwijderen werkte niet: de einddatum was vandaag en het filter liet "tot
    en met vandaag" nog meetellen, dus de persoon bleef tot morgen staan.

    Kapotgemaakt om te toetsen: met `>=` in plaats van `>` staat hij er na het
    verwijderen nog steeds.
    """
    from app.domains.mdm.api import end_circle_relation, organization_circle

    persoon = _person(db_session, "Kris", "Vermeulen", "kris@example.org")
    relatie = _in_circle(db_session, persoon)
    assert any(e.person.id == persoon.id for e in organization_circle(db_session))

    end_circle_relation(db_session, relatie.id)

    assert not any(e.person.id == persoon.id for e in organization_circle(db_session)), \
        "wie je verwijdert, hoort meteen uit de kring te zijn"


def test_een_vertrokken_deelnemer_blijft_in_het_oude_verslag(client, db_session):
    """Wie er wás, blijft er staan — ook nadat hij de kring verlaten heeft.

    De kring is een momentopname. Zou het verslag alleen de huidige kring tonen,
    dan verdween zijn naam uit een oud verslag terwijl zijn aanwezigheid gewoon in
    de databank staat: het document klopt dan niet meer met die avond, en niemand
    die het leest kan dat zien.
    """
    from app.domains.mdm.api import end_circle_relation
    from app.domains.meetings.api import set_attendance

    _login(client)
    persoon = _person(db_session, "Kris", "Vermeulen", "kris@example.org")
    relatie = _in_circle(db_session, persoon)
    meeting = create_meeting(db_session, meeting_date=date.today())
    set_attendance(db_session, meeting, person_id=persoon.id,
                   status=ATTENDANCE_PRESENT)

    end_circle_relation(db_session, relatie.id)

    tekst = _pdf_tekst(client.get(f"/admin/vergaderingen/{meeting.id}/pdf").content)
    assert "Kris Vermeulen" in tekst, \
        "de aanwezigheid van die avond verdween uit het verslag"


# ── 25. Terug naar de lijst ──────────────────────────────────────────────────

def test_de_detailschermen_hebben_een_weg_terug(client, db_session):
    """Bovenaan een detailscherm staat "‹ Alle vergaderingen", zoals overal.

    Zonder die link is de enige weg terug de navigatiebalk links, en die brengt je
    naar hetzelfde scherm via een omweg — op elk ander detailscherm in de app
    staat de link er wél, dus het ontbreken valt juist op.
    """
    _login(client)
    meeting = create_meeting(db_session, meeting_date=date(2026, 10, 1))

    for pad in (f"/admin/vergaderingen/{meeting.id}", "/admin/vergaderingen/kring"):
        html = client.get(pad).text
        assert 'href="/admin/vergaderingen"' in html, f"geen weg terug op {pad}"
        assert "Alle vergaderingen" in html, f"geen weg terug op {pad}"
