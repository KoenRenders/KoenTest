"""Formulierdefinitie en inzendervalidatie in de service (#635 D).

Twee regels stonden meervoudig, en de kopieën waren niet gelijk:

- `update_form` schreef tien instellingen, `json_import` maar drie. Een
  JSON-import verloor daardoor stilzwijgend zeven velden.
- De inzendervalidatie stond in de router (met de docstring "servicelaag-
  invariant, zodat élke ingang 'm afdwingt") én inline in de twee publieke
  schermen — terwijl de API-ingang `submit_bericht` hem helemaal niet aanriep.

Nu één functie per regel, hier rechtstreeks getoetst.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.domains.forms.service import assert_submitter, update_settings

pytestmark = pytest.mark.ui_agnostisch


class _Form:
    """Minimaal formulierobject: alleen attributen, geen sessie."""

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)


def _payload(**kw):
    velden = dict(title="Titel", slug="slug", description="", status="draft",
                  requires_login=True, max_submissions=25, send_confirmation=True,
                  confirmation_message="Bedankt", allow_edit=True, is_anonymous=True)
    velden.update(kw)
    return SimpleNamespace(**velden)


# ── Instellingen ─────────────────────────────────────────────────────────────

def test_alle_instellingen_worden_geschreven():
    """De zeven velden die json_image liet vallen (#635-3)."""
    form = _Form(title="", slug="", description="", status="", requires_login=False,
                 max_submissions=None, send_confirmation=False,
                 confirmation_message=None, allow_edit=False, is_anonymous=False)

    update_settings(form, _payload())

    assert form.requires_login is True
    assert form.max_submissions == 25
    assert form.send_confirmation is True
    assert form.confirmation_message == "Bedankt"
    assert form.allow_edit is True
    assert form.is_anonymous is True
    assert form.slug == "slug"


def test_een_ontbrekend_veld_in_de_payload_wordt_niet_aangeraakt():
    """`FormUpdate` heeft defaults; wat de payload niet draagt, bepaalt de
    aanroeper — niet deze functie."""
    form = _Form(title="Oud", slug="oud")
    update_settings(form, SimpleNamespace(title="Nieuw"))

    assert form.title == "Nieuw"
    assert form.slug == "oud"


# ── Inzender ─────────────────────────────────────────────────────────────────

def test_een_anoniem_formulier_vraagt_geen_naam():
    assert_submitter(_Form(is_anonymous=True), "", "")     # geen fout


def test_een_niet_anoniem_formulier_eist_naam_en_adres():
    form = _Form(is_anonymous=False)
    with pytest.raises(HTTPException) as fout:
        assert_submitter(form, "", "jan@example.com")
    assert fout.value.status_code == 422

    with pytest.raises(HTTPException):
        assert_submitter(form, "Jan", "geen-adres")

    assert_submitter(form, "Jan", "jan@example.com")       # geen fout


def test_een_bericht_mag_niet_leeg_zijn_als_dat_gevraagd_is():
    """Het berichtenformulier eiste dat alleen in het scherm; de chatbot schreef
    via dezelfde service en kwam er langs de zijdeur mee weg."""
    form = _Form(is_anonymous=True)
    with pytest.raises(HTTPException):
        assert_submitter(form, "Jan", "jan@example.com", message="  ",
                         require_message=True)

    assert_submitter(form, "Jan", "jan@example.com", message="Dag",
                     require_message=True)


def test_de_router_heeft_geen_eigen_kopie_meer():
    """De private helpers waar admin_ui.py uit importeerde, bestaan niet meer."""
    from app.domains.forms import router

    assert not hasattr(router, "_assert_submitter_impl")
    # De namen wijzen naar de service, niet naar een tweede implementatie.
    from app.domains.forms import service

    assert router.assert_submitter is service.assert_submitter
    assert router.apply_definition is service.apply_definition
    assert router.validate_definition is service.validate_definition


# ── HOOFDLID-regel (#635 F) ──────────────────────────────────────────────────
# Staat hier omdat het dezelfde soort bevinding is: een regel die alleen bestond
# zolang één scherm hem onthield.

def test_hoofdlid_wordt_nooit_overschreven(db_session):
    """Het hoofdlid draagt het adres, het lidmaatschap en de betaalcommunicatie.
    Hem stil degraderen laat een gezin zonder aanspreekpunt achter (#498)."""
    from app.domains.membership.api import set_relation_type
    from app.domains.mdm.api import MemberPerson

    from tests.conftest import create_test_family

    member, person = create_test_family(db_session, email="hoofdlid@example.com")
    db_session.flush()

    gewijzigd = set_relation_type(db_session, member.id, person.id, "PARTNER")

    koppeling = (db_session.query(MemberPerson)
                 .filter(MemberPerson.member_id == member.id,
                         MemberPerson.person_id == person.id).first())
    assert gewijzigd is False
    assert koppeling.relation_type == "HOOFDLID"


def test_een_gewoon_gezinslid_krijgt_wel_een_andere_rol(db_session):
    from app.domains.membership.api import set_relation_type
    from app.domains.mdm.api import MemberPerson

    from tests.conftest import create_test_family, create_test_person

    member, _hoofdlid = create_test_family(db_session, email="hl@example.com")
    kind = create_test_person(db_session, first_name="Kind")
    db_session.add(MemberPerson(member_id=member.id, person_id=kind.id,
                                relation_type="PARTNER"))
    db_session.flush()

    assert set_relation_type(db_session, member.id, kind.id, "KIND") is True

    koppeling = (db_session.query(MemberPerson)
                 .filter(MemberPerson.member_id == member.id,
                         MemberPerson.person_id == kind.id).first())
    assert koppeling.relation_type == "KIND"


def test_promoveren_tot_hoofdlid_kan_niet_via_dit_pad(db_session):
    from app.domains.membership.api import set_relation_type
    from app.domains.mdm.api import MemberPerson

    from tests.conftest import create_test_family, create_test_person

    member, _hoofdlid = create_test_family(db_session, email="hl2@example.com")
    kind = create_test_person(db_session, first_name="Kind2")
    db_session.add(MemberPerson(member_id=member.id, person_id=kind.id,
                                relation_type="KIND"))
    db_session.flush()

    assert set_relation_type(db_session, member.id, kind.id, "HOOFDLID") is False
