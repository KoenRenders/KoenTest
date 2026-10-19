"""Organisaties on the kit (#1932): the list and the record.

What can break: the three columns (the kind segments and the account above went
with CR-20), the Status cell that holds only Inactief, the record's four cards in both modes with every field of the old
form, the head and its Acties, the summary card, and the help texts that said
what another domain does with a value.

Each test names what it was made red by where it matters.
"""

import re
from html.parser import HTMLParser

import pytest

from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.mdm.api import ALLE_ORGANISATIEVELDEN, Organization, Tenant, create_organization
from tests._sites import new_site
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_postal_code

pytestmark = pytest.mark.ui_serverrendered


def _operator(client, db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    if not db.query(UserRole).filter_by(user_id=user.id, role_code="OPERATOR").first():
        db.add(UserRole(user_id=user.id, role_code="OPERATOR"))
        db.flush()
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _unit_under(db, account, *, name="Afdeling Zeven", code="zeven-1932"):
    """An afdeling that hangs under `account` (CR-20: a tenant showing a party of
    its own). Returns the party the tenant shows."""
    return new_site(db, name=name, code=code, account_id=account.id).organization


def _row(html: str, organisation_id: int) -> str:
    at = html.index(f'data-organisation="{organisation_id}"')
    return html[html.rindex("<tr", 0, at) : html.index("</tr>", at)]


def _cell(row: str, cell: str, nth: int = 0) -> str:
    return re.findall(rf'data-cell="{cell}"[^>]*>(.*?)</td>', row, flags=re.S)[nth]


# ── The list ──────────────────────────────────────────────────────────────────


def test_the_columns_stand_in_their_order(client, platform_workspace, db_session):
    """CR-20: the parties only — the kind (Soort) and the account above (Onder)
    went with the tenant columns of the organisation; phase 2 adds how many
    tenants use each one (Gebruikt door, F5)."""
    _operator(client, db_session)
    html = client.get("/admin/organisaties").text
    heads = re.findall(r"data-column-head[^>]*>(.*?)</th>", html, flags=re.S)
    assert [re.sub(r"<[^>]+>", "", h).strip() for h in heads] == [
        "Organisatie",
        "Gebruikt door",
        "Rechtsvorm",
        "Status",
    ]
    first = re.search(r"<tr data-row .*?</tr>", html, flags=re.S).group(0)
    assert re.findall(r'<td data-cell="(\w+)"', first) == ["name", "extra", "extra", "status"]
    assert "data-status-filter" not in html, "no kind segments since CR-20"


def test_a_tenant_is_no_row_and_the_legal_form_reads_as_its_word(
    client, platform_workspace, db_session
):
    """CR-20 R3: Organisaties lists organisations only. Broken on purpose: the
    list read from the tenants as well → the brand's code appears and this fails."""
    account = create_organization(db_session, name="Account Elf")
    new_site(db_session, name="Afdeling Elf", code="afdeling-elf-1932", account_id=account.id)
    db_session.commit()
    _operator(client, db_session)
    html = client.get("/admin/organisaties").text
    assert "afdeling-elf-1932" not in html
    names = re.findall(r"data-row-link[^>]*>([^<]+)</a>", html)
    assert "Account Elf" in names and "Afdeling Elf" in names, "the two parties"

    account.legal_form = "VZW"
    db_session.commit()
    again = client.get("/admin/organisaties").text
    assert _cell(_row(again, account.id), "extra", 1).strip() == "vzw"


def test_only_an_inactive_organisation_has_a_status_badge(client, platform_workspace, db_session):
    """Broken on purpose: the `if r.inactive` taken out of `_org_kaarten.html` →
    the active row carries a badge too and the first assertion fails."""
    active = create_organization(db_session, name="Actief Twaalf")
    inactive = create_organization(db_session, name="Inactief Twaalf")
    inactive.is_active = False
    db_session.commit()
    _operator(client, db_session)
    html = client.get("/admin/organisaties").text

    assert "data-badge" not in _cell(_row(html, active.id), "status")
    assert "Inactief" in _cell(_row(html, inactive.id), "status")


def test_search_on_name_and_sort_by_name(client, platform_workspace, db_session):
    create_organization(db_session, name="Zebra Dertien")
    create_organization(db_session, name="Alfa Dertien")
    db_session.commit()
    _operator(client, db_session)

    by_name = client.get("/admin/organisaties?q=dertien").text
    assert re.findall(r"data-row-link[^>]*>([^<]+)</a>", by_name) == [
        "Alfa Dertien",
        "Zebra Dertien",
    ], "by name, A to Z"
    turned = client.get("/admin/organisaties?q=dertien&sort=-naam").text
    assert re.findall(r"data-row-link[^>]*>([^<]+)</a>", turned) == [
        "Zebra Dertien",
        "Alfa Dertien",
    ]


def test_the_row_link_carries_the_lists_state_and_the_fragment_its_counts(
    client, platform_workspace, db_session
):
    account = create_organization(db_session, name="Account Veertien")
    db_session.commit()
    _operator(client, db_session)
    html = client.get("/admin/organisaties?q=veertien").text
    link = re.search(rf'href="(/admin/organisaties/{account.id}\?terug=[^"]+)"', html).group(1)
    assert "q%3Dveertien" in link

    fragment = client.get("/admin/organisaties?q=veertien", headers={"HX-Request": "true"}).text
    assert "<html" not in fragment and "Account Veertien" in fragment
    assert 'id="org-filter-count"' in fragment and 'hx-swap-oob="true"' in fragment


# ── The record ────────────────────────────────────────────────────────────────


class _FormFields(HTMLParser):
    """What the browser would send for the form of the record: every named
    input, and the selected option of every select."""

    def __init__(self):
        super().__init__()
        self.fields: dict[str, str] = {}
        self._select: str | None = None
        self._inside = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form" and a.get("id") == "org-form":
            self._inside = True
        if not self._inside:
            return
        if tag == "input" and a.get("name") and a.get("type") not in ("submit", "button"):
            self.fields[a["name"]] = a.get("value") or ""
        elif tag == "select" and a.get("name"):
            self._select = a["name"]
            self.fields.setdefault(self._select, "")
        elif tag == "option" and self._select is not None and "selected" in a:
            self.fields[self._select] = a.get("value") or ""

    def handle_endtag(self, tag):
        if tag == "select":
            self._select = None
        if tag == "form":
            self._inside = False


def _form_of(html: str) -> dict[str, str]:
    parser = _FormFields()
    parser.feed(html)
    return parser.fields


@pytest.fixture
def record(client, platform_workspace, db_session):
    seed_postal_code(db_session)
    account = create_organization(db_session, name="Account Vijftien")
    unit = _unit_under(db_session, account, name="Afdeling Vijftien", code="afd-vijftien-1932")
    db_session.commit()
    csrf = _operator(client, db_session)
    return account, unit, csrf


def test_the_edit_form_holds_every_field_of_the_old_form(client, record):
    """Broken on purpose: one field (`tiktok_url`) left out of the template → the
    set differs and this fails naming it."""
    account, _unit, _csrf = record
    fields = _form_of(client.get(f"/admin/organisaties/{account.id}?bewerken=1").text)
    expected = set(ALLE_ORGANISATIEVELDEN) | {"street", "house_number", "bus_number", "postal_code"}
    assert expected <= set(fields), f"missing: {sorted(expected - set(fields))}"
    assert len(ALLE_ORGANISATIEVELDEN) + 4 >= 17, "the seventeen fields of the issue"


def test_a_form_posted_as_the_old_screen_posted_it_reads_back_in_read_mode(client, record):
    account, _unit, csrf = record
    sent = {
        "name": "Account Vijftien",
        "legal_form": "VZW",
        "phone": "014123456",
        "mobile": "0470123456",
        "email": "info@example.com",
        "website": "https://www.example.com",
        "facebook_url": "https://www.facebook.com/voorbeeld",
        "instagram_url": "https://www.instagram.com/voorbeeld",
        "tiktok_url": "",
        "street": "Kerkstraat",
        "house_number": "12",
        "bus_number": "",
        "postal_code": "2400",
        "payment_iban": "BE68 5390 0754 7034",
        "payment_bic": "TRIOBEBB",
        "payment_beneficiary": "Account Vijftien vzw",
        "enterprise_number": "0123.456.749",
        "vat_number": "",
    }
    answer = client.post(
        f"/admin/organisaties/{account.id}",
        data=sent,
        headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
    )
    assert answer.status_code == 200
    assert answer.headers["HX-Push-Url"] == f"/admin/organisaties/{account.id}"
    assert 'data-mode="read"' in answer.text, "a good save answers the record in read mode"

    read = client.get(f"/admin/organisaties/{account.id}").text
    # The legal form is read as its word, in the card and in the head (#1932).
    assert "Rechtsvorm:</span> vzw" in read
    head = read[read.index("data-record-head") : read.index("data-form-flow")]
    assert "vzw" in head
    for shown in (
        "Account Vijftien",
        "014 12 34 56",
        "info@example.com",
        "www.example.com",
        "Kerkstraat 12",
        "BE68 5390 0754 7034",
        "TRIOBEBB",
        # Stored as its ten digits (#1517), shown as stored, as the old form did.
        "0123456749",
    ):
        assert shown in read, f"{shown!r} is not on the record"
    # The edit form hands back exactly what was saved.
    back = _form_of(client.get(f"/admin/organisaties/{account.id}?bewerken=1").text)
    assert {k: back[k] for k in ("name", "email", "street", "payment_iban", "postal_code")} == {
        "name": "Account Vijftien",
        "email": "info@example.com",
        "street": "Kerkstraat",
        "payment_iban": "BE68 5390 0754 7034",
        "postal_code": "2400",
    }


def test_read_mode_puts_each_fact_in_the_cell_of_its_field(client, record):
    """Telefoon and Mobiel share a row, E-mail stands under them at full width
    (K2); the address is one fact with the map-pin icon; an empty value is "—"."""
    account, _unit, _csrf = record
    read = client.get(f"/admin/organisaties/{account.id}").text
    spans = re.findall(r'<p data-span="(\w+)"', read.split("data-form-flow", 1)[1])
    # Organisatie: name/legal form, phone/mobile, mail, website, three social; Adres;
    # Rekening: IBAN, BIC, beneficiary; Nummers: two.
    assert spans[:4] == ["half", "half", "half", "half"]
    assert spans[4:9] == ["full"] * 5
    assert "data-address-line" in read
    assert read.count("—") >= 8, "an empty value reads as a dash"
    assert "<input" not in read.split("data-form-flow", 1)[1], "read mode holds no control"


def test_the_head_the_summary_and_the_acties_menu(client, record, db_session):
    account, unit, _csrf = record
    unit_page = client.get(f"/admin/organisaties/{unit.id}").text
    head = unit_page[unit_page.index("data-record-head") : unit_page.index("data-form-flow")]
    showing = db_session.query(Tenant).filter(Tenant.organization_id == unit.id).one()
    assert "Afdeling Vijftien" in head
    assert f'href="/admin/tenants/{showing.id}"' in head, (
        "Instellingen van de site, of the tenant that shows it (CR-20)"
    )
    assert "Bewerken" in head and "Actief" in unit_page.split("data-summary-card", 1)[1]

    account_page = client.get(f"/admin/organisaties/{account.id}").text
    assert "/admin/tenants/" not in account_page, "no tenant shows the account"
    summary = account_page.split("data-summary-card", 1)[1]
    assert ">Rechtsvorm<" in summary


def test_an_inactive_organisation_says_so_in_the_summary(client, record, db_session):
    account, _unit, _csrf = record
    account.is_active = False
    db_session.commit()
    page = client.get(f"/admin/organisaties/{account.id}").text
    assert "Inactief" in page.split("data-summary-card", 1)[1]


def test_no_help_text_says_what_another_domain_does_with_a_value(client, record):
    """A screen says what a value is, never what another domain does with it
    (AGENTS.md, 10 October 2026). Broken on purpose: the old name hint ("Staat in
    de paginatitel, de afzender van je mails en de footer.") put back → red."""
    account, _unit, _csrf = record
    edit = client.get(f"/admin/organisaties/{account.id}?bewerken=1").text
    for gone in ("paginatitel", "footer", "bevestigingsmail", "overschrijving"):
        assert gone not in edit, f"{gone!r} is back on the form"
    # The format hints stay.
    assert "Bv. 0123.456.749." in edit and "een buitenlands nummer bewaren we zoals getypt" in edit


def test_a_refusal_comes_as_the_banner_and_writes_nothing(client, record, db_session):
    account, _unit, csrf = record
    answer = client.post(
        f"/admin/organisaties/{account.id}",
        data={"name": "Andere naam", "enterprise_number": "123"},
        headers={"X-CSRF-Token": csrf, "HX-Request": "true"},
    )
    assert answer.status_code == 422
    assert answer.headers["HX-Retarget"] == "#org-melding"
    assert 'data-error-for="enterprise_number"' in answer.text
    db_session.expire_all()
    assert db_session.get(Organization, account.id).name == "Account Vijftien"
