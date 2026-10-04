"""The record head of the kit (CR-11 block 5, #1557): `record_header`,
`reference`, `related_tabs` and the way back (`app.ui.way_back`).

Norm: `docs/design-system-end-state.md` §2.2, §3.9, §3.11, §3.12. The geometry —
the title first on a phone, the frame that does not move between tabs — is
measured in a browser (`tests_e2e/`); here the markup and the placing rules are
pinned.
"""

import re

from app.ui import list_return, record_frame, register_origin, templates, way_back


def _render(body: str, **ctx) -> str:
    return templates.env.from_string("{% import '_macros.html' as ui %}" + body).render(**ctx)


ACTIONS = [
    {"kind": "delete", "label": "Verwijderen", "attrs": 'hx-post="/x/delete"', "confirm": "Zeker?"},
    {"kind": "tool", "label": "Design Studio", "href": "/studio"},
    {
        "kind": "record",
        "verb": "state",
        "label": "Terug naar concept",
        "attrs": 'hx-post="/x/status"',
    },
    {"kind": "tool", "label": "Foto's uploaden", "href": "/fotos"},
    {"kind": "record", "verb": "copy", "label": "Kopiëren", "href": "/x/kopieren"},
]


def _head(**kwargs) -> str:
    return _render(
        "{{ ui.record_header(title, badges=badges, facts=facts, primary=primary, actions=actions,"
        " back=back, editing=editing) }}",
        **{
            "title": "Zomerfeest",
            "badges": [{"label": "Gepubliceerd", "tone": "green"}, {"label": "Iedereen welkom"}],
            "facts": [],
            "primary": {"label": "Bewerken", "href": "/x?bewerken=1"},
            "actions": ACTIONS,
            "back": {"label": "Activiteiten", "href": "/admin/activiteiten"},
            "editing": False,
            **kwargs,
        },
    )


def _menu(html: str) -> str:
    return html[html.index("data-actions-menu") : html.index("</header>")]


# ── The macro places the actions; the screen only says what it has ───────────


def test_the_macro_orders_the_actions_whatever_order_the_screen_hands_them_in():
    """Record actions in the norm's order, tools under a divider (in the order
    the screen hands them: they have no fixed one), delete last after a divider
    — from a list that hands delete first and the record actions reversed."""
    menu = _menu(_head())
    labels = re.findall(r'role="menuitem"[^>]*>([^<]+)<', menu)
    assert labels == [
        "Kopiëren",
        "Terug naar concept",
        "Design Studio",
        "Foto&#39;s uploaden",
        "Verwijderen",
    ]
    assert menu.count("data-menu-divider") == 2
    first, second = (m.start() for m in re.finditer("data-menu-divider", menu))
    assert (
        menu.index("Terug naar concept")
        < first
        < menu.index("Design Studio")
        < second
        < menu.index("Verwijderen")
    )


def test_delete_is_red_and_asks_first():
    menu = _menu(_head())
    item = menu[menu.rindex("<button", 0, menu.index("Verwijderen")) : menu.index("Verwijderen")]
    assert "text-red-700" in item and 'data-confirm="Zeker?"' in item
    assert menu.count("text-red-700") == 1, "only delete is red"


def test_a_group_that_is_empty_draws_no_divider():
    only_tools = _menu(_head(actions=[a for a in ACTIONS if a["kind"] == "tool"]))
    assert "data-menu-divider" not in only_tools
    two_groups = _menu(_head(actions=[a for a in ACTIONS if a["kind"] != "delete"]))
    assert two_groups.count("data-menu-divider") == 1


def test_one_primary_and_one_actions_trigger():
    html = _head()
    controls = html[html.index("data-head-controls") : html.index("data-actions-menu")]
    assert controls.count(">Bewerken<") == 1
    assert controls.count("data-actions-trigger") == 1
    assert 'aria-haspopup="menu"' in controls


def test_a_head_without_actions_has_no_menu():
    html = _head(actions=[])
    assert "data-actions-trigger" not in html and ">Bewerken<" in html
    assert "data-head-controls" not in _head(actions=[], primary=None)


# ── Badges: the status first; the edit state after it ────────────────────────


def test_the_status_comes_first_and_the_others_are_grey():
    html = _head()
    badges = html[html.index("data-badges") : html.index("data-head-controls")]
    assert badges.index("Gepubliceerd") < badges.index("Iedereen welkom")
    grey = _render("{{ ui.badge('Iedereen welkom', 'gray') }}")
    assert grey in badges, "a badge without a tone is the grey one"


def test_editing_adds_the_badge_after_the_status_and_takes_the_primary_away():
    html = _head(editing=True)
    badges = html[html.index("data-badges") : html.index("data-head-controls")]
    assert (
        badges.index("Gepubliceerd") < badges.index(">Bewerken<") < badges.index("Iedereen welkom")
    )
    controls = html[html.index("data-head-controls") :]
    assert "?bewerken=1" not in controls, "no primary while editing"
    assert "data-actions-trigger" in controls, "Acties stays"


# ── Facts and the reference ──────────────────────────────────────────────────


