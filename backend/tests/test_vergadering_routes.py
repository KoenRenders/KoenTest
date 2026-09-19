"""De vergadermodule langs de ROUTES, niet langs de servicelaag (#939).

`test_vergaderingen.py` toetst de regels: wat een agenda hoort te bevatten, wat
een grendel weigert, wat er in de PDF staat. Het roept daarvoor de service aan.
Gemeten op 16 september 2026 bleek wat dat níét dekt: van de 28 routes werden er
negen aangeroepen, en van de negentien POST-routes precies één.

Dat gat is niet theoretisch. De twee fouten die Koen bij het testen vond, zaten
allebei in die niet-geraakte laag: een uploadformulier zonder verzendknop (de
route werkte, ze werd nooit aangeroepen) en een adres dat na het aanmaken niet
meeverhuisde. Een servicetest kan geen van beide zien.

Dit bestand loopt daarom de weg van een secretaris, via HTTP, met CSRF en al:
kring → vergadering → notuleren → bijlagen → versturen → heropenen. Eén lange
doorloop plus een paar gerichte tests op de punten waar een fout geld of
geloofwaardigheid kost.
"""
from datetime import date, time

import pytest

from app.domains.activities.api import Activity, ActivityDate
from app.domains.auth.api import (SESSION_COOKIE, csrf_token_for,
                                  make_session_value)
from app.domains.mdm.api import ContactDetail, Organization, OrganizationPerson, Person
from app.domains.meetings.api import (FILE_SENT_PDF, attendance_of, document_of,
                                      extra_recipients_of, files_of, get_meeting,
                                      sections_of)
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client) -> dict:
    """Meld aan en geef de headers die elke schrijfactie nodig heeft."""
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return {"X-CSRF-Token": csrf_token_for(waarde)}


def _kringlid(db, voornaam="Mon", achternaam="Essers", email="mon@example.org"):
    organisatie = db.query(Organization).first()
    if organisatie is None:
        organisatie = Organization(name="Raak Millegem", code="raakmillegem")
        db.add(organisatie)
        db.flush()
    person = Person(first_name=voornaam, last_name=achternaam)
    db.add(person)
    db.flush()
    db.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL", value=email))
    db.add(OrganizationPerson(person_id=person.id, organization_id=organisatie.id,
                              relation_type="BOARD_MEETING",
                              start_date=date(2020, 1, 1)))
    db.flush()
    return person


def _activiteit(db, naam, dag, uur=None, locatie="Miloheem"):
    activity = Activity(name=naam, location=locatie)
    db.add(activity)
    db.flush()
    db.add(ActivityDate(activity_id=activity.id, start_date=dag, start_time=uur))
    db.flush()
    return activity


@pytest.fixture
def postbus(monkeypatch):
    """Een dubbel voor het versturen: geen SMTP, wel zien wat er zou vertrekken.

    Het aanhechtingspunt is `app.domains.mail.api` en NIET de vergaderservice:
    die importeert de functie pas binnen de aanroep, dus een dubbel dat op de
    service geplakt wordt, wordt nooit gebruikt. Met `raising=False` erbij faalt
    zo'n vergissing ook niet — de test kijkt dan naar een lijst die per definitie
    leeg blijft. Gemeten: op het verkeerde punt geplakt loopt de doorloop
    helemaal uit, en meldt hij "er vertrok geen mail" terwijl de mail vertrok.
    """
    verzonden = []
    monkeypatch.setattr("app.domains.mail.api.send_with_attachments",
                        lambda **kw: verzonden.append(kw))
    return verzonden


