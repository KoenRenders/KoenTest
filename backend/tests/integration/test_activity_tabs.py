"""CR-11 pilot A, K6 (#1560) — the activity's summary and its two list tabs.

Block 8 (Koen, 4 October 2026; `docs/design-system-end-state.md` §2.2, §3.10):

- **Gegevens** carries the summary card: the state, Inschrijvingen · Deelnemers
  · Openstaand, the public link with its copy button. The list tabs carry
  neither card nor strip; the card "Publicatie" is gone.
- **Inschrijvingen** is one table with a collapsible group row per component,
  Exporteren under the group's `⋯`. **A row is the way in** (#1636, Koen,
  5 October 2026; CR-11 Q75): it links to the registration's page, whose way
  back names the row, so the tab brings that row into view again. It unfolds
  nowhere — K6 showed the same data three times. The row carries Bedrag and
  Saldo, one action and `⋯` with the jumps. The toolbar filters on
  *Alle | Openstaand (n)* and searches.
- **Betalingen**, embedded: the row opens the booking's page as on the main
  list (#1636), with the tab as its way back; the tab has its own address; the
  activity's figures band is gone (the household's stays until pilot B).

What only a browser shows — the card's size, the copy, the click on a row —
is in `tests_e2e/test_activity_tabs.py`.

Proven red (each on this branch, restored after):
- the summary rendered on the Inschrijvingen tab → the no-card test fails (and
  the gate, `tests/test_record_tab_gate.py`);
- "Openstaand" shown without asking who may see payments → the role test fails;
- `rij=` left out of a row's way back → the way-back test fails;
- the *Openstaand* filter ignored → the filter test fails;
- a registration's state read from one booking instead of all → the state test
  fails;
- #1636, against master `92866b83`: the row test fails on "data-row-toggle"
  (the row unfolds) and the contact count on 2 where 1 is asked; `rij=` left
  out of a row's way back → the way-back test; the booking of "Betaling
  openen" taken as the newest instead of the oldest open one → the menu test;
  "Bevestig" shown with two open bookings → the two-bookings test;
- the push of the tab's own address removed → the address test fails;
- the band's condition back to `embedded` → the band test fails.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import unquote

import pytest

from app.domains.activities.api import (
    ActivityProduct,
    ActivityStatus,
    ActivitySubRegistration,
    Registration,
    RegistrationItem,
)
from app.domains.auth.api import SESSION_COOKIE, User, UserRole, make_session_value
from app.domains.payment.api import (
    PaymentRecord,
    aggregate,
    registration_balance_by_activity,
    registration_payment_states,
)
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

pytestmark = pytest.mark.ui_serverrendered

T0 = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def _login(client, db) -> None:
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).one()
    if not db.query(UserRole).filter_by(user_id=user.id, role_code="FINANCE").first():
        db.add(UserRole(user_id=user.id, role_code="FINANCE"))
    db.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _registration(db, activity, component, product, name, quantity, minutes):
    reg = Registration(
        contact_name=name,
        contact_email=f"{name.split()[0].lower()}@example.org",
        phone="0470000000",
        activity_id=activity.id,
        component_id=component.id,
        registration_type="INDIVIDUAL",
        registered_at=T0 + timedelta(minutes=minutes),
    )
    db.add(reg)
    db.flush()
    db.add(RegistrationItem(registration_id=reg.id, product_id=product.id, quantity=quantity))
    db.flush()
    return reg


def _record(db, reg, amount, *, status="pending", paid=None, minutes=0, **extra):
    rec = PaymentRecord(
        payable_type="registration",
        payable_id=reg.id,
        amount=Decimal(amount),
        amount_paid=None if paid is None else Decimal(paid),
        method="transfer",
        status=status,
        created_at=T0 + timedelta(minutes=minutes),
        **extra,
    )
    db.add(rec)
    db.flush()
    return rec


@pytest.fixture
def world(db_session):
    """One published activity with two components.

    Wandeling: Bram (2 × product, open € 20), An (1 ×, paid € 10, and a refund
    of € 4 still to pay out — two bookings). Molen: Cas (3 ×, paid € 30).
    Open balance: 20 + 0 + (−4) = € 16; participants 2 + 1 + 3 = 6.
    """
    db = db_session
    activity, wandeling, product = seed_activity_with_product(db, price="10.00")
    wandeling.name = "Wandeling"
    molen = ActivitySubRegistration(
        activity_id=activity.id,
        name="Molen",
        registration_type_code="INDIVIDUAL",
        price=Decimal("0"),
        is_free=True,
    )
    db.add(molen)
    db.flush()
    molen_product = ActivityProduct(component_id=molen.id, name="Rondleiding", price=Decimal("10"))
    db.add(molen_product)
    db.flush()
    bram = _registration(db, activity, wandeling, product, "Bram Voorbeeld", 2, 1)
    an = _registration(db, activity, wandeling, product, "An Voorbeeld", 1, 2)
    cas = _registration(db, activity, molen, molen_product, "Cas Voorbeeld", 3, 3)
    r_bram = _record(db, bram, "20.00", minutes=1)
    r_an = _record(db, an, "10.00", status="paid", paid="10.00", minutes=2)
    r_refund = _record(db, an, "-4.00", minutes=3, type="refund", refund_of_id=r_an.id)
    r_cas = _record(db, cas, "30.00", status="paid", paid="30.00", minutes=4)
    activity.status = ActivityStatus.PUBLISHED
    db.commit()
    return {
        "activity": activity,
        "wandeling": wandeling,
        "molen": molen,
        "bram": bram,
        "an": an,
        "cas": cas,
        "records": {"bram": r_bram, "an": r_an, "refund": r_refund, "cas": r_cas},
    }


def _base(world) -> str:
    return f"/admin/activiteiten/{world['activity'].id}"


def _figures(html: str) -> dict[str, str]:
    card = html[html.index("data-summary-card") :]
    return dict(
        re.findall(
            r"<div data-summary-figure>\s*<dt[^>]*>([^<]+)</dt>\s*<dd[^>]*>([^<]+)</dd>", card
        )
    )


# ── Gegevens: the summary card ───────────────────────────────────────────────


def test_gegevens_carries_the_summary_card(client, db_session, world):
    _login(client, db_session)
    html = client.get(_base(world)).text
    assert html.count("data-summary-card") == 1
    card = html[html.index("data-summary-card") :]
    assert ">Gepubliceerd<" in card[: card.index("data-summary-figures")]
    assert _figures(html) == {"Inschrijvingen": "3", "Deelnemers": "6", "Openstaand": "€ 16,00"}
    # The open balance is not zero: the warning tone, and on that figure only.
    assert card.count("text-brand-warning") == 1
    # The public link, with the kit's copy button on the same address.
    link = re.search(r'data-summary-link[^>]* href="([^"]+)"', card).group(1)
    assert link.endswith(f"/activiteiten/{world['activity'].slug or world['activity'].id}")
    assert f'data-copy="{link}"' in card
    # The card "Publicatie" is gone, with its three headings.
    for old in (">Publicatie<", ">Deel de activiteit<", ">Toegang<"):
        assert old not in html, old


def test_the_open_balance_is_the_sum_the_payments_list_makes(db_session, world):
    """One aggregate row on the card, the same sum as `aggregate` over the
    activity's bookings — the card and the Betalingen tab cannot disagree."""
    records = list(world["records"].values())
    assert registration_balance_by_activity(db_session, world["activity"].id) == Decimal("16.00")
    assert aggregate(records)["saldo"] == Decimal("16.00")


