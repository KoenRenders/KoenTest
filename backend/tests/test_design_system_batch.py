"""Design-system batch #593–#598 — macro- en conventie-invarianten.

Snelle, DB-loze tests op de kit-macro's + shells. De bredere rendering-integriteit
is al gedekt door de scherm-tests (test_betalingen_ui, test_workflow_component, …);
hier nagelen we de nieuwe conventies vast zodat ze niet terugdriften.
"""
from pathlib import Path

from app.ui import templates

APP = Path(__file__).resolve().parents[1] / "app"


def _render(body: str) -> str:
    return templates.env.from_string("{% import '_macros.html' as ui %}" + body).render()


# ── #593 iconen ───────────────────────────────────────────────────────────────

def test_icon_macro_rendert_svg():
    for naam in ("download", "upload", "file-text", "search", "chevron-up",
                 "chevron-down", "arrow-up", "arrow-down"):
        out = _render("{{ ui.icon('%s') }}" % naam)
        assert "<svg" in out and "<path" in out or "<circle" in out, naam


def test_icon_onbekend_faalt_stil():
    out = _render("{{ ui.icon('bestaat-niet') }}")
    assert "<svg" in out  # lege maar geldige svg, breekt de layout niet


def test_knop_met_lead_icon_bevat_svg_en_label():
    out = _render("{{ ui.btn_secondary('Export', lead_icon='download') }}")
    assert "<svg" in out and "Export" in out


def test_geen_glyph_iconen_meer_in_templates():
    """De hand-geplaatste glyphs zijn vervangen door ui.icon() (#593/#594)."""
    glyphs = ["⬇", "⬆", "\U0001f4c4", "▲", "▼"]  # ⬇ ⬆ 📄 ▲ ▼
    fouten = []
    # De kit (_macros.html) mag de glyphs in zijn doc-comments noemen; enkel de
    # scherm-templates worden op resterend glyph-gebruik gecontroleerd.
    for pad in ([p for p in (APP / "ui" / "templates").rglob("*.html") if p.name != "_macros.html"]
                + [p for d in (APP / "domains").glob("*/templates") for p in d.rglob("*.html")]):
        for nr, regel in enumerate(pad.read_text().splitlines(), 1):
            if "{#" in regel or "#}" in regel:
                continue  # documentatie-comments mogen de glyph noemen
            if any(g in regel for g in glyphs):
                fouten.append(f"{pad.name}:{nr}")
    assert not fouten, f"Gebruik ui.icon() i.p.v. glyphs: {fouten}"


# ── #594 reorder ──────────────────────────────────────────────────────────────

def test_reorder_gebruikt_icon_svg():
    out = _render("{{ ui.reorder(up_attrs='hx-post=\"/x\"', down_attrs='hx-post=\"/y\"') }}")
    assert out.count("<svg") == 2 and "▲" not in out and "▼" not in out


# ── #595 bevestig-modal ───────────────────────────────────────────────────────

def test_confirm_attrs_levert_data_confirm():
    fn = templates.env.globals["confirm_attrs"]
    out = fn("Persoon", "Jan")
    assert out.startswith("data-confirm=") and "hx-confirm" not in out


def test_confirm_host_hangt_aan_htmx_confirm():
    out = _render("{{ ui.confirm_host() }}")
    # Alpine-store-idioom + de onvermijdelijke htmx-lifecycle-brug.
    assert "htmx:confirm" in out and "issueRequest" in out
    assert "Alpine.store('confirm'" in out and "$store.confirm.open" in out


def test_beide_shells_hebben_de_confirm_host():
    for schil in ("site_base.html", "admin_base.html"):
        inhoud = (APP / "ui" / "templates" / schil).read_text()
        assert "confirm_host()" in inhoud, f"{schil} mist ui.confirm_host()"


# ── #596 rij-acties + geen statusstreep ───────────────────────────────────────

def test_row_actions_verbergt_extra_achter_menu():
    acts = "['<button>A</button>', '<button>B</button>', '<button>C</button>']"
    out = _render("{{ ui.row_actions(actions=%s, delete_attrs='hx-post=\"/d\"') }}" % acts)
    assert "A" in out and "B" in out and "C" in out
    assert "⋯" in out                    # ⋯-menu aanwezig want >2 acties
    assert "Verwijderen" in out               # delete altijd, en laatst


def test_betalingen_lijst_heeft_geen_statusstreep():
    inhoud = (APP / "domains" / "payment" / "templates" / "_betalingen_lijst.html").read_text()
    assert "border-l-4" not in inhoud and "_stripe" not in inhoud
    # Sinds golf 10 (#913) geen ui.row_actions meer: de rij draagt de opener
    # (edit_toggle) plus één snelactie, en verwijderen woont in de
    # bewerk-uitklaprij (A2) — een ⋯-menu zou in de overflow-container clippen.
    assert "ui.edit_toggle" in inhoud
    assert 'ui.btn_danger(_("Verwijderen")' in inhoud


