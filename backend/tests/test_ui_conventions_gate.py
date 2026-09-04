"""Lint-gate UI-conventies (#528 as D) — drift kan niet stilletjes terugkomen.

De conformiteitsmatrix (docs/ui-conformiteit.md) legt vast hoe het hoort; deze
test bewaakt dat het zo blijft. Model: test_import_boundaries / test_i18n_gate.

Vier regels, elk met een reden:

1. **Geen `blue-800`/`blue-900`.** Titels stonden in drie kleuren door elkaar.
   Merkblauw is `blue-700`; de donkere tint bestaat alleen als hover-token
   (`brand-ocean-hover`).
2. **Geen rauwe hex in de opmaak.** Kleur komt uit tokens. Een hex mag enkel in
   een `:root{...}`-blok staan — dáár wordt een token gedefinieerd.
3. **Geen `alert()`/`confirm()`.** Bevestiging gaat via `ui.modal()`, feedback via
   `ui.toast()`.
4. **Geen `amber-*`.** Geel is "wachtend"; het amber-palet is vervallen.
5. **Geen `hx-confirm`.** Dat toont het native browser-confirm(); bevestiging gaat
   sinds #595 via de in-app modal (`data-confirm` + `ui.confirm_host()`).
6. **Geen ge-escapete attribuutstrings.** `_()` levert Markup; plak je daar met
   `~` een gewone string aan, dan escapet Jinja de gewone helft en ziet htmx
   `hx-post=&#34;…&#34;` — de knop is inert. Idem voor een `{% set %}` met
   attributen erin, die bij `{{ var }}` alsnog geëscaped wordt. Drie keer
   opgedoken: #514, #613, #616.
7. **Een "Bewerken"-knop die een modus omschakelt, toont beide standen.** Anders
   liegt hij over de toestand (#615). Gebruik `ui.edit_toggle()`.
8. **De primaire actie staat in de paginakop.** Een admin-lijstscherm gebruikt de
   call-vorm van `page_header` (#621) — de knop hoort op de titelregel, niet in een
   losse rij eronder.
9. **Geen merkblauwe kaarttitel.** Merkblauw is voor koppen en chrome (§1.1); een
   lijst van twintig blauwe recordnamen leest als twintig links (#621).
10. **Geen kale `<select>`.** Zonder control-klassen valt hij terug op de
   preflight-hoogte en staat hij ~15px lager dan het zoekveld ernaast; dat gaf
   scheve filterbalken op zeven schermen (#611). Gebruik `ui.select_control()`,
   `ui.grouped_filter()` of `ui.field_select()`.

Uitzonderingen staan expliciet in ALLOWLIST, met reden — zoals de allowlists in
de andere gates: een regel toevoegen mag, maar niet stilzwijgend.
"""

import pytest
pytestmark = pytest.mark.ui_serverrendered
import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

TEMPLATES = sorted(
    list((APP / "ui" / "templates").rglob("*.html"))
    + [p for d in (APP / "domains").glob("*/templates") for p in d.rglob("*.html")]
)

# (bestandsnaam, regel-fragment) → reden. Leeg is het doel.
ALLOWLIST: dict[tuple[str, str], str] = {}

HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
DONKERBLAUW = re.compile(r"\bblue-(800|900)\b")
AMBER = re.compile(r"\bamber-\d")
JS_DIALOOG = re.compile(r"\b(alert|confirm)\s*\(")
HX_CONFIRM = re.compile(r"\bhx-confirm\b")
# Markers die aantonen dat een <select> de kit-stijl draagt.
SELECT_OK = ("_control", "border")
# Een kit-knop met een label dat enkel uit 1–2 symbolen bestaat (×, ⚙, ➤, …).
GLYPH_KNOP = re.compile(r'btn_(?:danger|secondary|primary|outline)\(\s*"([^"\w\s]{1,2})"')


