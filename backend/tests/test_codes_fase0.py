"""Wat fase 0 van CR-12 moet bewijzen vóór het geldsdomein aangeraakt wordt (§B8).

De pilotlijst is `meetings.meeting_status`: drie codes, één scherm, één badge.
Klein genoeg dat een fout zichtbaar is, echt genoeg om de vier dingen te tonen
waar elke latere fase op steunt.

**De belangrijkste test hier is de round trip**, en de reden staat in §B10:
`sa.Enum` bewaart standaard de **membernaam**. Een kolom die tegen
`PaymentStatus` gedeclareerd wordt, zou dan `PAID` bevatten waar elke query,
export en rapportage `paid` verwacht — en er gaat niets stuk, niet bij het
schrijven en niet bij het lezen. De fout zit dan in de data, en dat is de dure
soort. `EnumColumn` bestaat om precies dat uit te sluiten, en deze test is het
bewijs dat hij het doet.
"""
from datetime import date

import pytest
from sqlalchemy import text

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.meetings.api import MEETING_STATUS, MeetingStatus, create_meeting
from app.i18n import current_locale
from app.kernel.codes import (
    CodeSeed,
    code_label,
    code_labels,
    registry,
    reset_label_cache,
    tone,
)
from tests.conftest import SEEDED_ADMIN_EMAIL

#: De Nederlandse woorden die de schermen tóónden vóór CR-12, letterlijk uit
#: `meetings/admin_ui.py:STATUS_LABELS` zoals dat er op 25 september 2026 stond.
#: §B8.5: latere fasen toetsen hiertegen dat de schermen dezelfde woorden tonen.
#: Verandert er hier één, dan is dat een beslissing en geen detail.
LABELS_VOOR_CR12 = {"agenda": "Agenda", "report": "Verslag (bezig)",
                    "sent": "Verslag verstuurd"}

#: De tonen zoals ze waren, om dezelfde reden.
TONEN_VOOR_CR12 = {"agenda": "blue", "report": "yellow", "sent": "green"}


@pytest.fixture(autouse=True)
def _schone_labelcache():
    """De cache leeft per proces; tests mogen elkaars taal niet erven."""
    reset_label_cache()
    yield
    reset_label_cache()


# ── §B8.3 De round trip ──────────────────────────────────────────────────────

def test_een_enum_lid_belandt_als_code_in_de_kolom(db_session):
    """Ruw uitgelezen staat er `sent` — niet `SENT`, niet `MeetingStatus.SENT`.

    Dit is de test die het stille datacorruptierisico afdekt. Zou de kolom tegen
    `sa.Enum(MeetingStatus)` gedeclareerd staan, dan zou hier `SENT` uitkomen en
    zou niets in de applicatie daarover klagen.
    """
    meeting = create_meeting(db_session, meeting_date=date(2026, 11, 3))
    meeting.status = MeetingStatus.SENT
    db_session.flush()

    ruw = db_session.execute(
        text("SELECT status FROM meetings.meetings WHERE id = :id"),
        {"id": meeting.id}).scalar_one()
    assert ruw == "sent"
    assert ruw != "SENT", "de membernaam is opgeslagen — EnumColumn doet zijn werk niet"
    assert "MeetingStatus" not in ruw


def test_een_code_in_de_kolom_leest_terug_als_het_lid(db_session):
    """De andere richting: wat er al stond, komt terug als lid en niet als string."""
    meeting = create_meeting(db_session, meeting_date=date(2026, 11, 4))
    db_session.execute(
        text("UPDATE meetings.meetings SET status = 'report' WHERE id = :id"),
        {"id": meeting.id})
    db_session.expire(meeting)

    assert meeting.status is MeetingStatus.REPORT
    assert meeting.status != "report", (
        "een gewone Enum hoort NIET gelijk te zijn aan zijn string — is hij dat "
        "wel, dan is het een `str, Enum` en blijft elke losse vergelijking stil waar")


def test_een_waarde_buiten_de_lijst_valt_op_bij_het_lezen(db_session):
    """Corrupte data geeft een melding met lijst en waarde, geen kale string.

    Een kale string zou ongelijk zijn aan élk lid — dezelfde stille fout, één
    laag hoger. Zo'n rij kan alleen ontstaan door een schrijver buiten de
    applicatie om, want de FK weigert hem; daarom is dit een uitzondering en
    geen weergavegeval. De test moet die FK dus eerst wegnemen om het geval
    überhaupt te kunnen maken — wat meteen toont dat de FK echt de eerste lijn
    is. De SAVEPOINT van de fixture zet hem na de test terug.
    """
    meeting = create_meeting(db_session, meeting_date=date(2026, 11, 5))
    db_session.execute(text(
        "ALTER TABLE meetings.meetings DROP CONSTRAINT fk_meetings_status_code"))
    db_session.execute(
        text("UPDATE meetings.meetings SET status = 'kwijt' WHERE id = :id"),
        {"id": meeting.id})
    db_session.expire(meeting)

    with pytest.raises(ValueError) as fout:
        _ = meeting.status
    assert "kwijt" in str(fout.value)
    assert "MeetingStatus" in str(fout.value)


