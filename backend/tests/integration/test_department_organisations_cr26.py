"""A department's Organisaties, by fact (CR-26 phase 2, F9, T10, T12; Koen, 19 October
2026: "weg 2" — an address family of its own, behind the invoices module).

- the list shows the organisations with a fact at the tenant and the ones with a fact
  nowhere, not the ones that belong to another tenant's facts;
- a record by id without a fact here answers 404, as an id that is not yours;
- a department creates an organisation in its own account, and sees it at once;
- *Klant* is read from the orders (`has_orders`), never stored;
- the address family is one constant, the module is on or off, the platform has its own.

Red proofs (19 October 2026, each put back): the fact filter left out of `_list_view` ->
the first test finds the other tenant's organisation; `_party_here` left out of the record
route -> the 404 test gets 200; the account left out of the create -> the created
organisation is not in the list.
"""

from __future__ import annotations

from app.domains.mdm.api import (
    PaymentMethod,
    create_organization,
    current_account_id,
)
from app.domains.mdm.tests.test_tenant_modules import modules_of  # noqa: F401
from app.domains.reporting.tests.test_reporting_panel_ui import login
from app.domains.sales.models import SalesOrder
from app.kernel.tenancy import TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID
from app.ui import organisaties_ui
from tests.conftest import SEEDED_ADMIN_EMAIL

BASE = organisaties_ui.DEPARTMENT_NAV


def _order(db, *, tenant_id: int, party_id: int) -> None:
    db.add(
        SalesOrder(
            tenant_id=tenant_id,
            buyer_party_id=party_id,
            guest_name="Gast",
            guest_email="gast@example.com",
            guest_mobile="0470000000",
            payment_method=PaymentMethod.TRANSFER,
            secret_key=f"dep-{tenant_id}-{party_id}",
        )
    )
    db.flush()


def _account_org(db, name: str):
    """An organisation in the account of the Millegem tenant, as a department makes one."""
    from app.kernel.tenancy import current_tenant_id

    token = current_tenant_id.set(TENANT_MILLEGEM_ID)
    try:
        organisation = create_organization(db, name=name, account_id=current_account_id(db))
    finally:
        current_tenant_id.reset(token)
    return organisation


def test_the_list_shows_what_has_a_fact_here_and_what_has_none_anywhere(
    client, db_session, every_module_on
):
    ordered_here = _account_org(db_session, "Hier Besteld vzw")
    _order(db_session, tenant_id=TENANT_MILLEGEM_ID, party_id=ordered_here.party_id)
    ordered_elsewhere = _account_org(db_session, "Elders Besteld vzw")
    _order(db_session, tenant_id=TENANT_VOORBEELD_ID, party_id=ordered_elsewhere.party_id)
    nowhere = _account_org(db_session, "Nergens vzw")
    db_session.commit()
    login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))

    html = client.get(BASE).text
    assert "Hier Besteld vzw" in html and "Nergens vzw" in html
    assert "Elders Besteld vzw" not in html
    assert f'data-organisation="{nowhere.id}"' in html


def test_a_record_without_a_fact_here_answers_404(client, db_session, every_module_on):
    elsewhere = _account_org(db_session, "Alleen Elders vzw")
    _order(db_session, tenant_id=TENANT_VOORBEELD_ID, party_id=elsewhere.party_id)
    here = _account_org(db_session, "Hier Ook vzw")
    _order(db_session, tenant_id=TENANT_MILLEGEM_ID, party_id=here.party_id)
    db_session.commit()
    csrf = login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))

    assert client.get(f"{BASE}/{elsewhere.id}").status_code == 404
    assert (
        client.post(
            f"{BASE}/{elsewhere.id}", data={"name": "Gekaapt"}, headers={"X-CSRF-Token": csrf}
        ).status_code
        == 404
    )
    assert client.get(f"{BASE}/{here.id}").status_code == 200


def test_a_department_creates_an_organisation_in_its_account_and_sees_it(
    client, db_session, every_module_on
):
    csrf = login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    answer = client.post(
        BASE,
        data={"name": "Nieuw Door Afdeling vzw"},
        headers={"X-CSRF-Token": csrf},
        follow_redirects=False,
    )
    assert answer.status_code == 303 and answer.headers["location"].startswith(BASE + "/")
    assert "Nieuw Door Afdeling vzw" in client.get(BASE).text
    record = client.get(answer.headers["location"]).text
    assert f'hx-post="{answer.headers["location"]}"' not in record, "read mode first"
    edit = client.get(answer.headers["location"] + "?bewerken=1").text
    assert f'hx-post="{answer.headers["location"]}"' in edit