def test_de_hele_weg_van_een_secretaris(client, db_session, postbus):
    """Kring → vergadering → notuleren → bijlage → agenda → verslag → heropenen.

    Eén doorloop in plaats van tien losse tests, omdat het de VOLGORDE is die
    breekt: elke stap werkt op wat de vorige achterliet. Faalt hij, dan zegt de
    stap waarop hij staat meteen wáár het misging.
    """
    headers = _login(client)
    _kringlid(db_session)
    _activiteit(db_session, "Comedy Festival", date(2026, 9, 11), time(20, 0))
    _activiteit(db_session, "Rumproefavond", date(2026, 10, 2), time(20, 0))
    # Ver genoeg vooruit om buiten de agendeerhorizon van drie maanden te vallen:
    # zo staat ze er niet vanzelf op en kan de kiezer haar alsnog toevoegen.
    _activiteit(db_session, "Zomerkamp", date(2027, 6, 20), time(10, 0))

    # 1. Een vergadering aanmaken — de agenda komt er meteen bij.
    aangemaakt = client.post("/admin/vergaderingen", headers=headers, data={
        "meeting_date": "2026-10-01", "start_time": "20:00",
        "location": "Miloheem — zaal 1"}, follow_redirects=False)
    assert aangemaakt.status_code in (200, 204, 303), aangemaakt.text[:200]
    meeting = _laatste_vergadering(db_session)
    assert meeting.location == "Miloheem — zaal 1"
    assert meeting.start_time == time(20, 0)

    secties = {s.kind: s for s in document_of(db_session, meeting)}
    assert "Comedy Festival" in [i.label for i in secties["EVALUATION"].items]
    assert "Rumproefavond" in [i.label for i in secties["UPCOMING"].items]

    # 2. Een gast uitnodigen — hij komt in de aanwezigheidslijst én bij de mail.
    client.post(f"/admin/vergaderingen/{meeting.id}/gast", headers=headers,
                data={"guest_name": "Alexander W.", "guest_email": "gast@example.org"})
    gasten = extra_recipients_of(db_session, meeting)
    assert [g.name for g in gasten] == ["Alexander W."]

    # 3. Aanwezigheid: één klik is aanwezig, twee is verontschuldigd.
    persoon = db_session.query(Person).filter(Person.last_name == "Essers").first()
    client.post(f"/admin/vergaderingen/{meeting.id}/aanwezigheid", headers=headers,
                data={"person_id": str(persoon.id), "current": ""})
    assert attendance_of(db_session, meeting) == {f"p{persoon.id}": "present"}
    client.post(f"/admin/vergaderingen/{meeting.id}/aanwezigheid", headers=headers,
                data={"person_id": str(persoon.id), "current": "present"})
    assert attendance_of(db_session, meeting) == {f"p{persoon.id}": "excused"}
    client.post(f"/admin/vergaderingen/{meeting.id}/aanwezigheid", headers=headers,
                data={"guest_id": str(gasten[0].id), "current": ""})
    assert attendance_of(db_session, meeting)[f"g{gasten[0].id}"] == "present"

    # 4. Notuleren op een bestaand punt.
    punt = secties["EVALUATION"].items[0]
    client.post(f"/admin/vergaderingen/{meeting.id}/punt/{punt.id}", headers=headers,
                data={"notes": "<div>Uitverkocht, 300 tickets.</div>"})
    opnieuw = next(i for s in document_of(db_session, meeting) for i in s.items
                   if i.id == punt.id)
    assert "300 tickets" in opnieuw.notes

    # 5. Een eigen sectie, en daarin een vrij punt.
    client.post(f"/admin/vergaderingen/{meeting.id}/sectie", headers=headers,
                data={"title": "Jaarplanning 2027"})
    eigen = next(s for s in sections_of(db_session, meeting)
                 if s.title == "Jaarplanning 2027")
    labels = [s.kind for s in sections_of(db_session, meeting)]
    assert labels[-1] == "MISC", "Varia hoort het laatste te blijven"
    client.post(f"/admin/vergaderingen/{meeting.id}/punt", headers=headers,
                data={"section_id": str(eigen.id), "title": "Kalender vastleggen"})
    getoond = next(s for s in document_of(db_session, meeting) if s.id == eigen.id)
    assert [i.label for i in getoond.items] == ["Kalender vastleggen"]

    # 6. Een activiteit van buiten de horizon alsnog agenderen.
    upcoming = next(s for s in sections_of(db_session, meeting) if s.kind == "UPCOMING")
    vooraf = [i.label for i in next(s for s in document_of(db_session, meeting)
                                    if s.kind == "UPCOMING").items]
    assert "Zomerkamp" not in vooraf, "juni 2027 valt buiten de drie maanden"
    kerst = db_session.query(Activity).filter(Activity.name == "Zomerkamp").first()
    client.post(f"/admin/vergaderingen/{meeting.id}/punt", headers=headers,
                data={"section_id": str(upcoming.id), "activity_id": str(kerst.id)})
    na = next(s for s in document_of(db_session, meeting) if s.kind == "UPCOMING")
    assert [i.label for i in na.items].count("Zomerkamp") == 1

    # En een tweede keer toevoegen levert geen dubbel punt op.
    nogmaals = client.post(f"/admin/vergaderingen/{meeting.id}/punt", headers=headers,
                           data={"section_id": str(upcoming.id),
                                 "activity_id": str(kerst.id)})
    assert "staat al" in nogmaals.text
    na = next(s for s in document_of(db_session, meeting) if s.kind == "UPCOMING")
    assert [i.label for i in na.items].count("Zomerkamp") == 1

    # 7. Een bijlage uploaden — via multipart, zoals het formulier het doet.
    client.post(f"/admin/vergaderingen/{meeting.id}/bijlage", headers=headers,
                files={"file": ("draaiboek.pdf", b"%PDF-1.4 draaiboek", "application/pdf")},
                data={"csrf_token": "x"})
    bijlagen = files_of(db_session, meeting)
    assert [f.filename for f in bijlagen] == ["draaiboek.pdf"]

    # 8. De agenda versturen: één mail, de kring plus de gast, de PDF erbij.
    verstuurd = client.post(f"/admin/vergaderingen/{meeting.id}/verstuur",
                            headers=headers, follow_redirects=False,
                            data={"kind": "agenda", "subject": "Agenda 1 oktober",
                                  "body": "Hallo allemaal"})
    assert verstuurd.status_code in (200, 204, 303), verstuurd.text[:300]
    assert len(postbus) == 1, "er vertrok geen mail"
    assert set(postbus[0]["to_emails"]) == {"mon@example.org", "gast@example.org"}
    namen = [naam for naam, _t, _d in postbus[0]["attachments"]]
    assert namen[0].startswith("agenda-") and "draaiboek.pdf" in namen
    assert get_meeting(db_session, meeting.id).agenda_sent_at is not None

    # 9. Een tweede bijlage die alleen bij het verslag hoort.
    client.post(f"/admin/vergaderingen/{meeting.id}/bijlage", headers=headers,
                files={"file": ("gemeente.pdf", b"%PDF-1.4 gemeente", "application/pdf")})
    gemeente = next(f for f in files_of(db_session, meeting)
                    if f.filename == "gemeente.pdf")
    client.post(f"/admin/vergaderingen/{meeting.id}/bijlage/{gemeente.id}/meesturen",
                headers=headers, data={"mail": "agenda"})
    assert not next(f for f in files_of(db_session, meeting)
                    if f.id == gemeente.id).on_agenda_mail

    # 10. Het verslag versturen, met die extra bijlage erbij.
    client.post(f"/admin/vergaderingen/{meeting.id}/verstuur", headers=headers,
                follow_redirects=False,
                data={"kind": "report", "subject": "Verslag 1 oktober",
                      "body": "Hoi allemaal"})
    assert len(postbus) == 2
    namen = [naam for naam, _t, _d in postbus[1]["attachments"]]
    assert namen[0].startswith("verslag-")
    assert "gemeente.pdf" in namen and "draaiboek.pdf" in namen
    ververst = get_meeting(db_session, meeting.id)
    assert ververst.report_sent_at is not None and ververst.status == "sent"
    assert len(files_of(db_session, meeting, purpose=FILE_SENT_PDF)) == 2

    # 11. Een verstuurd verslag ligt vast — tot je het heropent.
    geweigerd = client.post(f"/admin/vergaderingen/{meeting.id}/punt/{punt.id}",
                            headers=headers, data={"notes": "<div>nog iets</div>"})
    assert "verstuurd" in geweigerd.text.lower()
    client.post(f"/admin/vergaderingen/{meeting.id}/heropen", headers=headers)
    assert get_meeting(db_session, meeting.id).status == "report"
    client.post(f"/admin/vergaderingen/{meeting.id}/punt/{punt.id}", headers=headers,
                data={"notes": "<div>correctie achteraf</div>"})
    hersteld = next(i for s in document_of(db_session, meeting) for i in s.items
                    if i.id == punt.id)
    assert "correctie achteraf" in hersteld.notes