def test_a_settled_activity_shows_its_balance_without_the_warning(client, db_session, world):
    for rec in db_session.query(PaymentRecord).all():
        rec.amount_paid = rec.amount
        rec.status = "paid"
    db_session.commit()
    _login(client, db_session)
    html = client.get(_base(world)).text
    assert _figures(html)["Openstaand"] == "€ 0,00"
    assert (
        "text-brand-warning" not in html[html.index("data-summary-card") :].split("</section>")[0]
    )


def test_who_may_not_see_payments_gets_no_open_balance(client, db_session, world, monkeypatch):
    """#544: "Openstaand" is money; it goes to who gets the Betalingen tab. Every
    role that reaches this page may see payments today, so the answer is turned
    off at its one source — the card must follow it, as the tab does."""
    import app.domains.auth.api as auth_api

    monkeypatch.setattr(auth_api, "may_view_payments", lambda db, email: False)
    _login(client, db_session)
    html = client.get(_base(world)).text
    assert f'href="{_base(world)}/betalingen"' not in html
    assert _figures(html) == {"Inschrijvingen": "3", "Deelnemers": "6"}


def test_a_draft_has_no_public_link_to_copy(client, db_session, world):
    world["activity"].status = ActivityStatus.DRAFT
    db_session.commit()
    _login(client, db_session)
    card = client.get(_base(world)).text.split("data-summary-card")[1].split("</section>")[0]
    assert ">Concept<" in card
    assert "data-summary-action" not in card and "data-copy" not in card


