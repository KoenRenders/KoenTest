"""CR-32 phase 5 (R15, R18, F14, F16, C6 12, 13 and 15a): the data block of the
activities, the module rule, the viewer and the shell's thank-you.

Broken on purpose (15 October 2026), each red for its own reason: the module
check taken out of `_check_references` → a draft with the block saves on a tenant
without the module; `count` ignored by the renderer → every activity shows; the
viewer rule removed from `_button_html` → a member with a household sees *Word
lid*; the banner taken back out of the shell → the contact thank-you is gone on a
page that is not `home.html`.
"""

from datetime import date, timedelta

import pytest

from app.domains.cms.models import CmsPage
from app.domains.cms.render import render_document
from app.domains.cms.schema import InvalidShape, schema_for
from app.domains.cms.service import save_draft

pytestmark = pytest.mark.ui_serverrendered


def _doc(*blocks: dict) -> dict:
    return {"type": "doc", "content": list(blocks)}


def _upcoming(db, names):
    from app.domains.activities.api import Activity, ActivityDate

    for index, name in enumerate(names):
        activity = Activity(name=name, location="Miloheem")
        db.add(activity)
        db.flush()
        db.add(
            ActivityDate(
                activity_id=activity.id, start_date=date.today() + timedelta(days=10 + index)
            )
        )
    db.flush()


def _page(db, slug="datablok-cr32") -> CmsPage:
    page = CmsPage(title="Blok", slug=slug, content="<p>x</p>", is_published=True)
    db.add(page)
    db.flush()
    return page


def test_the_block_shows_the_upcoming_activities_as_the_home_did_at_most_count(db_session):
    _upcoming(db_session, ["Blokfeest een", "Blokfeest twee", "Blokfeest drie"])
    html = render_document(_doc({"type": "activities", "attrs": {"count": 2}}), db_session)
    assert "Blokfeest een" in html and "Blokfeest twee" in html and "Blokfeest drie" not in html
    assert html.count("data-card-title") == 2


def test_the_block_is_nothing_without_an_upcoming_activity_and_says_why_in_the_preview(
    db_session, monkeypatch
):
    import app.domains.activities.api as activities

    monkeypatch.setattr(activities, "list_activities", lambda *a, **k: [])
    document = _doc({"type": "activities", "attrs": {"count": 3}})
    assert render_document(document, db_session) == ""
    assert "geen komende activiteiten" in render_document(document, db_session, preview=True)


def test_a_tenant_without_the_module_has_no_block_and_the_save_refuses_it(db_session, monkeypatch):
    import app.domains.mdm.api as mdm

    page = _page(db_session)
    monkeypatch.setattr(mdm, "module_enabled", lambda code: str(code) != "activities")
    with pytest.raises(
        InvalidShape, match="Het blok activities hoort bij een module die uit staat"
    ):
        save_draft(
            db_session, page.id, _doc({"type": "activities", "attrs": {"count": 4}}), commit=False
        )
    assert render_document(_doc({"type": "activities", "attrs": {"count": 4}}), db_session) == ""
    monkeypatch.setattr(mdm, "module_enabled", lambda code: True)
    assert save_draft(
        db_session, page.id, _doc({"type": "activities", "attrs": {"count": 4}}), commit=False
    ).draft_json


def test_the_editor_offers_a_data_block_only_for_a_module_that_is_on():
    assert "activities" in schema_for("page", data_blocks=["activities"])["insert"]
    assert "activities" not in schema_for("page", data_blocks=[])["insert"]
    assert "activities" not in [
        item["id"] for item in schema_for("page", data_blocks=[])["toolbar"]["insert"]
    ]


def test_the_registry_names_the_data_blocks_of_a_module_and_membership_has_none():
    from app.kernel.modules import REGISTRY, ModuleCode, owner_of

    assert REGISTRY[ModuleCode.ACTIVITIES].home_blocks == ("activities",)
    assert REGISTRY[ModuleCode.MEMBERSHIP].home_blocks == ()
    assert owner_of("home_blocks", "activities") is ModuleCode.ACTIVITIES


def _button(**attrs) -> dict:
    return {"type": "button", "attrs": {"label": "Word lid", "variant": "primary", **attrs}}


def test_every_button_to_lid_worden_shows_mijn_gezin_to_a_member_with_a_household(db_session):
    document = _doc(_button(screen="lid-worden"))
    visitor = render_document(document, db_session)
    assert 'href="/lid-worden"' in visitor and ">Word lid<" in visitor
    member = render_document(document, db_session, viewer={"has_household": True})
    assert 'href="/leden/gezin"' in member and ">Mijn gezin<" in member
    assert "Word lid" not in member
    signed_in_only = render_document(document, db_session, viewer={"has_household": False})
    assert 'href="/lid-worden"' in signed_in_only and ">Word lid<" in signed_in_only


def test_other_buttons_are_not_touched_by_the_viewer(db_session):
    document = _doc(_button(label="Naar buiten", href="https://example.test/x"))
    html = render_document(document, db_session, viewer={"has_household": True})
    assert 'href="https://example.test/x"' in html and ">Naar buiten<" in html


def test_the_thank_you_shows_on_any_page_the_contact_form_may_land_on(client, db_session):
    page = CmsPage(
        title="Een pagina", slug="bedankt-cr32", content="<p>Hallo.</p>", is_published=True
    )
    db_session.add(page)
    db_session.commit()
    plain = client.get("/bedankt-cr32").text
    thanked = client.get("/bedankt-cr32?bericht=verzonden").text
    assert "Bedankt! We hebben je bericht goed ontvangen" not in plain
    assert "Bedankt! We hebben je bericht goed ontvangen" in thanked
    assert thanked.count("Bedankt! We hebben je bericht goed ontvangen") == 1
