"""CR-20 (#1578) — the migration that pulls the tenant out of the organisation.

The suite builds its schema with the whole chain, so migration 313 runs on every
run — but on the seed only, where no tenant borrows another organisation's data
and no page names an account. This test runs the chain on a database of its own
up to 312, writes the cases the seed lacks, runs 313 and reads what it left:

- the tenants carry the ids their organisation rows had (C6 test 1's premise,
  C4.1), with account and shown organisation (F7);
- the organisation keeps the party, no tenant column and no role (test 9, test 2);
- a borrowed-data tenant's own row is soft-deleted with its address, the tenant
  stays (F7, C4.6);
- the meeting circle hangs on the party its tenant shows, with its ids (F11);
- the stored `{{tenants:<account code>}}` names a tenant (F10, test 13);
- settings, modules and roles keep their values and gain the key (test 8); a
  role or a setting on an account is removed (Koen, 18 October 2026: "1a");
- the four reporting views list the tenants (test 12);
- an organisation's address in the seam is still accepted (test 14);
- every site renders what it rendered before 313 (test 11).

Proven red (put back each time): step 7 of the migration without its
`UPDATE mdm.organizations SET deleted_at` → the borrowed row stays live and the
soft-delete assertion fails; step 6 without its `UPDATE … organization_persons`
→ the circle assertion fails.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import text

from tests._own_database import own_database

BEFORE = "312_2026_10_16_162902"
AFTER = "313_2026_10_18_180812"


def _migrated(name: str, target: str):
    """A database of its own: the chain to 312, the cases, then `target`."""
    with own_database(name) as (upgrade, engine):
        upgrade(BEFORE)
        with engine.begin() as conn:
            _write_the_cases(conn)
        upgrade(target)
        yield engine


@pytest.fixture(scope="module")
def migrated_url():
    yield from _migrated("cr20", AFTER)


@pytest.fixture(scope="module")
def head_url():
    """The cases through every migration: the code under test reads the schema
    of the head, so test 11 renders there (CR-26's 314 keeps the sites too)."""
    yield from _migrated("cr20_head", "head")


def _one(conn, sql: str, **params):
    return conn.execute(text(sql), params).scalar()


def _write_the_cases(conn) -> None:
    """A company account with a brand site that shows the company's data, a page
    that lists the company's sites, a circle on the platform row, a setting, a
    role and a module of the brand."""
    platform = _one(conn, "SELECT id FROM mdm.organizations WHERE org_type = 'PLATFORM'")
    conn.execute(
        text(
            "INSERT INTO mdm.organizations (org_type, code, name, is_active, created_at, "
            "updated_at) VALUES ('ACCOUNT', 'firma-cr20', 'Firma Twintig', true, now(), now())"
        )
    )
    firm = _one(conn, "SELECT id FROM mdm.organizations WHERE code = 'firma-cr20'")
    conn.execute(
        text(
            "INSERT INTO mdm.organizations (org_type, code, name, kind, parent_id, "
            "site_organization_id, site_name, is_active, created_at, updated_at) VALUES "
            "('UNIT', 'merk-cr20', 'Merk (leeg)', 'BEDRIJF', :firm, :firm, 'Merk Twintig', "
            "true, now(), now())"
        ),
        {"firm": firm},
    )
    brand = _one(conn, "SELECT id FROM mdm.organizations WHERE code = 'merk-cr20'")
    # A site under no account: "Overige" in the sites placeholder before 313,
    # its own account after (Koen, 18 October 2026: "2a").
    conn.execute(
        text(
            "INSERT INTO mdm.organizations (org_type, code, name, kind, site_name, is_active, "
            "created_at, updated_at) VALUES ('UNIT', 'los-cr20', 'Losse Vereniging', "
            "'VERENIGING', 'Los Twintig', true, now(), now())"
        )
    )
    # An account with no tenant, made last: the highest organisation id is no
    # tenant's, so the tenants' sequence must start past it.
    conn.execute(
        text(
            "INSERT INTO mdm.organizations (org_type, code, name, is_active, created_at, "
            "updated_at) VALUES ('ACCOUNT', 'laatste-cr20', 'Laatste', true, now(), now())"
        )
    )
    postal = _one(
        conn,
        "INSERT INTO mdm.postal_codes (postal_code, municipality, created_at, updated_at) "
        "VALUES ('9999', 'Twintigdorp', now(), now()) RETURNING id",
    )
    # The empty organisation row of the brand, with an address of its own — the
    # tenant_id is the owner, as `organization_service` writes it (the seam).
    conn.execute(
        text(
            "INSERT INTO mdm.addresses (tenant_id, organization_id, street, house_number, "
            "postal_code_id, created_at, updated_at) VALUES "
            "(:brand, :brand, 'Merkstraat', '1', :pc, now(), now())"
        ),
        {"brand": brand, "pc": postal},
    )
    conn.execute(
        text("INSERT INTO mdm.tenant_modules (tenant_id, module_code) VALUES (:brand, 'cms')"),
        {"brand": brand},
    )
    conn.execute(
        text(
            "INSERT INTO kernel_tenant_settings (tenant_id, key, value) "
            "VALUES (:brand, 'tagline', 'Twintig')"
        ),
        {"brand": brand},
    )
    user = _one(
        conn,
        "INSERT INTO auth.users (email, is_active, created_at, updated_at) "
        "VALUES ('cr20@example.org', true, now(), now()) RETURNING id",
    )
    conn.execute(
        text(
            "INSERT INTO auth.user_roles (user_id, role_code, tenant_id, created_at) "
            "VALUES (:user, 'ADMIN', :brand, now())"
        ),
        {"user": user, "brand": brand},
    )
    # A role and a setting on the account, as migration 127 put roles on Raak vzw.
    conn.execute(
        text(
            "INSERT INTO auth.user_roles (user_id, role_code, tenant_id, created_at) "
            "VALUES (:user, 'ACCOUNT_ADMIN', :firm, now())"
        ),
        {"user": user, "firm": firm},
    )
    conn.execute(
        text(
            "INSERT INTO kernel_tenant_settings (tenant_id, key, value) "
            "VALUES (:firm, 'tagline', 'Op het account')"
        ),
        {"firm": firm},
    )
    person = _one(
        conn,
        "INSERT INTO mdm.persons (tenant_id, first_name, last_name, created_at, updated_at) "
        "VALUES (2, 'Kring', 'Lid', now(), now()) RETURNING id",
    )
    conn.execute(
        text(
            "INSERT INTO mdm.organization_persons (tenant_id, organization_id, person_id, "
            "relation_type, start_date) VALUES (2, :platform, :person, 'BOARD_MEETING', "
            "'2026-01-01')"
        ),
        {"platform": platform, "person": person},
    )
    conn.execute(
        text(
            "INSERT INTO cms.cms_pages (tenant_id, title, slug, content, is_published, "
            "show_in_nav, is_home, sort_order, created_at, updated_at) VALUES "
            "(2, 'Sites', 'sites-cr20', '<p>{{tenants:firma-cr20}}</p>', true, false, false, "
            "0, now(), now()), "
            "(2, 'Alle sites', 'alle-sites-cr20', '<p>{{tenants}}</p>', true, false, false, "
            "0, now(), now())"
        )
    )
    # Test 11 reads the circles of the two departments as this user.
    conn.execute(
        text(
            "INSERT INTO auth.user_roles (user_id, role_code, tenant_id, created_at) "
            "VALUES (:user, 'ADMIN', 2, now()), (:user, 'ADMIN', 3, now())"
        ),
        {"user": user},
    )


def test_the_tenants_carry_the_ids_of_their_rows(migrated_url):
    with migrated_url.connect() as conn:
        brand = conn.execute(
            text(
                "SELECT t.id, t.kind, t.site_name, t.account_id, t.organization_id, a.name "
                "FROM mdm.tenants t JOIN mdm.organizations a ON a.id = t.account_id "
                "WHERE t.code = 'merk-cr20'"
            )
        ).one()
        firm = _one(conn, "SELECT id FROM mdm.organizations WHERE name = 'Firma Twintig'")
        assert (brand.kind, brand.site_name, brand.name) == (
            "BEDRIJF",
            "Merk Twintig",
            "Firma Twintig",
        )
        assert brand.account_id == firm and brand.organization_id == firm
        # The seed's own tenants: each its own party, the same id.
        millegem = conn.execute(
            text("SELECT id, organization_id FROM mdm.tenants WHERE code = 'raakmillegem'")
        ).one()
        assert millegem.organization_id == millegem.id
        assert _one(conn, "SELECT count(*) FROM mdm.tenants WHERE kind = 'PLATFORM'") == 1


def test_a_new_tenant_never_takes_the_id_of_an_organisation(migrated_url):
    """dev2's read of #2155: the seam rows carry an organisation's id in
    `tenant_id` until CR-26, so the tenants' own sequence starts past every
    organisation id. Broken on purpose: `setval` back to `max(tenants.id)` → the
    next tenant id is an organisation's and this fails."""
    with migrated_url.connect() as conn:
        last = _one(conn, "SELECT last_value FROM mdm.tenants_id_seq")
        assert last >= _one(conn, "SELECT max(id) FROM mdm.organizations")


def test_the_organisation_keeps_the_party_only(migrated_url):
    with migrated_url.connect() as conn:
        columns = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'mdm' AND table_name = 'organizations'"
                )
            )
        }
        assert "name" in columns and "legal_form" in columns
        assert not columns & {
            "org_type",
            "role",
            "code",
            "kind",
            "parent_id",
            "site_organization_id",
            "site_name",
        }
        assert _one(conn, "SELECT to_regclass('mdm.organization_type_codes')") is None