def test_the_occupancy_stands_on_the_components_row(client, db_session, world):
    world["wandeling"].max_participants = 20
    db_session.commit()
    _login(client, db_session)
    html = client.get(_base(world)).text
    # #1559 shows it on the component: Bram 2 + An 1, of 20.
    assert "3 / 20" in html


def test_the_list_tabs_carry_no_summary(client, db_session, world):
    _login(client, db_session)
    for tab in ("inschrijvingen", "betalingen"):
        html = client.get(f"{_base(world)}/{tab}").text
        assert "data-summary-card" not in html, tab
        # The head and the tabs are the same on every tab.
        assert "data-record-head" in html and f'href="{_base(world)}/betalingen"' in html
    # And the activity's Betalingen tab lost its figures band (K1 kept it here
    # until the summary existed).
    assert "kpi-strip" not in client.get(f"{_base(world)}/betalingen").text


# ── Inschrijvingen: one table, groups, the unfold ────────────────────────────


def _groups(html: str) -> list[tuple[str, str]]:
    return re.findall(
        r"<tr data-group-row.*?<span>([^<]+?) <span data-group-count[^>]*>\((\d+)\)</span>",
        html,
        re.S,
    )


def _row_names(html: str) -> list[str]:
    return re.findall(r"data-row-link[^>]*>([^<]+)</a>", html)


def _row(html: str, key: int) -> str:
    """One row of a kit table, by its key."""
    return re.search(rf'<tr data-row data-row-key="{key}".*?</tr>', html, re.S).group(0)


def _menu(row: str) -> dict[str, str]:
    """The row's `⋯`: label → href."""
    return {
        label.strip(): href
        for href, label in re.findall(r'role="menuitem" href="([^"]+)"[^>]*>([^<]+)</a>', row)
    }


# What an unfolding row left in the page (the kit's own script still reads
# `dataset.openRow`, the row a visitor came back to — that is no disclosure).
NO_DISCLOSURE = ("data-row-toggle", "data-row-detail", "data-row-part", "openRow ===")


def test_the_registrations_are_one_table_with_a_group_row_per_component(client, db_session, world):
    _login(client, db_session)
    html = client.get(f"{_base(world)}/inschrijvingen").text
    assert html.count("<table") == 1
    assert _groups(html) == [("Wandeling", "2"), ("Molen", "1")]
    assert _row_names(html) == ["Bram Voorbeeld", "An Voorbeeld", "Cas Voorbeeld"]
    # Exporteren under each group's ⋯ — not a button in a card head.
    for component in (world["wandeling"], world["molen"]):
        assert f'role="menuitem" href="{_base(world)}/onderdelen/{component.id}/export"' in html
    assert ">Export<" not in html
    # The embedded toolbar: status filter, search, count — no title, no figures.
    assert 'id="reg-filter"' in html and "data-status-filter" in html
    assert ">1–3 van 3<" in html.replace("\n", "")
    assert "data-figures" not in html and "data-filters-button" not in html
    # The tab's one primary button stays.
    assert f'href="{_base(world)}/inschrijvingen/nieuw"' in html


def test_a_row_shows_its_payment_state_from_all_its_bookings(client, db_session, world):
    _login(client, db_session)
    html = client.get(f"{_base(world)}/inschrijvingen").text
    rows = dict(zip(_row_names(html), re.findall(r'<td data-cell="status".*?</td>', html, re.S)))
    assert "Openstaand" in rows["Bram Voorbeeld"]
    # An paid her booking, but her refund is still to pay out: money has to move.
    assert "Openstaand" in rows["An Voorbeeld"] and "Vereffend" not in rows["An Voorbeeld"]
    assert "Vereffend" in rows["Cas Voorbeeld"]
    states = registration_payment_states(
        db_session, [world["bram"].id, world["an"].id, world["cas"].id, 999_999]
    )
    assert {k: v["state"] for k, v in states.items()} == {
        world["bram"].id: "open",
        world["an"].id: "open",
        world["cas"].id: "settled",
    }
    assert states[world["an"].id]["saldo"] == Decimal("-4.00")