def _overtredingen(patroon: re.Pattern, *, negeer_root: bool = False):
    """Alle regels in alle templates die het patroon raken, minus de allowlist.

    Jinja-commentaar telt niet mee — ook niet over meerdere regels. Zonder die
    uitzondering slaat de gate aan op de conventie die hem beschrijft: het
    commentaar bij ui.toast() zegt letterlijk dat alert() verboden is.
    """
    treffers = []
    for pad in TEMPLATES:
        in_commentaar = False
        for nr, regel in enumerate(pad.read_text().splitlines(), 1):
            was_commentaar = in_commentaar
            if "{#" in regel and "#}" not in regel:
                in_commentaar = True
            elif "#}" in regel:
                in_commentaar = False
                was_commentaar = True
            if was_commentaar or ("{#" in regel and "#}" in regel):
                continue
            if not patroon.search(regel):
                continue
            # Een tokendefinitie (:root{--x:#hex}) is precies waar hex hoort.
            if negeer_root and ":root" in regel:
                continue
            if (pad.name, regel.strip()) in ALLOWLIST:
                continue
            treffers.append(f"{pad.relative_to(APP)}:{nr}: {regel.strip()[:110]}")
    return treffers


def test_geen_donkerblauw_buiten_de_tokens():
    """blue-800/900 met de hand = titelkleur-drift (#486). Merkblauw is blue-700."""
    fouten = _overtredingen(DONKERBLAUW)
    assert not fouten, (
        "Gebruik blue-700 (merkblauw) of het token brand-ocean-hover:\n  "
        + "\n  ".join(fouten)
    )


def test_geen_rauwe_hex_in_de_opmaak():
    """Kleur komt uit tokens; een hex hoort enkel in een :root-tokendefinitie."""
    fouten = _overtredingen(HEX, negeer_root=True)
    assert not fouten, (
        "Gebruik een token (var(--line), text-ink-soft, …) i.p.v. een hex:\n  "
        + "\n  ".join(fouten)
    )


def test_geen_browserdialogen():
    """alert()/confirm() zijn vervangen door ui.toast() en ui.modal() (§2.9)."""
    fouten = _overtredingen(JS_DIALOOG)
    assert not fouten, (
        "Gebruik ui.toast() voor feedback en ui.modal() voor bevestiging:\n  "
        + "\n  ".join(fouten)
    )


def test_amber_is_vervallen():
    """Eén gele schaal: yellow-* is de token, amber bestaat niet meer."""
    fouten = _overtredingen(AMBER)
    assert not fouten, "Gebruik yellow-* (= wachtend):\n  " + "\n  ".join(fouten)


def test_glyph_knoppen_hebben_aria_label():
    """Een knoplabel dat enkel uit een symbool bestaat (×, ⚙, …) heeft een
    aria-label nodig — een screenreader hoort anders enkel het teken (#528-nulmeting)."""
    fouten = []
    for pad in TEMPLATES:
        for nr, regel in enumerate(pad.read_text().splitlines(), 1):
            if "{#" in regel or "#}" in regel:
                continue
            if GLYPH_KNOP.search(regel) and "aria-label" not in regel:
                fouten.append(f"{pad.relative_to(APP)}:{nr}: {regel.strip()[:90]}")
    assert not fouten, (
        "Geef symbool-knoppen een aria-label (attrs='aria-label=\"…\" …'):\n  "
        + "\n  ".join(fouten)
    )


def test_geen_hx_confirm():
    """hx-confirm toont het native browser-confirm(); bevestiging gaat via de
    in-app modal (data-confirm + ui.confirm_host(), #595)."""
    fouten = _overtredingen(HX_CONFIRM)
    assert not fouten, (
        "Gebruik confirm_attrs()/data-confirm i.p.v. hx-confirm:\n  "
        + "\n  ".join(fouten)
    )