def test_a_borrowed_data_row_is_soft_deleted_with_its_address(migrated_url):
    with migrated_url.connect() as conn:
        row = conn.execute(
            text(
                "SELECT o.deleted_at IS NOT NULL AS gone FROM mdm.organizations o "
                "JOIN mdm.tenants t ON t.id = o.id WHERE t.code = 'merk-cr20'"
            )
        ).one()
        assert row.gone, "the brand's empty organisation row is soft-deleted"
        assert (
            _one(
                conn,
                "SELECT count(*) FROM mdm.addresses WHERE street = 'Merkstraat' "
                "AND deleted_at IS NOT NULL",
            )
            == 1
        )
        # The tenant itself stays, active.
        assert _one(conn, "SELECT is_active FROM mdm.tenants WHERE code = 'merk-cr20'") is True


def test_the_circle_hangs_on_the_party_its_tenant_shows(migrated_url):
    with migrated_url.connect() as conn:
        relation = conn.execute(
            text(
                "SELECT r.organization_id, t.organization_id AS shown FROM mdm.organization_persons r "
                "JOIN mdm.tenants t ON t.id = r.tenant_id JOIN mdm.persons p ON p.id = r.person_id "
                "WHERE p.first_name = 'Kring'"
            )
        ).one()
        assert relation.organization_id == relation.shown