def test_a_row_is_the_way_in_and_unfolds_nowhere(client, db_session, world):
    """#1636. Red against master: the row carries `data-row-toggle` and its
    contact stands twice on the page (the row and the unfolded row)."""
    _login(client, db_session)
    tab = f"{_base(world)}/inschrijvingen"
    html = client.get(tab).text
    for trace in NO_DISCLOSURE:
        assert trace not in html, f"a disclosure in the table: {trace}"
    # Every row links to its registration, and nothing says "Bewerken".
    assert len(_row_names(html)) == 3
    row = _row(html, world["bram"].id)
    assert f'href="/admin/inschrijvingen/{world["bram"].id}?terug=' in row
    assert "Bewerken" not in row
    # What the row says, it says ONCE on the page.
    assert html.count(">bram@example.org<") == 1
    assert html.count("2 × Testproduct") == 1
    # Bedrag and Saldo are columns of the table.
    heads = re.findall(r'<th scope="col" data-cell="([a-z]+)"', html)
    assert heads == ["name", "context", "date", "more", "amount", "extra", "status", "actions"]
    assert ">Bedrag<" in html.replace("\n", "").replace("  ", "") or "Bedrag" in html
    cells = dict(re.findall(r'<td data-cell="(amount|extra)"[^>]*>(.*?)</td>', row, re.S))
    assert "€ 20,00" in cells["amount"]
    assert "€ 20,00" in cells["extra"] and "text-brand-warning" in cells["extra"], (
        "orange when not zero"
    )
    # A settled registration: the balance is zero and carries no warning.
    settled = dict(
        re.findall(
            r'<td data-cell="(amount|extra)"[^>]*>(.*?)</td>', _row(html, world["cas"].id), re.S
        )
    )
    assert "€ 30,00" in settled["amount"] and "€ 0,00" in settled["extra"]
    assert "text-brand-warning" not in settled["extra"]


def test_the_rows_menu_carries_the_jumps_and_its_one_action(client, db_session, world):
    """#1636: "Inschrijving openen" and "Betaling openen" under `⋯`; "Bevestig"
    as the one action where exactly one booking is open. "Betaling openen"
    leads to the oldest booking that is still open, else to the oldest."""
    _login(client, db_session)
    tab = f"{_base(world)}/inschrijvingen"
    html = client.get(tab).text
    records = world["records"]
    expected = {
        # Bram: one booking, open.
        "bram": (records["bram"].id, "Als volledig betaald bevestigen?"),
        # An: paid, and a refund still to pay out — the refund is the open one.
        "an": (records["refund"].id, "Als volledig terugbetaald bevestigen?"),
        # Cas: settled — the oldest booking, and nothing to confirm.
        "cas": (records["cas"].id, None),
    }
    for who, (booking, question) in expected.items():
        row = _row(html, world[who].id)
        menu = _menu(row)
        assert list(menu) == ["Inschrijving openen", "Betaling openen"], (who, menu)
        back = f"{tab}?rij={world[who].id}"
        assert unquote(menu["Inschrijving openen"]) == (
            f"/admin/inschrijvingen/{world[who].id}?terug={back}"
        )
        assert unquote(menu["Betaling openen"]) == f"/admin/betalingen/{booking}?terug={back}"
        action = re.search(r"<button[^>]*data-row-action[^>]*>", row)
        if question is None:
            assert action is None, f"{who}: an action on a settled registration"
        else:
            assert action and f'hx-post="/admin/betalingen/{booking}/bevestigen"' in action.group(0)
            assert f'data-confirm="{question}"' in action.group(0)
    # The booking's page leads back to the tab, to the row.
    page = client.get(_menu(_row(html, world["bram"].id))["Betaling openen"]).text
    assert f"{tab}?rij={world['bram'].id}".replace("&", "&amp;") in page


def test_two_open_bookings_get_no_action_and_the_oldest_opens(client, db_session, world):
    """A click may not confirm one of two bookings unseen."""
    second = _record(db_session, world["bram"], "5.00", minutes=9)
    db_session.commit()
    _login(client, db_session)
    row = _row(client.get(f"{_base(world)}/inschrijvingen").text, world["bram"].id)
    assert not re.search(r"<button[^>]*data-row-action", row)
    first = world["records"]["bram"].id
    assert f"/admin/betalingen/{first}?terug=" in _menu(row)["Betaling openen"]
    states = registration_payment_states(db_session, [world["bram"].id])[world["bram"].id]
    assert (states["booking_id"], states["open_booking_ids"]) == (first, [first, second.id])