def _laatste_vergadering(db):
    from app.domains.meetings.api import Meeting

    return db.query(Meeting).order_by(Meeting.id.desc()).first()


def test_versturen_zonder_csrf_token_gaat_niet(client, db_session):
    """De verzendknop is de enige onomkeerbare handeling in deze module.

    Een POST zonder token hoort te weigeren — en dat is het soort regel dat je
    juist wil toetsen op de route, want de servicelaag weet niets van CSRF.
    """
    # #1024: de headers van `_login` hergebruiken, niet een TWEEDE sessiewaarde
    # munten. `make_session_value()` draagt `int(time.time())`, dus viel die tweede
    # munting in een andere seconde dan de cookie, dan hoorde het token bij een
    # andere sessie en weigerde de AANMAAK al met 403 — vóór het onderwerp van deze
    # test aan bod kwam. Een test die willekeurig rood wordt, leert iedereen rood
    # te negeren.
    headers = _login(client)
    _kringlid(db_session)
    vergadering = client.post("/admin/vergaderingen", headers=headers,
                              data={"meeting_date": "2026-10-01"},
                              follow_redirects=False)
    assert vergadering.status_code in (200, 204, 303)
    meeting = _laatste_vergadering(db_session)

    zonder = client.post(f"/admin/vergaderingen/{meeting.id}/verstuur",
                         data={"kind": "report", "subject": "x", "body": "y"})
    assert zonder.status_code == 403, "versturen zonder token hoort te weigeren"
    assert get_meeting(db_session, meeting.id).report_sent_at is None