def test_the_sites_placeholder_names_a_tenant(migrated_url):
    with migrated_url.connect() as conn:
        content = _one(conn, "SELECT content FROM cms.cms_pages WHERE slug = 'sites-cr20'")
        assert content == "<p>{{tenants:merk-cr20}}</p>"


def test_settings_modules_and_roles_keep_their_tenant_and_gain_the_key(migrated_url):
    with migrated_url.connect() as conn:
        brand = _one(conn, "SELECT id FROM mdm.tenants WHERE code = 'merk-cr20'")
        assert (
            _one(
                conn,
                "SELECT value FROM kernel_tenant_settings WHERE tenant_id = :t AND key = 'tagline'",
                t=brand,
            )
            == "Twintig"
        )
        assert (
            _one(conn, "SELECT count(*) FROM mdm.tenant_modules WHERE tenant_id = :t", t=brand) == 1
        )
        assert _one(conn, "SELECT count(*) FROM auth.user_roles WHERE tenant_id = :t", t=brand) == 1
        keyed = {
            r[0]
            for r in conn.execute(
                text(
                    "SELECT conrelid::regclass::text FROM pg_constraint "
                    "WHERE contype = 'f' AND confrelid = 'mdm.tenants'::regclass"
                )
            )
        }
        assert {"kernel_tenant_settings", "auth.user_roles", "mdm.tenant_modules"} <= keyed
        assert "activities.registrations" in keyed and "mdm.persons" in keyed
        assert "mdm.addresses" not in keyed, "the seam carries no key (C4.8)"


def test_a_role_and_a_setting_on_an_account_are_removed(migrated_url):
    """Koen, 18 October 2026: "1a" — they opened nothing, and they would refuse
    the key. The brand's own role and setting stay (the test above)."""
    with migrated_url.connect() as conn:
        firm = _one(conn, "SELECT id FROM mdm.organizations WHERE name = 'Firma Twintig'")
        assert _one(conn, "SELECT count(*) FROM auth.user_roles WHERE tenant_id = :f", f=firm) == 0
        assert (
            _one(conn, "SELECT count(*) FROM kernel_tenant_settings WHERE tenant_id = :f", f=firm)
            == 0
        )


def test_the_reporting_views_list_the_tenants(migrated_url):
    with migrated_url.connect() as conn:
        departments = {
            r[0] for r in conn.execute(text("SELECT id FROM mdm.tenants WHERE kind <> 'PLATFORM'"))
        }
        for view in ("d_payment_method", "d_payment_status", "d_membership_status"):
            listed = {
                r[0] for r in conn.execute(text(f"SELECT DISTINCT tenant_id FROM reporting.{view}"))
            }
            assert listed == departments, view
        assert _one(conn, "SELECT count(DISTINCT tenant_id) FROM reporting.d_date") == len(
            departments
        )