def test_who_may_not_confirm_gets_no_action(client, db_session, world):
    """`may_mutate_payments`: an ADMIN without FINANCE sees the jumps, not "Bevestig"."""
    user = User(email="admin-1636@example.org", is_active=True)
    db_session.add(user)
    db_session.flush()
    db_session.add(UserRole(user_id=user.id, role_code="ADMIN"))
    db_session.commit()
    client.cookies.set(SESSION_COOKIE, make_session_value(user.email))
    response = client.get(f"{_base(world)}/inschrijvingen")
    assert response.status_code == 200
    assert not re.search(r"<button[^>]*data-row-action", response.text)
    assert "Inschrijving openen" in _menu(_row(response.text, world["bram"].id))
    # The same page for who may: the action is there.
    _login(client, db_session)
    assert re.search(
        r"<button[^>]*data-row-action", client.get(f"{_base(world)}/inschrijvingen").text
    )


def test_the_way_back_from_a_registration_lands_on_its_row(client, db_session, world):
    _login(client, db_session)
    tab = f"{_base(world)}/inschrijvingen"
    html = client.get(f"{tab}?zicht=openstaand&sort=-naam").text
    href = re.search(
        rf'href="(/admin/inschrijvingen/{world["bram"].id}\?terug=[^"]+)" data-row-link', html
    ).group(1)
    back = unquote(href.split("terug=", 1)[1])
    # The list as it was left — filter and sort — and the row it was opened from.
    assert back == f"{tab}?zicht=openstaand&sort=-naam&rij={world['bram'].id}"
    # The registration's page leads back there…
    assert back.replace("&", "&amp;") in client.get(href).text
    # …and the tab names that row again (the kit brings it into view and gives
    # its link the focus), with the same filter and sort.
    again = client.get(back).text
    assert f'data-open-row="{world["bram"].id}"' in again
    assert _row_names(again) == ["Bram Voorbeeld", "An Voorbeeld"]
    # A row that is not on the list is not named.
    assert 'data-open-row="' not in client.get(f"{tab}?rij=999999").text
    assert 'data-open-row="' not in client.get(f"{tab}?rij=');alert(1)//").text


def test_the_toolbar_filters_on_openstaand_and_searches(client, db_session, world):
    _login(client, db_session)
    lijst = f"{_base(world)}/inschrijvingen/lijst"
    # Openstaand: Bram and An; the group without an open registration is gone.
    html = client.get(f"{lijst}?zicht=openstaand", headers={"X-Raak-Filter": "1"})
    assert _row_names(html.text) == ["Bram Voorbeeld", "An Voorbeeld"]
    assert _groups(html.text) == [("Wandeling", "2")]
    # The fragment refreshes the toolbar's count and the count on the segment…
    assert 'id="reg-filter-count" hx-swap-oob="true"' in html.text
    assert re.search(r'id="reg-filter-n-openstaand"[^>]*>\(2\)<', html.text)
    # …and the address that holds the state is the TAB's.
    assert html.headers["HX-Push-Url"] == f"{_base(world)}/inschrijvingen?zicht=openstaand"
    # A search narrows the list and the count on Openstaand with it.
    html = client.get(f"{lijst}?q=cas").text
    assert _row_names(html) == ["Cas Voorbeeld"]
    assert re.search(r'id="reg-filter-n-openstaand"[^>]*>\(0\)<', html)
    # An empty list says why.
    html = client.get(f"{lijst}?q=niemand").text
    assert "<table" not in html and "Geen inschrijvingen gevonden voor “niemand”." in html
    assert ">0–0 van 0<" in html.replace("\n", "")


def test_the_sort_orders_inside_a_group(client, db_session, world):
    _login(client, db_session)
    tab = f"{_base(world)}/inschrijvingen"
    assert _row_names(client.get(f"{tab}?sort=naam").text)[:2] == ["An Voorbeeld", "Bram Voorbeeld"]
    assert _row_names(client.get(f"{tab}?sort=-naam").text)[:2] == [
        "Bram Voorbeeld",
        "An Voorbeeld",
    ]
    # The older pair of parameters still reads (a link from before K6).
    old = client.get(f"{tab}?sort=naam&richting=desc").text
    assert _row_names(old)[:2] == ["Bram Voorbeeld", "An Voorbeeld"]
    assert 'aria-sort="descending"' in old