# ── #597 werkbank full-page ───────────────────────────────────────────────────

def test_werkbank_lijst_klikt_door_naar_full_page():
    inhoud = (APP / "domains" / "workflow" / "templates" / "_werkbank_lijst.html").read_text()
    assert 'href="/admin/werkbank/taken/' in inhoud       # doorklik-link
    assert 'hx-target="#taak-' not in inhoud              # geen inline uitklap meer


# ── #598 microcopy ────────────────────────────────────────────────────────────

def test_header_woordmerk_is_raak():
    """Header-woordmerk = 'RaaK' (kapitale R/K, aa vergroot), niet 'RAAK' via uppercase (#605).

    De schaalfactor is 1.3em sinds #625: capHeight 690 / xHeight 530 van Radio Canada
    Big zet de "aa" exact op kapitaalhoogte. Met de vorige 1.4 stond ze 7,5 % te hoog.
    """
    site = (APP / "ui" / "templates" / "site_base.html").read_text()
    assert 'R<span class="text-[1.3em]">aa</span>K' in site
    for regel in site.splitlines():
        if '>aa</span>K' in regel:
            assert "uppercase" not in regel   # geen all-caps meer op het woordmerk


def test_link_tint_token_en_cms_link():
    """Links dragen de fellere merk-tint #2367bd via de --link/text-link-token (#603).

    Sinds golf 0 van het Ontwerpspoor (#913) staat de waarde als RGB-triplet in
    `--c-link` (35 103 189 = #2367bd) en verwijzen de utility en de leesbare
    alias ernaar — de bedoeling van #603 blijft: één linktoken, en de CMS-inhoud
    gebruikt hem.
    """
    build = (Path(__file__).resolve().parents[2] / "scripts" / "build-css.sh").read_text()
    assert "--c-link:35 103 189" in build                       # de ene bron (= #2367bd)
    assert "--link:rgb(var(--c-link))" in build                 # leesbare alias
    assert "link: 'rgb(var(--c-link) / <alpha-value>)'" in build  # Tailwind text-link-utility
    site = (APP / "ui" / "templates" / "site_base.html").read_text()
    assert ".cms-content a{color:var(--link)" in site and "underline" in site


def test_create_schermen_gebruiken_opslaan():
    for pad in [
        ("activities", "admin_activiteiten.html"),
        ("auth", "admin_gebruikers.html"),
        ("cms", "admin_paginas.html"),
        ("forms", "admin_formulieren.html"),
        ("mdm", "leden.html"),
    ]:
        inhoud = (APP / "domains" / pad[0] / "templates" / pad[1]).read_text()
        assert 'btn_primary(_("Aanmaken"))' not in inhoud, pad[1]
    tenants = (APP / "ui" / "templates" / "admin_tenants.html").read_text()
    assert "Tenant aanmaken" not in tenants


# ── golf 4 (#913): tabs op het dict-contract ─────────────────────────────────

def test_tabs_rendert_labels_hrefs_en_een_actieve():
    """De macro pakte tuples uit terwijl de enige aanroeper dicts gaf: Jinja
    itereerde dan over de sléutels, dus elke tab heette "href", linkte naar
    "label" en was actief. Dit pint het dict-contract vast: was de bug er nog,
    dan stond "Gegevens" nergens en "href" wél als tekst."""
    html = _render(
        '{{ ui.tabs([{"label": "Gegevens", "href": "/a", "active": True},'
        '            {"label": "Historiek", "href": "/b", "active": False}]) }}')
    assert '>Gegevens</a>' in html and '>Historiek</a>' in html
    assert 'href="/a"' in html and 'href="/b"' in html
    assert '>href</a>' not in html
    assert html.count("border-blue-700") == 1, "precies één tab is actief"


def test_modal_draagt_dialoogsemantiek_en_focusherstel():
    """A6 (golf 4, #913): het modal is een echt dialog (role + aria-modal) en
    sluiten geeft de focus terug aan de trigger. De focus-heen-en-terug zelf is
    browsergedrag; hier pinnen we vast dat de bedrading er staat — valt het
    x-effect weg, dan kleurt dit rood."""
    html = _render('{% call ui.modal("open", "Proef") %}inhoud{% endcall %}')
    assert 'role="dialog"' in html and 'aria-modal="true"' in html
    assert "x-effect=" in html
    assert "_vorige" in html and ".focus()" in html