def test_klant_is_read_from_the_orders(client, db_session, every_module_on):
    organisation = _account_org(db_session, "Klant Proef vzw")
    db_session.commit()
    login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    assert "Klant</span>" not in client.get(f"{BASE}/{organisation.id}").text
    _order(db_session, tenant_id=TENANT_MILLEGEM_ID, party_id=organisation.party_id)
    db_session.commit()
    assert "Klant" in client.get(f"{BASE}/{organisation.id}").text


def test_the_platform_has_its_own_and_the_module_decides(
    client,
    db_session,
    every_module_on,
    modules_of,  # noqa: F811
):
    platform_id, platform_headers = every_module_on["platform"]
    login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN", "OPERATOR"))
    assert client.get(BASE, headers=platform_headers).status_code == 404
    assert client.get("/admin/organisaties", headers=platform_headers).status_code == 200
    assert client.get("/admin/organisaties").status_code == 404

    modules_of({TENANT_MILLEGEM_ID: frozenset({"cms"})})
    assert client.get(BASE).status_code == 404, "the module is off"


def test_the_department_address_is_one_constant():
    """The decorators and the form targets carry the address as text (the rules gate reads
    them); they are held to the constant here."""
    paths = {r.path for r in organisaties_ui.department_router.routes}
    assert {BASE, BASE + "/nieuw", BASE + "/{organization_id}"} <= paths
    templates = "app/ui/templates/"
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[2] / templates
    for name in ("admin_organisatie.html", "admin_organisatie_nieuw.html"):
        assert f'hx-post="{BASE}' in (root / name).read_text(), name


def _read_only_and_refused(client, csrf, organisation_id: int, db_session, name: str) -> None:
    """The record opens read-only even with `?bewerken=1`, and the save is refused (422, on the banner)
    with the name unchanged: the rule of Q14, as "Onze organisatie" applies it."""
    record = client.get(f"{BASE}/{organisation_id}?bewerken=1").text
    assert "data-read-only" in record and 'hx-post="/admin/relaties/' not in record
    refused = client.post(
        f"{BASE}/{organisation_id}", data={"name": "Gekaapt"}, headers={"X-CSRF-Token": csrf}
    )
    assert refused.status_code == 422
    db_session.expire_all()
    from app.domains.mdm.api import Organization

    assert db_session.get(Organization, organisation_id).name == name


def test_the_account_itself_is_read_only_in_a_department(client, db_session, every_module_on):
    """An ADMIN of a department cannot rename the account's own organisation, which the
    list shows him as a party with a fact nowhere (dev4's measurement, PR #2169).

    Red proof (put back): the `read_only=` of the department's record dropped -> the form
    opens; the refusal of the save dropped -> the account is renamed."""
    from app.domains.mdm.api import Organization
    from app.kernel.tenancy import current_tenant_id

    csrf = login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    token = current_tenant_id.set(TENANT_MILLEGEM_ID)
    try:
        account = (
            db_session.query(Organization)
            .filter(Organization.party_id == current_account_id(db_session))
            .execution_options(include_all_tenants=True)
            .one()
        )
    finally:
        current_tenant_id.reset(token)
    assert f'data-organisation="{account.id}"' in client.get(BASE).text
    _read_only_and_refused(client, csrf, account.id, db_session, account.name)


def test_a_party_two_departments_show_is_read_only_at_both(client, db_session, every_module_on):
    from app.domains.mdm.api import Tenant

    shared = _account_org(db_session, "Gedeeld vzw")
    for tenant_id in (TENANT_MILLEGEM_ID, TENANT_VOORBEELD_ID):
        db_session.get(Tenant, tenant_id).organization_id = shared.id
    db_session.commit()
    csrf = login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    _read_only_and_refused(client, csrf, shared.id, db_session, "Gedeeld vzw")


def test_an_organisation_of_the_department_alone_is_editable(client, db_session, every_module_on):
    own = _account_org(db_session, "Eigen vzw")
    db_session.commit()
    csrf = login(client, db_session, SEEDED_ADMIN_EMAIL, ("ADMIN",))
    saved = client.post(
        f"{BASE}/{own.id}", data={"name": "Eigen BV"}, headers={"X-CSRF-Token": csrf}
    )
    assert saved.status_code == 200 and "Eigen BV" in saved.text
