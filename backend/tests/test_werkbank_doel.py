"""#666 — het afhandelformulier werkt in béide schermen.

`_werkbank_detail.html` staat op de werkbanklijst én op de zelfstandige
taakpagina, maar wees naar `#werkbank-lijst` — een id dat alleen op de lijst
bestaat. Op de detailpagina gooide htmx een `targetError` en **verstuurde het
verzoek nooit**: in het HDEV-log stonden alleen GET's, en de csrf_fail-diagnose
uit #662 bleef leeg omdat er geen 403 was. Vanaf de lijst werkte de knop wél,
dus de route was in orde.

De invariant hieronder is niet "de knop werkt" maar "het doel van de vorm is
oplosbaar in elk scherm dat het fragment opneemt". Dat is wat stukging.
"""
import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _taak(db):
    from app.domains.workflow.models import WorkflowTask

    taak = WorkflowTask(kind="bericht.behartigen", status="open",
                        subject_type="form_submission", subject_id=1,
                        title="Vernieuwing nakijken")
    db.add(taak)
    db.commit()
    return taak


def _doelen(html: str) -> list[str]:
    """De hx-target-waarden van de afhandelvormen op deze pagina."""
    return [m.group(1) for m in re.finditer(
        r'<form[^>]*hx-post="[^"]*/afgehandeld"[^>]*hx-target="([^"]+)"', html)]


@pytest.mark.parametrize("context", ["fragment", "pagina"])
def test_het_doel_is_oplosbaar_in_beide_schermen(client, db_session, context):
    """De kern. Een id-doel moet in dát document bestaan; `this` altijd.

    Het fragment wordt vanaf de lijst met htmx bijgeladen (`HX-Request`) en de
    detailpagina neemt het met een include op. In dat tweede document bestond
    `#werkbank-lijst` niet — precies de fout.
    """
    taak = _taak(db_session)
    _login(client)
    url = f"/admin/werkbank/taken/{taak.id}"
    kop = {"HX-Request": "true"} if context == "fragment" else {}
    html = client.get(url, headers=kop).text

    doelen = _doelen(html)
    assert doelen, f"geen afhandelvorm gevonden ({context})"
    for doel in doelen:
        if doel.startswith("#"):
            assert f'id="{doel[1:]}"' in html, (
                f"{context}: het doel {doel} staat niet in dit document — htmx "
                "verstuurt dan niets (#666)")
        else:
            assert doel in ("this", "closest form"), f"onbekend doel {doel!r}"


def test_afhandelen_vanaf_de_detailpagina_stuurt_terug(client, db_session):
    """Bewuste keuze: de taak is weg, dus die pagina heeft niets meer te tonen."""
    taak = _taak(db_session)
    csrf = _login(client)

    r = client.post(f"/admin/werkbank/taken/{taak.id}/afgehandeld",
                    data={"besluit": "goedgekeurd", "standalone": "1"},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 204
    assert r.headers.get("HX-Redirect") == "/admin/werkbank"

    from app.domains.workflow.models import WorkflowTask
    db_session.expire_all()
    assert db_session.get(WorkflowTask, taak.id).status == "done"


def test_afhandelen_vanaf_de_lijst_ververst_de_lijst(client, db_session):
    """Daar hoort het antwoord wél op het scherm te landen, op zijn eigen plek."""
    taak = _taak(db_session)
    csrf = _login(client)

    r = client.post(f"/admin/werkbank/taken/{taak.id}/afgehandeld",
                    data={"besluit": ""}, headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200
    assert r.headers.get("HX-Retarget") == "#werkbank-lijst"
    assert r.headers.get("HX-Reswap") == "innerHTML"


def test_de_kit_meldt_ook_een_doelfout():
    """#649 luisterde op htmx:responseError, en bij een doelfout is er geen
    response — die hele klasse bleef dus even stil als de 403's vroeger."""
    kit = open("app/ui/templates/_macros.html", encoding="utf-8").read()
    assert "htmx:targetError" in kit and "htmx:swapError" in kit
    # De melding is voor de gebruiker; de selector hoort in de console.
    handler = kit[kit.index("htmx:targetError"):]
    handler = handler[:handler.index("});")]
    assert "console.error" in handler
    assert "meldFout" in handler
