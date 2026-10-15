"""CR-32 phase 5 (R16, R17, C6 15): a new tenant's seed and the migration for the
tenants that exist make the SAME home page.

Two doors, one builder: `seed_home_page` (ORM, on `TenantCreated`) and migration
208 (SQL, for the existing tenants) both take their document from
`cms.home_page.home_document`; this test holds the whole result equal — the
document, the title, the slug, the flag, the intro made invisible — so the two
cannot drift.

Broken on purpose (15 October 2026): `contact_slug` left out of the migration's
call → the documents differ on the contact button; the intro not unpublished by
the migration → the last assertion fails; the idempotence guard (`is_home`)
taken out of the seed → the second seed makes a second page.
"""

import importlib.util
from pathlib import Path

import pytest

from app.domains.cms.api import published_document
from app.domains.cms.models import CmsPage, CmsPageTranslation
from app.domains.mdm.api import TenantKind, create_tenant

pytestmark = pytest.mark.ui_serverrendered

MIGRATION = next(
    (Path(__file__).parents[2] / "alembic" / "versions").glob("208_*_home_page_in_the_cms.py")
)

INTRO = [
    {
        "type": "heading",
        "attrs": {"level": 2},
        "content": [{"type": "text", "text": "Welkom bij ons"}],
    },
    {"type": "paragraph", "content": [{"type": "text", "text": "Een tekst van het bestuur."}]},
]


def _load():
    spec = importlib.util.spec_from_file_location("home_208", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pages(db, tenant_id):
    return (
        db.query(CmsPage)
        .filter(CmsPage.tenant_id == tenant_id)
        .execution_options(include_all_tenants=True)
        .all()
    )


def _remove_home(db, tenant_id):
    for page in _pages(db, tenant_id):
        if page.is_home:
            db.query(CmsPageTranslation).filter(CmsPageTranslation.page_id == page.id).delete()
            db.delete(page)
    db.flush()


def _give_an_intro(db, tenant_id):
    """What an existing tenant has: a published `home-intro` page with a document."""
    intro = CmsPage(
        tenant_id=tenant_id, slug="home-intro", title="Welkom", is_published=True, show_in_nav=False
    )
    db.add(intro)
    db.flush()
    db.add(
        CmsPageTranslation(
            page_id=intro.id,
            language="nl",
            title="Welkom",
            draft_json={"type": "doc", "content": INTRO},
            published_json={"type": "doc", "content": INTRO},
        )
    )
    db.flush()
    return intro


@pytest.mark.parametrize("kind", [TenantKind.COMPANY, TenantKind.ASSOCIATION])
def test_the_migration_and_the_seed_make_the_same_home_page(db_session, kind):
    org = create_tenant(db_session, name="Bakkerij & Co", code=f"home-{kind.value}", kind=kind)
    tenant_id = org.id

    # The migration's door: an existing tenant with an intro and no home page.
    _remove_home(db_session, tenant_id)
    intro = _give_an_intro(db_session, tenant_id)
    made, _skipped = _load().make_home_pages(db_session.connection())
    assert tenant_id in made
    db_session.expire_all()
    by_migration = next(p for p in _pages(db_session, tenant_id) if p.is_home)
    document_m = published_document(db_session, by_migration)
    shape_m = (
        by_migration.slug,
        by_migration.title,
        by_migration.is_published,
        by_migration.show_in_nav,
    )
    assert intro.is_published is False, "the intro is made invisible by the same step"

    # The seed's door: the same tenant, the same intro, no home page.
    _remove_home(db_session, tenant_id)
    from app.domains.cms.service import seed_home_page

    by_seed = seed_home_page(db_session, tenant_id, "Bakkerij & Co", intro_blocks=INTRO)
    assert by_seed is not None
    document_s = published_document(db_session, by_seed)
    shape_s = (
        by_seed.slug,
        by_seed.title,
        by_seed.is_published,
        by_seed.show_in_nav,
    )

    assert document_m == document_s, "the migration and the seed compose differently"
    assert shape_m == shape_s == ("start", "Bakkerij & Co", True, False)


def test_a_second_run_of_either_door_makes_nothing_and_never_touches_a_page(db_session):
    from app.domains.cms.service import seed_home_page

    org = create_tenant(db_session, name="Eenmaal", code="home-eenmaal", kind=TenantKind.COMPANY)
    first = next(p for p in _pages(db_session, org.id) if p.is_home)
    before = published_document(db_session, first)
    assert seed_home_page(db_session, org.id, "Eenmaal") is None
    made, _ = _load().make_home_pages(db_session.connection())
    assert org.id not in made
    db_session.expire_all()
    homes = [p for p in _pages(db_session, org.id) if p.is_home]
    assert [p.id for p in homes] == [first.id]
    assert published_document(db_session, homes[0]) == before


def test_the_module_set_decides_what_the_page_holds(db_session):
    company = create_tenant(db_session, name="Zonder", code="home-zonder", kind=TenantKind.COMPANY)
    association = create_tenant(
        db_session, name="Met", code="home-met", kind=TenantKind.ASSOCIATION
    )

    def kinds(tenant_id):
        page = next(p for p in _pages(db_session, tenant_id) if p.is_home)
        text = str(published_document(db_session, page))
        return {
            "activities": "'activities'" in text,
            "fee": "membership_price_full" in text,
            "contact": "berichten" in text,
        }

    assert kinds(company.id) == {"activities": False, "fee": False, "contact": True}
    assert kinds(association.id) == {"activities": True, "fee": True, "contact": True}
