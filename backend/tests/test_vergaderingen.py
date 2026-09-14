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
    assert "verstuurd" in str(gevangen.value)
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
        set_attendance(db_session, meeting, persoon.id, ATTENDANCE_PRESENT)


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
