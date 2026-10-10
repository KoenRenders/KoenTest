"""The registrations table of a record's tab (CR-11 pilot A, K6 — #1560).

Block 8 (Koen, 4 October 2026; `docs/design-system-end-state.md` §2.2): the
registrations of an activity and of a household are **one table with a
collapsible group row** per component — per activity on the household.

**A row is the way in** (#1636, Koen, 5 October 2026; CR-11 Q75): it links to
the registration's own page and unfolds nowhere. It carries the amounts of its
bookings (Bedrag, Saldo), one action and a menu with the jumps — decided here.

One builder for both tabs (the shared `_inschrijvingen_groepen.html` renders
what it returns): the grouping is the caller's — data, not layout — and
everything a row shows is decided here, so neither route derives a state and
the template derives none either.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote, urlencode

from sqlalchemy.orm import Session

from app.i18n import _

#: The status filter of the tab: *Alle | Openstaand (n)*, as on Betalingen.
VIEWS = ("alle", "openstaand")

#: sort key in the URL → the key of `sorteer_inschrijvingen`. A leading "-" is
#: descending (the toolbar's form, K2).
SORT_KEYS = {"naam": "naam", "datum": "datum"}


def parse_sort(sort: str, direction: str = "") -> str:
    """The sort as the toolbar carries it ("naam", "-naam", "datum", "-datum"),
    from that form or from the older pair `sort` + `richting`. Anything unknown
    is the list's own order: oldest first."""
    key = sort.lstrip("-")
    if key not in SORT_KEYS:
        return "datum"
    descending = sort.startswith("-") or direction == "desc"
    return ("-" if descending else "") + key


def _state_query(view: str, q: str, sort: str) -> list[tuple[str, str]]:
    """The list's state as query pairs, defaults left out — the same address
    for the same list."""
    pairs = []
    if view != "alle":
        pairs.append(("zicht", view))
    if q:
        pairs.append(("q", q))
    if sort != "datum":
        pairs.append(("sort", sort))
    return pairs


def _matches(row: dict, needle: str) -> bool:
    haystack = " ".join(
        str(row.get(key) or "") for key in ("contact_name", "contact_email", "phone", "team_name")
    )
    return needle in haystack.casefold()