def test_an_organisation_address_in_the_seam_is_still_accepted(migrated_url):
    # Rolled back on leaving: test 11 reads the firm's footer after this.
    with migrated_url.connect() as conn:
        firm = _one(conn, "SELECT id FROM mdm.organizations WHERE name = 'Firma Twintig'")
        postal = _one(conn, "SELECT id FROM mdm.postal_codes ORDER BY id LIMIT 1")
        conn.execute(
            text(
                "INSERT INTO mdm.addresses (tenant_id, organization_id, street, house_number, "
                "postal_code_id, created_at, updated_at) VALUES "
                "(:firm, :firm, 'Firmastraat', '2', :pc, now(), now())"
            ),
            {"firm": firm, "pc": postal},
        )


#: Koen, 18 October 2026: "2a" — a site under no account becomes its own
#: account, so "Overige" goes: its card stands under its organisation's name.
OVERIGE_BECOMES = {"Los Twintig": "Losse Vereniging"}
_GROUP = re.compile(r'  <h3>(.*?)</h3>\n  <div class="grid[^"]*">\n    (.*?)\n  </div>\n  \n')
_CARD = re.compile(r"<a [^>]*data-site-card.*?</a>")


def _groups(html: str) -> tuple[str, list[tuple[str, str]], str]:
    """The sites placeholder's cards as (heading, cards) per group, with the
    page around them."""
    first = _GROUP.search(html)
    groups = [(m.group(1), m.group(2)) for m in _GROUP.finditer(html)]
    last = list(_GROUP.finditer(html))[-1]
    return html[: first.start()], groups, html[last.end() :]


def _without_overige(html: str) -> str:
    """What the page rendered before 313, with "Overige" as Koen's "2a" says:
    each card under the name of its own organisation, the groups by name."""
    before, groups, after = _groups(html)
    renamed = [g for g in groups if g[0] != "Overige"]
    for heading, cards in groups:
        if heading == "Overige":
            for card in _CARD.findall(cards):
                name = re.search(r'font-semibold !text-ink">(.*?)</span>', card).group(1)
                renamed.append((OVERIGE_BECOMES[name], card))
    renamed.sort(key=lambda group: group[0].casefold())
    return (
        before
        + "".join(
            f'  <h3>{heading}</h3>\n  <div class="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-3 mb-8">\n'
            f"    {cards}\n  </div>\n  \n"
            for heading, cards in renamed
        )
        + after
    )


def test_every_site_renders_as_before(head_url, tmp_path):
    """C6 test 11: per tenant the header and footer of the site shell, both
    sites placeholders and the meeting circle render after 313 what the code
    before 313 rendered on the same cases, with one exception named: "Overige"
    (Koen's "2a"). The platform without an account of its own stays out of the
    sites placeholder, as before (R4).

    `cr20_rendered_before.json` is the code before 313 (commit 7c389256, the
    merge-base of #2155) rendering this file's cases on revision 312, through
    `tests/_cr20_render.py`, the same file that renders the after here — on
    the head, since the code under test reads its schema: CR-26's migration 314
    (#2020) is held to the same output. To make
    it again: a worktree of that commit with these two files copied in, the chain
    to its head, `_write_the_cases`, then `python -m tests._cr20_render <url> <file>`.

    Proven red, additively (put back): a step in migration 313 appending "X" to
    the brand's `site_name` → its header differs (a trailing space is not
    enough: the shell strips it); the platform let through when it is its own
    account → the all-sites page gains its card.
    """
    url = head_url.url.render_as_string(hide_password=False)
    subprocess.run(
        [sys.executable, "-m", "tests._cr20_render", url, str(tmp_path / "after.json")],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
        capture_output=True,
        text=True,
    )
    after = json.loads((tmp_path / "after.json").read_text())
    before = json.loads((Path(__file__).parent / "cr20_rendered_before.json").read_text())

    assert sorted(after) == sorted(before)
    assert "Kring Lid" in after["raakmillegem"]["circle"], "the circle renders its member"
    assert "Firma Twintig" in after["merk-cr20"]["footer"], "the brand shows the firm's data"
    for code, parts in before.items():
        for part, html in parts.items():
            if (code, part) == ("raakmillegem", "alle-sites-cr20"):
                assert "<h3>Overige</h3>" in html, "the snapshot holds the exception"
                html = _without_overige(html)
            assert after[code][part] == html, (code, part)