# ── Betalingen, embedded: the row opens the booking, as on the list ─────────


def test_an_embedded_booking_opens_its_page_and_unfolds_nowhere(client, db_session, world):
    """#1636 (Koen's addition): a kit table has no inline disclosure, on a tab
    either. Red against master: `data-row-toggle` on every row of the tab."""
    _login(client, db_session)
    tab = f"{_base(world)}/betalingen"
    html = client.get(tab).text
    for trace in NO_DISCLOSURE:
        assert trace not in html, f"a disclosure in the table: {trace}"
    ids = {str(r.id) for r in world["records"].values()}
    assert set(re.findall(r'data-row-key="([^"]+)"', html)) == ids
    assert len(_row_names(html)) == 4
    bram = world["records"]["bram"].id
    # The row leads to the booking's page, and that page leads back to the TAB
    # with the booking named — so the way back lands on the row it left.
    href = re.search(rf'href="(/admin/betalingen/{bram}\?terug=[^"]+)" data-row-link', html).group(
        1
    )
    assert unquote(href.split("terug=", 1)[1]) == f"{tab}?boeking={bram}"
    assert f"{tab}?boeking={bram}" in client.get(href).text
    assert f'data-open-row="{bram}"' in client.get(f"{tab}?boeking={bram}").text
    # The list itself: the row is the way in there too (K2), back to the list.
    top = client.get("/admin/betalingen").text
    assert len(_row_names(top)) == 4 and 'data-open-row="' not in top


def test_the_embedded_tab_keeps_its_own_address(client, db_session, world):
    """A filter on the tab pushes the tab's address, not the payments list's —
    the scope is the path there, not a parameter."""
    _login(client, db_session)
    activity = world["activity"].id
    r = client.get(
        f"/admin/betalingen/lijst?zicht=openstaand&activiteit={activity}&scope_stil=1",
        headers={"X-Raak-Filter": "1"},
    )
    assert r.headers["HX-Push-Url"] == f"{_base(world)}/betalingen?zicht=openstaand"
    # The list's own push is untouched.
    r = client.get("/admin/betalingen/lijst?zicht=openstaand", headers={"X-Raak-Filter": "1"})
    assert r.headers["HX-Push-Url"] == "/admin/betalingen?zicht=openstaand"
    # And a reload of the pushed address shows the filtered tab under its head.
    html = client.get(f"{_base(world)}/betalingen?zicht=openstaand").text
    assert "data-record-head" in html
    shown = set(re.findall(r'data-row-key="([^"]+)"', html))
    assert str(world["records"]["cas"].id) not in shown and shown


def test_the_payments_tab_of_a_household_keeps_its_band(client, db_session, world):
    """Pilot B gives the household its summary; until then its Betalingen tab
    keeps the figures band the activity's lost."""
    from tests.conftest import create_test_family

    member, _person = create_test_family(db_session, email="gezin-k6@example.org")
    db_session.commit()
    _login(client, db_session)
    assert "kpi-strip" in client.get(f"/admin/leden/gezin/{member.id}/betalingen").text


def test_the_registrations_own_payments_tab_opens_the_booking_too(client, db_session, world):
    """#1636: the registration's page has a Betalingen tab on the same fragment
    as the activity's and the household's — its rows are the way in as well,
    and the booking's page leads back to that tab."""
    _login(client, db_session)
    tab = f"/admin/inschrijvingen/{world['an'].id}/betalingen"
    html = client.get(tab).text
    for trace in NO_DISCLOSURE:
        assert trace not in html, f"a disclosure in the table: {trace}"
    own = {str(world["records"]["an"].id), str(world["records"]["refund"].id)}
    assert set(re.findall(r'data-row-key="([^"]+)"', html)) == own
    booking = world["records"]["an"].id
    href = re.search(rf'href="(/admin/betalingen/{booking}\?terug=[^"]+)" data-row-link', html)
    assert href and unquote(href.group(1).split("terug=", 1)[1]) == f"{tab}?boeking={booking}"