def test_the_facts_line_keeps_plain_text_a_reference_and_a_mail_address_apart():
    html = _head(
        facts=[
            {"text": "zaterdag 14 juni 2031"},
            {"text": "Publieke pagina", "kind": "reference", "href": "/activiteiten/zomerfeest"},
            {"text": "info@example.test", "kind": "mail"},
        ]
    )
    facts = html[html.index("data-facts") : html.index("</header>")]
    assert "<span>zaterdag 14 juni 2031</span>" in facts
    assert 'href="/activiteiten/zomerfeest" data-reference' in facts
    assert 'href="mailto:info@example.test"' in facts
    assert facts.count('aria-hidden="true">·<') == 2, (
        "a separator between facts, none before the first"
    )


def test_a_head_without_facts_has_no_facts_line():
    assert "data-facts" not in _head(facts=[])


def test_a_reference_carries_the_arrow():
    html = _render("{{ ui.reference('Gezin Peeters', '/admin/leden/gezin/7') }}")
    arrow = _render("{{ ui.icon('arrow-up-right', 14) }}")
    assert 'href="/admin/leden/gezin/7" data-reference' in html and arrow in html


# ── Related tabs ─────────────────────────────────────────────────────────────

TABS = [
    {"label": "Gegevens", "href": "/x", "active": True},
    {"label": "Inschrijvingen", "count": 23, "href": "/x/inschrijvingen", "active": False},
    {"label": "Betalingen", "count": 0, "href": "/x/betalingen", "active": False},
]


def test_tabs_show_their_count_in_brackets_and_mark_the_active_one():
    html = _render("{{ ui.related_tabs(tabs) }}", tabs=TABS)
    assert re.search(r"Inschrijvingen<span[^>]*>\(23\)</span>", html)
    assert re.search(r"Betalingen<span[^>]*>\(0\)</span>", html), "zero is a count too"
    assert ">Gegevens</a>" in html, "a tab without a count shows no brackets"
    assert html.count('aria-current="page"') == 1
    active = html[html.index('href="/x"') : html.index(">Gegevens")]
    assert 'aria-current="page"' in active and "border-b-2" in active
    assert "rounded" not in html and "bg-" not in html, "an underline, no filled or bordered tab"


def test_tabs_carry_the_way_back_along():
    html = _render(
        "{{ ui.related_tabs(tabs, keep='terug=%2Fadmin%2Factiviteiten%3Fq%3Dzomer') }}", tabs=TABS
    )
    assert 'href="/x/inschrijvingen?terug=%2Fadmin%2Factiviteiten%3Fq%3Dzomer"' in html


def test_a_record_without_tabs_has_no_tab_line():
    assert _render("{{ ui.related_tabs([]) }}").strip() == ""


# ── The way back names its origin ────────────────────────────────────────────

LIST = "/admin/activiteiten"


def test_without_an_origin_the_way_back_is_the_list_by_its_menu_name(db_session):
    assert way_back(db_session, None, LIST) == {"label": "Activiteiten", "href": LIST, "keep": ""}


def test_the_list_as_it_was_left_comes_back_with_its_state(db_session):
    origin = list_return(LIST, scope="all", q="zomer")
    assert origin == "/admin/activiteiten?scope=all&q=zomer"
    back = way_back(db_session, origin, LIST)
    assert back["label"] == "Activiteiten" and back["href"] == origin
    assert back["keep"] == "terug=%2Fadmin%2Factiviteiten%3Fscope%3Dall%26q%3Dzomer"


def test_a_plain_list_hands_a_plain_path():
    assert list_return(LIST, scope="", q="") == LIST


def test_an_origin_outside_the_site_is_dropped(db_session):
    """`veilige_terug`: only a local path. The label would otherwise name a
    list while the link leaves the site."""
    for hostile in ("https://evil.example/x", "//evil.example/x", "javascript:alert(1)", "/\\evil"):
        assert way_back(db_session, hostile, LIST) == {
            "label": "Activiteiten",
            "href": LIST,
            "keep": "",
        }


def test_a_registered_origin_names_itself_and_falls_back_to_the_menu(db_session):
    def labeler(db, url):
        return "Dossier van An" if "dossier=7" in url else None

    register_origin("/admin/werkbank", labeler)
    named = way_back(db_session, "/admin/werkbank?dossier=7", LIST)
    assert named["label"] == "Dossier van An" and named["href"] == "/admin/werkbank?dossier=7"
    plain = way_back(db_session, "/admin/werkbank", LIST)
    assert plain["label"] == "Werkbank" and plain["href"] == "/admin/werkbank"


def test_the_frame_reads_the_page_address_of_a_fragment_request(db_session):
    """A save inside the record answers on its own URL; htmx sends the page's as
    `HX-Current-URL`, and the head it carries along must still know its way back
    and its edit state."""
    from starlette.requests import Request

    def request(query: str, current: str | None = None) -> Request:
        headers = [(b"hx-current-url", current.encode())] if current else []
        return Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/x",
                "query_string": query.encode(),
                "headers": headers,
            }
        )

    frame = record_frame(
        request("bewerken=1&terug=%2Fadmin%2Factiviteiten%3Fq%3Dzomer"), db_session, LIST
    )
    assert frame["head_editing"] is True
    assert frame["way_back"]["href"] == "/admin/activiteiten?q=zomer"

    via_htmx = record_frame(
        request(
            "",
            "http://testserver/admin/activiteiten/3?bewerken=1&terug=%2Fadmin%2Factiviteiten%3Fq%3Dzomer",
        ),
        db_session,
        LIST,
    )
    assert via_htmx == frame

    assert record_frame(request(""), db_session, LIST)["head_editing"] is False