def test_datum_verschuiven_via_het_scherm(client, db_session):
    """Een vergadering een week opschuiven — de route, niet de service.

    De route zet de datum om uit een formulierveld; een typefout daarin is in de
    servicetest onzichtbaar omdat die al een `date` doorgeeft.
    """
    headers = _login(client)
    _activiteit(db_session, "Rumproefavond", date(2026, 10, 5), time(20, 0))
    client.post("/admin/vergaderingen", headers=headers,
                data={"meeting_date": "2026-10-01"}, follow_redirects=False)
    meeting = _laatste_vergadering(db_session)
    assert "Rumproefavond" in [i.label for s in document_of(db_session, meeting)
                               for i in s.items if s.kind == "UPCOMING"]

    client.post(f"/admin/vergaderingen/{meeting.id}/bewerken", headers=headers,
                follow_redirects=False,
                data={"meeting_date": "2026-10-08", "start_time": "20:30",
                      "location": "Miloheem — zaal 2"})

    ververst = get_meeting(db_session, meeting.id)
    assert ververst.meeting_date == date(2026, 10, 8)
    assert ververst.start_time == time(20, 30)
    assert "Rumproefavond" in [i.label for s in document_of(db_session, ververst)
                               for i in s.items if s.kind == "EVALUATION"], \
        "de activiteit valt nu vóór de vergadering en hoort bij de evaluatie"