def test_de_kit_levert_de_beloofde_macros():
    """ui-conventies.md §5.1 belooft deze macro's; ze moeten echt bestaan.

    Een conventie die naar een niet-bestaande macro verwijst, stuurt de volgende
    schermbouwer terug naar een lokaal patroon — precies de drift die #528 sluit.
    """
    kit = (APP / "ui" / "templates" / "_macros.html").read_text()
    beloofd = [
        "page_header", "section_header", "card", "nested_panel", "tabs",
        "search", "grouped_filter", "pager", "row_actions", "reorder",
        "empty_state", "loading", "badge", "modal",
        "toast", "toast_host", "success_banner", "error_banner",
        "field_input", "field_select", "field_textarea", "person_fields",
        "btn_primary", "btn_secondary", "btn_outline", "btn_danger",
    ]
    ontbreekt = [m for m in beloofd if f"macro {m}(" not in kit]
    assert not ontbreekt, f"Beloofd in ui-conventies.md §5.1 maar niet in de kit: {ontbreekt}"


def test_toasts_hebben_een_landingsplek():
    """ui.toast() stuurt out-of-band naar #toasts; die host hoort in de schil."""
    for schil in ("site_base.html", "admin_base.html"):
        inhoud = (APP / "ui" / "templates" / schil).read_text()
        assert "toast_host()" in inhoud, f"{schil} mist ui.toast_host()"


def test_geen_kale_select():
    """Een <select> zonder control-klassen valt terug op de preflight-hoogte (#611).

    De basisregel uit #482 (`:where(… select …)`) zet wél rand en radius, maar de
    padding wordt overschreven door Tailwinds eigen preflight — `select{padding:0}`
    heeft specificiteit 0,0,1 tegenover 0,0,0 voor `:where()`. Daardoor is zo'n
    select ~15px lager dan het zoekveld ernaast. De kitmacro's zetten de padding
    expliciet; dit is een regel-vormige afwijking, dus ze hoort in de gate.
    """
    fouten = []
    for pad in TEMPLATES:
        tekst = _zonder_commentaar(pad)
        for treffer in re.finditer(r"<select\b", tekst):
            eind = tekst.find(">", treffer.start())
            tag = tekst[treffer.start():eind + 1] if eind != -1 else tekst[treffer.start():]
            if any(m in tag for m in SELECT_OK):
                continue
            regel = tekst[:treffer.start()].count("\n") + 1
            fouten.append(f"{pad.relative_to(APP)}:{regel}: {tag.strip()[:90]}")
    assert not fouten, (
        "Gebruik ui.select_control() / ui.grouped_filter() / ui.field_select():\n  "
        + "\n  ".join(fouten)
    )


# ── Ge-escapete attribuutstrings (#514/#613/#616) ─────────────────────────────
# Twee smaken van dezelfde fout, samen in één regel omdat het één klasse is.
def _zonder_commentaar(pad) -> str:
    """Jinja-commentaar leegmaken met behoud van regelnummers.

    Nodig omdat het commentaar bij een fix juist het FOUTE patroon toont — zowel bij
    select_control() als bij _inschrijving_detail.html, waar staat waarom de
    attributen niet meer in een {% set %} zitten."""
    return re.sub(r"\{#.*?#\}", lambda m: re.sub(r"[^\n]", " ", m.group(0)),
                  pad.read_text(), flags=re.S)


VEILIG_STRING = re.compile(r"_\((?:[^()]|\([^()]*\))*\)\|string")
MARKUP_CONCAT = re.compile(r"~\s*_\(|_\((?:[^()]|\([^()]*\))*\)\s*~")
ATTR_IN_SET = re.compile(r"\{%-?\s*set\s+\w+\s*=\s*['\"]\s*hx-")
# Een modus-knop die maar één stand toont (#615).
HANDMATIGE_TOGGLE = re.compile(r"btn_\w+\(\s*_\(\"Bewerk[^\"]*\"\)[^)]*@click")