def registration_table(
    db: Session,
    groups: list[dict],
    *,
    page_url: str,
    fragment_url: str = "",
    view: str = "alle",
    q: str = "",
    sort: str = "datum",
    open_row: str = "",
    sub_is_component: bool = False,
    may_mutate: bool = False,
) -> dict[str, Any]:
    """Everything the registrations table shows, from `groups` of enriched
    registrations (`enrich_registration`).

    `groups`: [{name, regs, items?, link?}] — `items` the group row's `⋯`
    (Exporteren, Antwoorden), `link` its jump link ({label, href}).
    `page_url` is the tab's own address; a row's way back is that address with
    the list's state and `rij=<id>`, so the registration's page leads back to
    the row it was opened from. `fragment_url` is where a sort link asks the
    list alone; without one (the household's tab) the link is the page.
    `sub_is_component` puts the component's name under the contact's (the
    household groups by activity, so the component is not the group).
    `may_mutate` (the right `payment.manage`): whether the viewer may confirm a
    payment — the row's one action. `open_row` is the row a visitor came back
    to.

    The row's menu (#1636): "Inschrijving openen", "Betaling openen" — the
    oldest booking that is still open, else the oldest one — and "Antwoorden
    (n)" where the registration has answers, which opens the registration's
    page (the answers stand there only). "Bevestig" is the row's action only
    when the registration has exactly ONE open booking: with two, a click
    would confirm one of them unseen, so the booking's page is the way.
    """
    from app.domains.activities.models import Registration
    from app.domains.activities.service import sorteer_inschrijvingen
    from app.domains.forms.api import submission_views
    from app.domains.payment.api import registration_payment_states

    view = view if view in VIEWS else "alle"
    sort = parse_sort(sort)
    q = (q or "").strip()

    every = [reg for group in groups for reg in group["regs"]]
    ids = [reg["id"] for reg in every]
    payments = registration_payment_states(db, ids)
    # The answers of every row in one read; a registration whose link is still
    # open has none yet and says when they were asked.
    asked: dict[int, tuple[Any, Any]] = {}
    if ids:
        for reg_id, submission_id, token in (
            db.query(Registration.id, Registration.form_submission_id, Registration.answer_token)
            .filter(Registration.id.in_(ids))
            .execution_options(include_deleted=True)
        ):
            asked[reg_id] = (submission_id, token)
    answers = submission_views(db, [s for s, _t in asked.values() if s is not None])

    needle = q.casefold()
    searched = [reg for reg in every if not needle or _matches(reg, needle)]
    open_count = sum(1 for reg in searched if payments.get(reg["id"], {}).get("state") == "open")

    state = _state_query(view, q, sort)
    badges = {
        "open": {"label": _("Openstaand"), "tone": "yellow", "check": False},
        "settled": {"label": _("Vereffend"), "tone": "green", "check": True},
    }

    def _row(reg: dict) -> dict:
        payment = payments.get(reg["id"])
        submission_id, _token = asked.get(reg["id"], (None, None))
        back = quote(page_url + "?" + urlencode(state + [("rij", str(reg["id"]))]), safe="")
        page = f"/admin/inschrijvingen/{reg['id']}?terug={back}"
        own_answers = answers.get(submission_id, []) if submission_id is not None else []
        menu = [{"label": _("Inschrijving openen"), "href": page}]
        action = None
        if payment:
            booking = f"/admin/betalingen/{payment['booking_id']}"
            menu.append({"label": _("Betaling openen"), "href": f"{booking}?terug={back}"})
            if may_mutate and len(payment["open_booking_ids"]) == 1:
                # The answer of the confirm route is the payments list; this
                # list is another one, so the page is read again after it.
                action = {
                    "label": _("Bevestig"),
                    "attrs": f'hx-post="{booking}/bevestigen" hx-swap="none" '
                    'hx-on::after-request="if (event.detail.successful) window.location.reload()"',
                    "confirm": _("Als volledig terugbetaald bevestigen?")
                    if payment["open_booking_is_refund"]
                    else _("Als volledig betaald bevestigen?"),
                }
        if own_answers:
            menu.append(
                {
                    "label": _("Antwoorden (%(n)s)") % {"n": len(own_answers)},
                    "href": page,
                }
            )
        return {
            "key": str(reg["id"]),
            "name": reg["contact_name"] or "—",
            "team": reg["team_name"],
            "sub": reg["component_name"] if sub_is_component else None,
            "email": reg["contact_email"],
            "phone": reg["phone"],
            "date": reg["registered_at"],
            "products": [
                f"{item['quantity']} × {item['product_name'] or '—'}" for item in reg["items"]
            ],
            "badge": badges[payment["state"]] if payment else None,
            "payment": payment,
            "href": page,
            "action": action,
            "menu": menu,
        }

    key = SORT_KEYS[sort.lstrip("-")]
    direction = "desc" if sort.startswith("-") else "asc"
    shown = []
    total = 0
    for index, group in enumerate(groups):
        own = {reg["id"] for reg in group["regs"]}
        regs = [reg for reg in searched if reg["id"] in own]
        if view == "openstaand":
            regs = [reg for reg in regs if payments.get(reg["id"], {}).get("state") == "open"]
        if not regs:
            continue
        regs = sorteer_inschrijvingen(regs, key, direction)[0]
        total += len(regs)
        shown.append(
            {
                "id": f"reg-group-{index}",
                "name": group["name"],
                "count": len(regs),
                "items": group.get("items") or [],
                "link": group.get("link"),
                "rows": [_row(reg) for reg in regs],
            }
        )

    def _sort_link(column: str) -> dict:
        nxt = "-" + column if sort == column else column
        query = urlencode(_state_query(view, q, nxt))
        page = page_url + ("?" + query if query else "")
        fragment = (fragment_url + ("?" + query if query else "")) if fragment_url else page
        return {
            "sort_url": fragment,
            "sort_page_url": page,
            "sorted": ("desc" if sort.startswith("-") else "asc")
            if sort.lstrip("-") == column
            else None,
        }

    columns = [
        {"key": "naam", "label": _("Naam"), "cell": "name", **_sort_link("naam")},
        {"key": "contact", "label": _("Contact"), "cell": "context"},
        {"key": "datum", "label": _("Datum"), "cell": "date", **_sort_link("datum")},
        # #1741: five columns have the width their content needs (568 px
        # together), so in a table of 900–1100 px a name was left with 47–76
        # px and broke inside a word. The two columns a row can miss leave as
        # the table gets narrower — the kit's own priorities, as on
        # Betalingen: Producten first (the registration's page lists them),
        # then Saldo. On a phone the stacked row keeps its products line.
        {"key": "producten", "label": _("Producten"), "cell": "more", "priority": 1},
        {"key": "bedrag", "label": _("Bedrag"), "cell": "amount", "num": True},
        {"key": "saldo", "label": _("Saldo"), "cell": "extra", "num": True, "priority": 2},
        {"key": "status", "label": _("Status"), "cell": "status"},
        {"key": "acties", "label": _("Acties"), "cell": "actions"},
    ]

    if needle:
        empty = _("Geen inschrijvingen gevonden voor “%(q)s”.") % {"q": q}
    elif view == "openstaand":
        empty = _("Geen inschrijvingen met een openstaande betaling.")
    else:
        empty = _("Nog geen inschrijvingen.")

    return {
        "reg_groups": shown,
        "reg_columns": columns,
        "reg_total": total,
        # No paging inside a record: the count reads "1–n van n".
        "reg_per_page": max(total, 1),
        "reg_open_row": open_row if open_row in {str(i) for i in ids} else "",
        "reg_view": view,
        "reg_q": q,
        "reg_sort": sort,
        "reg_segments": [
            {"value": "alle", "label": _("Alle")},
            {"value": "openstaand", "label": _("Openstaand"), "count": open_count},
        ],
        "reg_sort_options": [
            ("datum", _("Oudste eerst")),
            ("-datum", _("Recentste eerst")),
            ("naam", _("Naam A–Z")),
            ("-naam", _("Naam Z–A")),
        ],
        "reg_empty": empty,
    }
