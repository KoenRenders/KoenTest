"""The legend of the page editor shows every placeholder's example in WORDS
(#1615).

Found by Koen on HDEV: under "Beschikbare placeholders" the example of
`{{tenants}}` and `{{tenants:<code>}}` was the raw HTML of the site cards —
`<div hx-boost="false" data-tenant-sites> <h3>…` — several lines long. Since
#1566 that placeholder renders a template with markup; #1567 gave the form
button a preview in words, the sites kept their rendered output.

The rule, for every placeholder there is and will be: the legend never shows
markup. `cms.service.placeholders()` reduces whatever a code renders to its
text; the sites say who they are (the accounts with their site names).

Measured on master `63677671` before the repair: two of the nine examples
were markup — `{{tenants}}` (846 characters, starting `<div hx-boost="false"
data-tenant-sites>`) and `{{tenants:raak}}` (833, a tenant's code since CR-20) — and the bar's description
ended "na het streepje". These tests cannot run against that code as they
stand (they pass the request's session, which `placeholders()` did not take);
the measurement was taken with the same check, `"<" in preview`, on the old
function.
"""

from __future__ import annotations

import re

import pytest

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.domains.cms import service
from app.domains.cms.api import CmsPage
from app.domains.mdm.api import create_organization
from tests._sites import new_site
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


def _previews(db) -> dict[str, str]:
    listed = service.placeholders(db)
    assert len(listed) >= 9, f"only {len(listed)} placeholders listed"
    return {entry["code"]: entry["preview"] for entry in listed}


@pytest.fixture
def network(db_session):
    """Two accounts next to the seed's own: one with an active and a closed
    site, one with a single site."""
    first = create_organization(db_session, name="Account Vijf")
    second = create_organization(db_session, name="Account Zes")
    new_site(db_session, name="Clubhuis", code="clubhuis-1615", account_id=first.id)
    new_site(db_session, name="Atelier", code="atelier-1615", account_id=first.id)
    closed = new_site(db_session, name="Gesloten Club", code="gesloten-1615", account_id=first.id)
    closed.is_active = False
    new_site(db_session, name="Werkplaats", code="werkplaats-1615", account_id=second.id)
    db_session.commit()


def test_no_example_in_the_legend_contains_markup(db_session, network):
    for code, preview in _previews(db_session).items():
        assert "<" not in preview and ">" not in preview, f"{code}: {preview[:120]!r}"
        assert "&lt;" not in preview and "hx-boost" not in preview, f"{code}: {preview[:120]!r}"
        assert preview.strip(), f"{code} has no example at all"
        assert "\n" not in preview, f"{code}: an example of several lines"


def test_the_sites_example_names_the_accounts_with_their_sites(db_session, network):
    from app.domains.cms.render import sites_in_words

    everything = _previews(db_session)["{{tenants}}"]
    groups = dict(part.split(": ", 1) for part in everything.split(" · "))
    assert groups["Account Vijf"] == "Atelier, Clubhuis", "the active sites by name, in order"
    assert groups["Account Zes"] == "Werkplaats"
    assert "Raak Millegem" in groups["Raak"], "the seed's own account and site"
    assert "Gesloten Club" not in everything, "a closed site is no example"

    assert sites_in_words("clubhuis-1615", db_session) == "Atelier, Clubhuis", (
        "one tenant's account: its sites, no heading (CR-20 F10)"
    )
    assert sites_in_words("bestaat-niet", db_session) == ""
    # The legend's own example code is a tenant of the seed.
    one = _previews(db_session)["{{tenants:raakmillegem}}"]
    assert "Raak Millegem" in one and ":" not in one


def test_an_unknown_tenant_has_no_names_and_the_legend_says_so(db_session, monkeypatch):
    """CR-20 F10: the parameter names a tenant; a code no tenant has lists nothing."""
    from app.domains.cms import render

    assert render.sites_in_words("geen-tenant-1615", db_session) == ""
    # The legend's example, made empty: the example says so in words.
    monkeypatch.setattr(render, "sites_in_words", lambda code, db=None: "")
    assert (
        _previews(db_session)["{{tenants:raakmillegem}}"] == "geen sites: dit account heeft er geen"
    )


def test_the_form_buttons_bar_is_called_what_it_is():
    labels = {entry["code"]: entry["label"] for entry in service.placeholders()}
    assert labels["{{form:berichten|Contacteer ons}}"].endswith("na het verticale streepje (|)")
    assert not any(label.endswith("na het streepje") for label in labels.values())


def test_the_values_keep_their_example(db_session, network):
    """What was right stays right: an amount, a date, the button in brackets."""
    previews = _previews(db_session)
    assert re.fullmatch(r"€\s?\d+,\d{2}", previews["{{membership_price_full}}"]), previews
    assert re.fullmatch(r"\d{1,2} [a-z]+", previews["{{half_price_start}}"]), previews
    assert previews["{{form:berichten|Contacteer ons}}"] in (
        "[Contacteer ons]",
        "geen knop: dit formulier kan niets ontvangen",
    )


def test_the_page_editor_shows_the_legend_in_words(client, db_session, network):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))
    page = db_session.query(CmsPage).first()
    html = client.get(f"/admin/paginas/{page.id}").text
    assert "data-placeholders" in html, "the legend is not on the page editor"
    legend = html[html.index("data-placeholders") :]
    legend = legend[: legend.index("</dl>")]
    assert "Account Vijf: Atelier, Clubhuis" in legend
    assert "data-tenant-sites" not in legend and "&lt;" not in legend
    assert legend.count("<dt") == len(service.placeholders(db_session))