# ── §B8.2 en AC1 De FK houdt ─────────────────────────────────────────────────

def test_de_databank_weigert_een_status_die_niet_bestaat(db_session):
    """AC1 op de pilotlijst: `payed` komt er niet in, ook niet via ruwe SQL."""
    from sqlalchemy.exc import IntegrityError

    meeting = create_meeting(db_session, meeting_date=date(2026, 11, 6))
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("UPDATE meetings.meetings SET status = 'verzonden' WHERE id = :id"),
            {"id": meeting.id})


# ── §B8.4 Eén label per code per taal ────────────────────────────────────────

def test_elke_actieve_code_van_elke_lijst_heeft_nl_en_en(db_session):
    """Precies één niet-lege tekst per taal, voor élke lijst in de registry."""
    for lijst in registry().values():
        for code, _label in code_labels(lijst.name, language="nl"):
            for taal in ("nl", "en"):
                tekst = code_label(lijst.name, code, language=taal)
                assert tekst and tekst != code, (
                    f"`{lijst.name}`.`{code}` heeft geen {taal}-label")


def test_de_pilotlijst_toont_dezelfde_nederlandse_woorden_als_voor_cr12(db_session):
    """§B8.5: het scherm mag van deze verhuizing niets merken."""
    for code, verwacht in LABELS_VOOR_CR12.items():
        assert code_label("meeting_status", code, language="nl") == verwacht


def test_de_engelse_labels_zijn_gezaaid(db_session):
    assert code_label("meeting_status", MeetingStatus.SENT, language="en") == \
        "Report sent"


def test_de_keuzelijst_komt_in_sort_order(db_session):
    """`sort_order` is de laatste plek waar een Python-lijst de volgorde koos.

    De drie codes staan hier alle drie actief, dus deze test toont de volgorde
    en niet de `is_active`-filter; die wordt getoetst waar er iets ingetrokken
    ís, in de intrektest hieronder.
    """
    assert [code for code, _ in code_labels("meeting_status", language="nl")] == \
        ["agenda", "report", "sent"]


def test_een_lid_mag_ook_rechtstreeks_in_de_labelfunctie(db_session):
    assert code_label("meeting_status", MeetingStatus.REPORT, language="nl") == \
        "Verslag (bezig)"


# ── §B4.4 De terugvallen ─────────────────────────────────────────────────────

def test_een_onbekende_taal_valt_terug_op_nederlands(db_session):
    assert code_label("meeting_status", "sent", language="de") == "Verslag verstuurd"


def test_een_onbekende_code_toont_zichzelf_en_wordt_een_keer_gelogd(db_session,
                                                                    caplog):
    """Onder `StrictUndefined` is leeg renderen erger dan de code tonen.

    Eén waarschuwing per (lijst, code) en niet per render: een lijstscherm met
    veertig rijen zou anders veertig identieke regels in de log zetten, en dan
    leest niemand de log nog.
    """
    import logging

    with caplog.at_level(logging.WARNING, logger="app.kernel.codes"):
        assert code_label("meeting_status", "bestaat-niet") == "bestaat-niet"
        assert code_label("meeting_status", "bestaat-niet") == "bestaat-niet"
    regels = [r for r in caplog.records if "bestaat-niet" in r.getMessage()]
    assert len(regels) == 1, f"{len(regels)} waarschuwingen in plaats van één"


def test_de_actieve_taal_komt_uit_de_locale(db_session):
    """`nl_BE` → `nl`: de instelling is een locale, de labelsleutel een taal (§F8)."""
    teken = current_locale.set("en_GB")
    try:
        assert code_label("meeting_status", "sent") == "Report sent"
    finally:
        current_locale.reset(teken)


# ── §B4.5 De tonen ───────────────────────────────────────────────────────────

def test_de_tonen_zijn_die_van_voor_cr12():
    import app.main  # noqa: F401  — laadt de UI-module die ze registreert

    for code, verwacht in TONEN_VOOR_CR12.items():
        assert tone("meeting_status", code) == verwacht


# ── §B8.6 Het scherm rendert tekst ───────────────────────────────────────────

def _login(client) -> dict:
    waarde = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, waarde)
    return {"X-CSRF-Token": csrf_token_for(waarde)}