def test_geen_geescapete_attribuutstrings():
    """`'…' ~ _(\"…\")` en `{% set x = 'hx-…' %}` maken knoppen stil inert.

    `_()` geeft in een autoescaped template Markup terug. Zodra je daar met `~` een
    gewone string aan plakt, escapet Jinja de gewone helft: htmx krijgt
    `hx-post=&#34;/…&#34;` en doet niets. Een `{% set %}` met attributen erin gaat op
    dezelfde manier stuk bij `{{ var }}`. Fix: `_(\"…\")|string`, of de attributen
    letterlijk op het element / via de `attrs=`-parameter (die doet zelf `|safe`).
    """
    fouten = []
    for pad in TEMPLATES:
        for nr, regel in enumerate(_zonder_commentaar(pad).splitlines(), 1):
            if "attrs=" in regel and MARKUP_CONCAT.search(VEILIG_STRING.sub("", regel)):
                fouten.append(f"{pad.relative_to(APP)}:{nr}: ~ _() in een attrs-string "
                              f"→ gebruik _()|string")
            if ATTR_IN_SET.search(regel):
                fouten.append(f"{pad.relative_to(APP)}:{nr}: attributen in een "
                              f"{{% set %}} → schrijf ze letterlijk of geef ze via attrs=")
    assert not fouten, (
        "Ge-escapete attributen maken de knop inert (#514/#613/#616):\n  "
        + "\n  ".join(fouten)
    )


def test_bewerk_knoppen_tonen_beide_standen():
    """Een knop die "Bewerken" blijft zeggen terwijl je bewerkt, liegt over de
    toestand (#615, ui-conventies §2.8). `ui.edit_toggle()` toont beide standen;
    handmatig mag ook, zolang de knop zelf "Bewerken" én "Annuleren" bevat."""
    fouten = []
    for pad in TEMPLATES:
        for nr, regel in enumerate(_zonder_commentaar(pad).splitlines(), 1):
            if HANDMATIGE_TOGGLE.search(regel):
                fouten.append(f"{pad.relative_to(APP)}:{nr}: {regel.strip()[:80]}")
    assert not fouten, (
        "Gebruik ui.edit_toggle(state) i.p.v. een knop met één stand:\n  "
        + "\n  ".join(fouten)
    )


# ── C1-lijstschermen: actie in de kop, kaarttitel in ink (#621) ──────────────
LIJSTSCHERMEN = ["admin_activiteiten.html", "admin_formulieren.html",
                 "admin_paginas.html", "admin_media.html",
                 "admin_gebruikers.html", "admin_tenants.html", "leden.html"]
KAARTFRAGMENTEN = ("_aa_kaarten.html", "_fb_kaarten.html", "_cp_kaarten.html",
                   "_tn_kaarten.html", "_leden_lijst.html", "_me_lijst.html",
                   "_gu_lijst.html")


def test_lijstschermen_zetten_de_actie_in_de_kop():
    """De "+ Nieuwe …"-knop hoort op de titelregel, zoals C1 en het referentiescherm
    Leden (#611/#621). De call-vorm van page_header is daar het bewijs van: zonder
    caller-blok staat de knop noodzakelijk ergens anders."""
    per_naam = {pad.name: pad for pad in TEMPLATES}
    fouten = []
    for naam in LIJSTSCHERMEN:
        pad = per_naam.get(naam)
        if pad is None:
            continue
        if "{% call ui.page_header" not in _zonder_commentaar(pad):
            fouten.append(f"{pad.relative_to(APP)}: gebruikt ui.page_header() zonder call-blok")
    assert not fouten, (
        "Zet de primaire actie in de kop via {% call ui.page_header(…) %}:\n  "
        + "\n  ".join(fouten)
    )


def test_kaarttitels_staan_niet_in_merkblauw():
    """Merkblauw draagt koppen en chrome (§1.1). Een recordnaam is geen kop; een
    lijst van twintig blauwe regels leest als twintig links (#621)."""
    fouten = []
    for pad in TEMPLATES:
        if not pad.name.endswith(KAARTFRAGMENTEN):
            continue
        for nr, regel in enumerate(_zonder_commentaar(pad).splitlines(), 1):
            if "font-semibold" in regel and "text-blue-700" in regel:
                fouten.append(f"{pad.relative_to(APP)}:{nr}: {regel.strip()[:80]}")
    assert not fouten, (
        "Gebruik text-ink voor de recordnaam, ink-soft voor de metadata:\n  "
        + "\n  ".join(fouten)
    )