def test_het_vergaderscherm_toont_het_label_en_niet_de_code(client, db_session):
    """Door het échte view-model, in de `StrictUndefined`-omgeving.

    De badge kwam vóór CR-12 uit een woordenboek in `admin_ui.py`; nu uit de
    labeltabel via het Jinja-filter. Het scherm hoort identiek te lezen — dat is
    precies wat Koen op HDEV valideert.
    """
    create_meeting(db_session, meeting_date=date(2026, 11, 7))
    db_session.commit()
    _login(client)

    antwoord = client.get("/admin/vergaderingen")
    assert antwoord.status_code == 200
    tekst = antwoord.text
    assert "Agenda" in tekst
    assert "MeetingStatus" not in tekst, "de membernaam lekt naar het scherm"


# ── De migratiehelper ────────────────────────────────────────────────────────

def test_de_helper_weigert_een_fk_op_data_die_niet_past(db_session):
    """De wacht vóór de FK noemt de waarde én het aantal.

    Bewezen door overtreding: één rij met een waarde buiten de lijst, en de
    helper hoort af te breken vóór hij de FK zet — met het getal in de melding,
    zodat de lezer weet of het om één rij gaat of om vijftien. Dat is de vorm
    waar fase 1 op steunt (§B4.6), dus hij wordt hier gemeten en niet daar.
    """
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    from app.kernel.codes import create_code_list

    db_session.execute(text(
        "CREATE TABLE meetings.proef (id serial PRIMARY KEY, soort_code varchar(10))"))
    db_session.execute(text(
        "INSERT INTO meetings.proef (soort_code) VALUES ('een'), ('kwijt'), ('kwijt')"))
    op = Operations(MigrationContext.configure(db_session.connection()))

    with pytest.raises(RuntimeError) as fout:
        create_code_list(op, schema="meetings", name="proef_soort",
                         codes=(CodeSeed(code="een", nl="Een", en="One"),),
                         fk_from=("meetings.proef.soort_code",), code_length=10)
    melding = str(fout.value)
    assert "'kwijt'×2" in melding
    assert "meetings.proef.soort_code" in melding


def test_intrekken_verwijdert_niets_en_houdt_de_fk_geldig(db_session):
    """`retire_code` zet `is_active` uit — een delete zou de history breken.

    Fase 2 trekt gender `U`/`O` in, en fase 2 is niet de plek om te ontdekken
    dat deze helper nooit gedraaid heeft. De invarianten: de rij blijft bestaan
    (de FK van bestaande rijen blijft geldig), ze telt niet meer mee als actief,
    het lid blijft in de enum en het label blijft leesbaar — anders zou een oude
    vergadering haar status ineens niet meer kunnen tonen.

    **Wat deze test bewust NIET door `code_labels()` heen meet.** De labelcache
    leest via een sessie die de kernel zelf opent (§B2.4), dus een intrekking
    die in de testtransactie staat en nog niet gecommit is, ziet hij niet. Dat
    is geen tekortkoming van de helper maar de opzet van de cache: labels
    wijzigen enkel door een migratie, en die is gecommit vóór er iets rendert.
    De filtering op `is_active` wordt daarom hier op de tabel zelf getoetst.
    """
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    from app.kernel.codes import retire_code

    meeting = create_meeting(db_session, meeting_date=date(2026, 11, 8))
    meeting.status = MeetingStatus.SENT
    db_session.flush()
    op = Operations(MigrationContext.configure(db_session.connection()))

    retire_code(op, schema="meetings", name="meeting_status", code="sent",
                used_by=("meetings.meetings.status",))

    rij = db_session.execute(text(
        "SELECT is_active FROM meetings.meeting_status_codes WHERE code = 'sent'"
    )).all()
    assert rij == [(False,)], "een ingetrokken code mag niet verdwijnen, wel uit"
    assert db_session.execute(text(
        "SELECT code FROM meetings.meeting_status_codes WHERE is_active "
        "ORDER BY sort_order")).scalars().all() == ["agenda", "report"]
    assert db_session.execute(text(
        "SELECT value FROM meetings.meeting_status_labels "
        "WHERE code = 'sent' AND language = 'nl'")).scalar_one() == \
        "Verslag verstuurd"
    assert MeetingStatus.SENT in list(MeetingStatus), (
        "het lid blijft bestaan, anders leest deze rij terug als een kale string")
    db_session.expire(meeting)
    assert meeting.status is MeetingStatus.SENT


def test_de_lijst_van_de_pilot_staat_in_de_registry():
    assert registry()["meeting_status"] is MEETING_STATUS
    assert MEETING_STATUS.enum is MeetingStatus
    assert MEETING_STATUS.codes_table == "meetings.meeting_status_codes"
