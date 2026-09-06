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
10. **Het woordmerk schaalt op 1.3em** — de fontmetriek van Radio Canada Big
    (capHeight 690 / xHeight 530), niet een schatting (#625).
11. **De sociale footer-iconen zijn 32px** — ze waren stil 25 % gekrompen (#626).
12. **Het woord "reglement" komt niet meer voor** — het heet overal "info" (#623).
    Eén woord voor één ding (§2.12).
13. **Geen aanmaak-modal** — aanmaken opent een volledige-pagina-editor (#627,
    §2.8). Modals blijven voor read-only detail en bevestigingen; de publieke
    activiteitinschrijving is de beredeneerde uitzondering (#601).
14. **Terminologie is infinitief** — "Verwijderen"/"Annuleren", niet "Verwijder"/
    "Annuleer" (§2.12, #630). Het stond exact fifty-fifty.
15. **Geen leveranciersnaam in een knoplabel** (§2.12 sinds `edc7241`): een knop
    beschrijft de handeling, niet wie ze uitvoert.
16. **Geen rauwe DB-waarde in een badge** — `ui.badge(x.status|kind|method, …)` toont
    een interne code op het scherm (#630). Map ze eerst naar een label.
17. **Elke symboolknop heeft een aria-label** — ook publiek, niet enkel in de admin
    (#631). De Raakje-verstuurknop heette voor een schermlezer "➤".
18. **Geen getinte KPI-kaart** — de mock kent witte kaarten met een rand; een
    `bg-blue-50`-uitzondering liep twee keer uiteen tussen zusterschermen (#636).
19. **Beide gebooste schillen dragen `hx-boost`** (#634) en hebben een `#main` om
    in te swappen. Navigatie zonder volledige herlaad is een eigenschap van de
    schil; valt het attribuut weg, dan is de polish stil verdwenen zonder dat iets
    faalt. `hx-target`/`hx-select`/`hx-swap` horen er juist NIET bij: die erven in
    htmx naar élke actie in de pagina (closest-lookup) en zouden elke
    fragment-swap breken — de swap-instructie komt uit de responsheaders
    (`_boosted_swap_headers` in main.py).
20. **Downloads en /afmelden staan buiten de boost** (#634). Een gebooste klik op
    een `.ods`-export of op uitloggen levert geen HTML om te swappen — de knop
    doet dan zichtbaar niets. Elke href naar een export-/download-route of naar
    /afmelden draagt `hx-boost="false"`.
21. **Geen `<script src=` buiten een schil** (#634). htmx voert `<script>`-tags in
    ingeswapte inhoud uit; een bibliotheek die `customElements.define` doet (Trix)
    faalt bij de tweede uitvoering. Bibliotheken horen in de `<head>` van de schil.
22. **Geen metadata-emoji.** ✉ 📱 ☎ 📍 🗓 buiten `_macros.html`: dezelfde reden
    als de ⬇⬆📄-regel — emoji renderen per OS en per font anders, met een eigen
    regelhoogte, waardoor de regel verspringt (#638). De kit heeft `mail`,
    `phone`, `mobile`, `map-pin` en `calendar`.
23. **Geen handgeschreven lege toestand.** Een schuine "Geen …"/"Nog geen …"-regel
    is een ad-hoc `Empty` — §2.11 legt één component vast en verbiedt italic. De
    twee publieke fotoschermen deden het zo en importeerden `_macros.html` zelfs
    niet (#637).
24. **Submit heet "Opslaan", niet "<Woord> opslaan"** (§2.12, #641). De
    form-builder had er drie eigen varianten in één scherm. Een
    sub-item-toevoegformulier mag wel "Toevoegen" heten — de regel gaat specifiek
    over de opslaan-variant.
25. **Geen kale `<select>`.** Zonder control-klassen valt hij terug op de
   preflight-hoogte en staat hij ~15px lager dan het zoekveld ernaast; dat gaf
   scheve filterbalken op zeven schermen (#611). Gebruik `ui.select_control()`,
   `ui.grouped_filter()` of `ui.field_select()`.
26. **Het verplicht-sterretje komt uit `label(required=…)`**, niet uit de labeltekst
    (#646). In de tekst erft het `text-gray-700` en staat er grijs naast een rood
    sterretje van een veld dat de parameter wél gebruikt.
32. **Een volledige-pagina-editor heeft [Annuleren] naast [Opslaan]** (§2.8, #664).
    Zonder is de enige terugweg de link bovenaan, die bij een lang formulier buiten
    beeld ligt — precies de motivering die de conventie zelf geeft.
31. **Geen teal badge** (#660). §2.10 kent zes tonen; teal sloop er in #617 bij om
    twee oranje badges naast elkaar te vermijden. #660 lost dat op aan de juiste
    kant — "Terug te betalen" wordt geel, gelijk aan "Openstaand" — zodat de
    ongedocumenteerde zevende toon niet meer nodig is.
30. **Formuliervelden komen uit de kit** (#659). Een `border-gray-300` op een
    input/select/textarea buiten `_macros.html` is een handgeschreven control. Die
    mist `text-sm` (dus hoger dan zijn buren) en heeft een eigen padding — op het
    activiteitdetail stonden er drie verschillende in omloop. Het restant staat als
    telling in `CONTROL_ALLOWLIST`; sinds #663 is die leeg en de regel blokkerend.
29. **Geen hint-alinea in een kolom van een `items-end`-vorm** (#656). Zo'n vorm
    lijnt haar kolommen op de ONDERKANT uit, dus een extra regel onder een
    invoerveld duwt dat veld omhoog. Op de betalingen stond het bedrag daardoor
    scheef — en alleen bij een terugbetaling, want de hint staat achter een
    `{% if %}`. Zet de hint als eigen regel in de vorm (`w-full order-last`).
28. **Een leeslink naar de bijlage staat enkel in leesmodus** (#653, §2.12). Een
    `<a href="…_asset_url">` buiten het uploadblok hoort achter `x-show="!edit"`;
    anders staat "Huidige affiche bekijken" in bewerkmodus twee keer op het scherm.
    Deze regel dekt bewust alleen de bijlage — zie de docstring voor waarom de
    bredere structuurregel uit #653 geen betrouwbare gate oplevert.
27. **Een KPI-cijfer draagt `font-brand` en geen eigen kleurklasse** (#647). Twee
    van de zes stonden in `text-blue-700` en één miste het merkfont; op één scherm
    stond een blauw cijfer naast een zwart. Het design-systeem legt voor KPI's
    alleen het gewicht vast en laat blauw enkel toe als tegelACHTERGROND — een
    kleur op het cijfer zelf staat nergens. De kleur van een dashboardtegel zit op
    de tegel, niet op het cijfer, en blijft dus toegestaan.

Uitzonderingen staan expliciet in ALLOWLIST, met reden — zoals de allowlists in
de andere gates: een regel toevoegen mag, maar niet stilzwijgend.
"""

import pytest
pytestmark = pytest.mark.ui_serverrendered
import re
from pathlib import Path

from tests._bestanden import bestanden

APP = Path(__file__).resolve().parents[1] / "app"

# Via de gedeelde helper (#678): een gate die nergens kijkt, staat groen zonder
# iets te bewaken. Het plafond ligt bewust hoog genoeg om ook een glob te vangen
# die nog wél iets vindt maar de helft mist.
TEMPLATES = bestanden(
    (APP / "ui" / "templates").rglob("*.html"),
    (p for d in (APP / "domains").glob("*/templates") for p in d.rglob("*.html")),
    wat="alle Jinja-templates van de kit en de domeinen", minstens=50,
)

# (bestandsnaam, regel-fragment) → reden. Leeg is het doel.
ALLOWLIST: dict[tuple[str, str], str] = {}

HEX = re.compile(r"#[0-9a-fA-F]{6}\b")
DONKERBLAUW = re.compile(r"\bblue-(800|900)\b")
AMBER = re.compile(r"\bamber-\d")
JS_DIALOOG = re.compile(r"\b(alert|confirm)\s*\(")
HX_CONFIRM = re.compile(r"\bhx-confirm\b")
# Markers die aantonen dat een <select> de kit-stijl draagt.
# `_basis(cls)` levert sinds #663 de control-klassen; `_control_base` blijft
# staan voor de macro's die hem rechtstreeks gebruiken.
SELECT_OK = ("_control", "_basis", "border")
# Een kit-knop met een label dat enkel uit 1–2 symbolen bestaat (×, ⚙, ➤, …).
GLYPH_KNOP = re.compile(r'btn_(?:danger|secondary|primary|outline)\(\s*"([^"\w\s]{1,2})"')
# Metadata-emoji (#638). Zelfde klasse als de ⬇⬆📄-glyphs uit #593: ze horen als
# ui.icon() in de kit, niet als tekstteken in een template.
METADATA_GLYPH = re.compile("[\u2709\u260e\U0001f4f1\U0001f4cd\U0001f5d3]")
# Verplicht-sterretje in de labeltekst i.p.v. via label(required=…) — #646.
# `[^)]*` zou hier NIET werken: `label(_("E-mail") ~ …)` bevat zelf al een
# sluithaakje van `_()`, dus de zoektocht stopt vóór het sterretje.
STERRETJE_IN_LABEL_CALL = re.compile(r'\blabel\([^\n]*["\']\s*\*')
# Een leeslink naar de huidige bijlage: <a href="{{ …_asset_url }}"> buiten het
# uploadblok. Die hoort achter x-show="!<vlag>" (§2.12, #653).
BIJLAGE_LINK = re.compile(r'<[^>]*href="\{\{\s*[a-z_.]*_asset_url[^"]*"[^>]*>')
# Een scherm mét bewerkmodus: een <form> dat aan een Alpine-vlag hangt.
BEWERKVORM = re.compile(r'<form[^>]*x-show="[a-z_]')
# Een hint-alinea (§2.4: text-xs + een gedempte tint) binnen een kolom van een
# flexvorm die op de onderkant uitlijnt — #656.
HINT_ALINEA = re.compile(r'<p[^>]*class="[^"]*\btext-xs\b[^"]*\btext-(?:gray|ink)-(?:400|500|soft)\b')
ITEMS_END = re.compile(r'\bitems-end\b')
FLEX_OPEN = re.compile(r'<(div|form)\b')
# Een handgeschreven formulier-control: de kit zet zijn rand via `_control_base`,
# dus een losse `border-gray-300` op een input/select/textarea betekent dat het
# scherm de kit omzeilt (#659).
HANDGESCHREVEN_CONTROL = re.compile(r"<(?:input|select|textarea)\b[^>]*>")
# Teal is geen semantische toon: de macro kent hem, §2.10 niet (#660).
TEAL_BADGE = re.compile(r'badge\([^)]*"teal"')

# #663 heeft de sweep afgemaakt: er staat er geen enkele meer buiten de kit, dus
# de regel is blokkerend en de allowlist leeg. Blijft ze leeg, dan hoort dat zo.
CONTROL_ALLOWLIST: dict[str, int] = {}

RODE_SPAN = re.compile(r'<span class="text-red-600">.*?</span>')
# Een KPI-cijfer herken je aan font-extrabold: §Weight reserveert dat gewicht voor
# de paginatitel, de KPI-cijfers en het woordmerk, en die eerste twee dragen
# font-bold. In deze codebase is font-extrabold dus exact de KPI-cijfers (#647).
KPI_CIJFER = re.compile(r"\bfont-extrabold\b")
KLEURKLASSE = re.compile(r"\btext-(?:[a-z]+-\d{2,3}|white|black)\b")


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
            # `aria_label=` is sinds #622 de voorkeursvorm: als macro-parameter
            # schrijft Jinja het attribuut zelf, i.p.v. het in een attrs-string te
            # concateneren waar `_()` de escaping sloopt.
            if GLYPH_KNOP.search(regel) and not (
                    "aria-label" in regel or "aria_label" in regel):
                fouten.append(f"{pad.relative_to(APP)}:{nr}: {regel.strip()[:90]}")
    assert not fouten, (
        "Geef symbool-knoppen een aria_label=_(\"…\") op de knopmacro:\n  "
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


MARKUP_CONCAT = re.compile(r"~\s*_\(|_\((?:[^()]|\([^()]*\))*\)\s*~")
ATTR_IN_SET = re.compile(r"\{%-?\s*set\s+\w+\s*=\s*['\"]\s*hx-")
# Een modus-knop die maar één stand toont (#615).
# De regex eiste dat het label met "Bewerk" BEGON, waardoor `_("Adres bewerken")`
# erdoor glipte — de echte bevinding van #639. Nu: het woord mag overal staan.
#
# Bewust NIET de strengere variant uit #642-1 ("een @click=\"x = true\" zonder
# tegenhanger op hetzelfde element"): elke modal-opener is zo'n knop — de
# inschrijfpopup en de e-mailpreview zetten hun state aan, en de modal zelf zet
# hem uit. Die regel zou dus vooral correcte popups afkeuren. Wat #639 écht
# fout deed, is de knop binnen het `x-show="!edit"`-blok zetten waardoor hij
# verdwijnt; dat vraagt structurele parsing van de template, geen regex.
HANDMATIGE_TOGGLE = re.compile(r'btn_\w+\(\s*_\("[^"]*[Bb]ewerk[^"]*"\)[^)]*@click')


def test_geen_geescapete_attribuutstrings():
    """`'…' ~ _(\"…\")` en `{% set x = 'hx-…' %}` maken knoppen stil inert.

    `_()` geeft in een autoescaped template Markup terug. Zodra je daar met `~` een
    gewone string aan plakt, escapet Jinja de gewone helft: htmx krijgt
    `hx-post=&#34;/…&#34;` en doet niets. Een `{% set %}` met attributen erin gaat op
    dezelfde manier stuk bij `{{ var }}`.

    **`|string` lost dit NIET op** — dat was de eerste poging in #616 en ze werkte
    niet: Markup is een str-subklasse, dus `soft_str` geeft ze ongewijzigd terug en de
    escaping blijft. De render-gate (#622) ving dat. Fix: vertaalde tekst hoort niet in
    een geconcateneerde attribuutstring maar als macro-parameter (`confirm=`,
    `aria_label=`), of de attributen letterlijk op het element.
    """
    fouten = []
    for pad in TEMPLATES:
        for nr, regel in enumerate(_zonder_commentaar(pad).splitlines(), 1):
            if "attrs=" in regel and MARKUP_CONCAT.search(regel):
                fouten.append(f"{pad.relative_to(APP)}:{nr}: ~ _() in een attrs-string "
                              f"→ gebruik confirm=/aria_label= op de knopmacro")
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


# ── Huisstijldetails die al eens stil verdwenen (#625/#626) ──────────────────
SITE_BASE = APP / "ui" / "templates" / "site_base.html"
# De publieke formulierkant valt buiten de admin-microcopyregel (§2.12 Deel A).
PUBLIEKE_FORMULIEREN = ("formulier.html",)


def test_woordmerk_schaalt_op_de_fontmetriek():
    """De "aa" hoort exact op kapitaalhoogte te staan.

    Radio Canada Big: capHeight 690, xHeight 530 op 1000 units per em → 690/530 = 1.30.
    Met 1.4 stond de "aa" 7,5 % te hoog (#625). Deze regel legt de waarde vast; wijzigt
    het display-font, dan herbereken je de factor en pas je deze test mee aan — dat is
    het moment waarop je erover hoort na te denken.
    """
    inhoud = SITE_BASE.read_text()
    assert "text-[1.3em]" in inhoud, "de aa-schaal hoort 1.3em te zijn (capHeight/xHeight)"
    assert "text-[1.4em]" not in inhoud


def test_sociale_footer_iconen_zijn_32px():
    """v1.14 had w-8; in v2.0 stonden ze op w-6 en werd Instagram onleesbaar — dat
    glyph heeft de meeste interne detaillering en loopt op 24px dicht (#626)."""
    inhoud = _zonder_commentaar(SITE_BASE)
    sociale = [regel for regel in inhoud.splitlines()
               if "<svg" in regel and "currentColor" in regel and "viewBox=\"0 0 24 24\"" in regel]
    assert len(sociale) >= 3, "de drie sociale iconen zijn niet gevonden"
    fouten = [r.strip()[:70] for r in sociale if "w-8 h-8" not in r]
    assert not fouten, "footer-iconen horen w-8 h-8 te zijn:\n  " + "\n  ".join(fouten)


def test_de_term_reglement_is_vervallen():
    """Eén woord voor één ding (§2.12): de info-bijlage heette op sommige schermen
    "reglement" en elders "info" (#623). Jinja-commentaar telt niet mee — daar mag
    de hernoeming uitgelegd worden."""
    fouten = []
    for pad in TEMPLATES:
        for nr, regel in enumerate(_zonder_commentaar(pad).splitlines(), 1):
            if "reglement" in regel.lower():
                fouten.append(f"{pad.relative_to(APP)}:{nr}: {regel.strip()[:80]}")
    assert not fouten, "Gebruik \"info\" i.p.v. \"reglement\":\n  " + "\n  ".join(fouten)


def test_geen_aanmaak_modal_in_de_admin():
    """Aanmaken opent een volledige-pagina-editor, geen modal (#627, §2.8).

    Je werkt na het aanmaken toch verder in de editor, en de velden uit een dialoogje
    maken het object zelden compleet. v1.14 had trouwens geen enkele modal in de
    admin. De regel eronder: één korte, afgeronde handeling in de context van een
    lijst → modal; een vorm die je moet overzien of een object waar je in verderwerkt
    → volledig scherm.

    Mikt op ADMIN-templates: de publieke activiteitinschrijving blijft bewust een
    modal (#601) en valt dus buiten deze regel.
    """
    fouten = []
    for pad in TEMPLATES:
        naam = pad.name
        if not (naam.startswith("admin_") or naam in ("leden.html", "betalingen.html",
                                                      "werkbank.html")):
            continue
        tekst = _zonder_commentaar(pad)
        if "{% call ui.modal(" not in tekst:
            continue
        # Een modal is enkel fout als er ook een aanmaak-hx-post in dezelfde template staat.
        if re.search(r'hx-post="/admin/[a-z-]+"', tekst):
            fouten.append(f"{pad.relative_to(APP)}: aanmaakformulier in een modal")
    assert not fouten, (
        "Aanmaken opent een volledige-pagina-editor (#627):\n  " + "\n  ".join(fouten)
    )


# ── Rauwe codes en terminologie (#630) ───────────────────────────────────────
INFINITIEF = re.compile(r'_\("(Verwijder|Annuleer)"\)')
# Een badge die rechtstreeks een DB-veld toont i.p.v. een gemapt label.
RAUWE_BADGE = re.compile(r'badge\(\s*[a-z_]+\.(status|kind|method)\b')
# Leveranciersnamen die in een knoplabel niets te zoeken hebben.
LEVERANCIERS = ("Mollie", "Stripe", "Umami", "Mistral", "Voxtral", "Gmail")
KNOPLABEL = re.compile(r'btn_\w+\(\s*_\("([^"]+)"\)')


def test_terminologie_is_infinitief():
    """§2.12 legt de infinitief vast; het stond exact fifty-fifty (#630)."""
    fouten = []
    for pad in TEMPLATES:
        for nr, regel in enumerate(_zonder_commentaar(pad).splitlines(), 1):
            m = INFINITIEF.search(regel)
            if m:
                fouten.append(f"{pad.relative_to(APP)}:{nr}: _(\"{m.group(1)}\")")
    assert not fouten, (
        "Gebruik de infinitief (Verwijderen/Annuleren):\n  " + "\n  ".join(fouten)
    )


def test_geen_leveranciersnaam_in_een_knoplabel():
    """Een knop beschrijft de handeling, niet wie ze uitvoert (§2.12, edc7241).

    Wisselt de betaalprovider ooit, dan hoeft er niets omgetypt te worden — en voor de
    gebruiker doet het er niet toe waar de status vandaan komt.
    """
    fouten = []
    for pad in TEMPLATES:
        for nr, regel in enumerate(_zonder_commentaar(pad).splitlines(), 1):
            for m in KNOPLABEL.finditer(regel):
                if any(naam in m.group(1) for naam in LEVERANCIERS):
                    fouten.append(f"{pad.relative_to(APP)}:{nr}: {m.group(1)!r}")
    assert not fouten, (
        "Beschrijf de handeling, niet de leverancier:\n  " + "\n  ".join(fouten)
    )


def test_geen_rauwe_db_waarde_in_een_badge():
    """§2.12: nooit rauwe codes tonen (#630).

    Vangt de drie gevallen ineens: het taaktype op de werkbank
    (`payment.webhook_mismatch` als badge), de betaalmethode (`online`/`transfer`) en
    de status-fallback — die laatste was een tijdbom, want Mollie kent ook `open`,
    `authorized` en `expired` en die vielen door naar de code.
    """
    # Uitzondering mét reden, zoals de andere allowlists: `Activity.status` is géén
    # DB-code maar een server-side gezet Nederlands label ("Open" / "Voorbij" /
    # "Geannuleerd", activities/router.py:76-80). Daar valt niets te mappen.
    TOEGESTAAN = {("_activiteiten_cards.html", "a.status")}

    fouten = []
    for pad in TEMPLATES:
        for nr, regel in enumerate(_zonder_commentaar(pad).splitlines(), 1):
            m = RAUWE_BADGE.search(regel)
            if not m:
                continue
            veld = m.group(0).split("badge(")[1].strip()
            if (pad.name, veld) in TOEGESTAAN:
                continue
            fouten.append(f"{pad.relative_to(APP)}:{nr}: badge(….{m.group(1)})")
    assert not fouten, (
        "Map naar een leesbaar label vóór je het in een badge zet:\n  "
        + "\n  ".join(fouten)
    )


# Een <button> waarvan de zichtbare inhoud enkel uit symbolen/emoji bestaat.
GLYPH_BUTTON = re.compile(r"<button\b(?P<attrs>[^>]*)>(?P<inhoud>[^<]{1,4})</button>")


def test_symboolknoppen_hebben_een_aria_label_ook_publiek():
    """De bestaande regel keek naar de kit-macro's; deze naar handgeschreven
    <button>-elementen (#631). De verstuurknop van de Raakje-widget stond op élke
    publieke pagina en heette voor een schermlezer "➤"."""
    fouten = []
    for pad in TEMPLATES:
        for nr, regel in enumerate(_zonder_commentaar(pad).splitlines(), 1):
            for m in GLYPH_BUTTON.finditer(regel):
                inhoud = m.group("inhoud").strip()
                if not inhoud or inhoud.isascii() and inhoud.isalnum():
                    continue          # gewone tekst of leeg (Alpine vult die)
                if any(c.isalnum() for c in inhoud):
                    continue          # bevat leesbare tekst
                if "aria-label" in m.group("attrs"):
                    continue
                fouten.append(f"{pad.relative_to(APP)}:{nr}: <button>{inhoud}</button>")
    assert not fouten, (
        "Geef een symboolknop een aria-label — een schermlezer leest anders het "
        "teken voor:\n  " + "\n  ".join(fouten)
    )


def test_kpi_kaarten_zijn_wit():
    """De mock (`.kpi`) kent één vorm: witte kaart met rand, label bóven het cijfer.

    Op Leden was dat met #611 rechtgezet, op Activiteiten bleef een `bg-blue-50`-kaart
    staan — zichtbaar inconsistent tussen twee zusterschermen die hetzelfde soort
    informatie tonen (#636).
    """
    fouten = []
    for pad in TEMPLATES:
        tekst = _zonder_commentaar(pad)
        for nr, regel in enumerate(tekst.splitlines(), 1):
            # Een KPI-kaart herken je aan de kaartvorm mét een getinte achtergrond.
            if "rounded-xl" in regel and "bg-blue-50" in regel:
                fouten.append(f"{pad.relative_to(APP)}:{nr}: {regel.strip()[:70]}")
    assert not fouten, (
        "KPI-kaarten zijn wit met een rand (bg-white border border-line):\n  "
        + "\n  ".join(fouten)
    )


# ── #634: navigatie zonder volledige herlaad ─────────────────────────────────
# De drie regels hieronder bewaken de schil-eigenschappen van hx-boost. Ze staan
# los van de patroon-gates hierboven omdat ze niet over één regel gaan maar over
# de plaats van iets in de template-boom.

# De schillen: alleen dáár horen <script src>-tags en boost-attributen.
SCHILLEN = {"site_base.html", "admin_base.html", "public_base.html", "platform_landing.html"}

# Routes waarvan het antwoord geen te swappen HTML is.
GEEN_HTML_ANTWOORD = re.compile(r'href="[^"]*(/export|/json|/afmelden|\.md)\b')


def test_de_schillen_dragen_hx_boost():
    """Zonder hx-boost op de <body> is elke klik weer een volledige herlaad (#634).

    En omgekeerd: hx-target/hx-select/hx-swap mogen daar NIET staan. htmx zoekt die
    drie op met een closest()-lookup, dus op de <body> erft élke hx-post-knop in de
    app ze — die zou dan `#main` zoeken in een fragmentantwoord en stil niets doen.
    De swap-instructie voor een gebooste navigatie komt uit de responsheaders
    (HX-Retarget/HX-Reselect/HX-Reswap, main.py).
    """
    for naam in ("site_base.html", "admin_base.html"):
        tekst = (APP / "ui" / "templates" / naam).read_text()
        body = tekst.split("<body", 1)[1].split(">", 1)[0]
        assert 'hx-boost="true"' in body, f"{naam}: <body> mist hx-boost"
        for verboden in ("hx-target=", "hx-select=", "hx-swap="):
            assert verboden not in body, (
                f"{naam}: {verboden} op de <body> erft naar elke htmx-actie in de app")
        assert 'id="main"' in tekst, f"{naam}: geen element met id=\"main\" om in te swappen"


def test_downloads_en_afmelden_staan_buiten_de_boost():
    """Een gebooste klik op een download of op uitloggen doet zichtbaar niets (#634)."""
    fouten = []
    for pad in TEMPLATES:
        for nr, regel in enumerate(_zonder_commentaar(pad).splitlines(), 1):
            if not GEEN_HTML_ANTWOORD.search(regel):
                continue
            # De macro-aanroep kan over twee regels lopen: attrs staat dan onder de href.
            venster = "\n".join(_zonder_commentaar(pad).splitlines()[nr - 1:nr + 2])
            # target="_blank" is al genoeg: htmx boost geen link met een target.
            if 'hx-boost="false"' in venster or 'target="_blank"' in venster:
                continue
            fouten.append(f"{pad.relative_to(APP)}:{nr}: {regel.strip()[:100]}")
    assert not fouten, (
        'Zet hx-boost="false" op links naar een download of naar /afmelden:\n  '
        + "\n  ".join(fouten)
    )


def test_geen_scriptbestand_buiten_een_schil():
    """Bibliotheken horen in de <head> van de schil, niet in ingeswapte inhoud (#634).

    htmx voert <script>-tags in geswapte inhoud uit. Trix een tweede keer laden
    faalt op customElements.define('trix-editor'); stt.js/tts.js zouden hun
    document-listeners dubbel ophangen.
    """
    fouten = [
        f"{pad.relative_to(APP)}: {regel.strip()[:90]}"
        for pad in TEMPLATES if pad.name not in SCHILLEN
        for regel in _zonder_commentaar(pad).splitlines()
        if "<script src=" in regel
    ]
    assert not fouten, (
        "Verhuis het script naar de <head> van de schil:\n  " + "\n  ".join(fouten)
    )


def test_geen_metadata_emoji_in_de_templates():
    """✉ 📱 ☎ 📍 🗓 horen als ui.icon() in de kit (#638).

    Ze stonden op de meest bekeken publieke pagina's — de activiteitenkaart op de
    homepage en het gezinsportaal. Op sommige Androids is ☎ een zwart-witte glyph,
    op andere een gekleurde emoji met een eigen regelhoogte; de regel verspringt
    dan. De kit heeft mail, phone, mobile, map-pin en calendar.
    """
    fouten = []
    for pad in TEMPLATES:
        if pad.name == "_macros.html":
            continue        # daar staan de iconen zelf, en de toelichting erbij
        for nr, regel in enumerate(_zonder_commentaar(pad).splitlines(), 1):
            if METADATA_GLYPH.search(regel):
                fouten.append(f"{pad.relative_to(APP)}:{nr}: {regel.strip()[:70]}")
    assert not fouten, (
        'Gebruik ui.icon("mail"/"phone"/"mobile"/"map-pin"/"calendar"):\n  '
        + "\n  ".join(fouten)
    )


def test_lege_toestanden_komen_uit_de_kit():
    """Een schuine "Geen …"-regel is een handgeschreven Empty (#637, §2.11).

    De combinatie is het signaal: `italic` mét een lege-toestandzin. Dat vangt de
    twee fotoschermen zonder aan te slaan op gewone cursieve tekst elders.
    """
    fouten = []
    for pad in TEMPLATES:
        if pad.name == "_macros.html":
            continue
        for nr, regel in enumerate(_zonder_commentaar(pad).splitlines(), 1):
            if "italic" in regel and ("Geen " in regel or "Nog geen " in regel):
                fouten.append(f"{pad.relative_to(APP)}:{nr}: {regel.strip()[:80]}")
    assert not fouten, (
        "Gebruik ui.empty_state(...) — niet schuin, één component:\n  "
        + "\n  ".join(fouten)
    )


# Een submitknop met een eigen opslaan-label: `_("Veld opslaan")` i.p.v. `_("Opslaan")`.
EIGEN_OPSLAAN = re.compile(r'btn_(?:primary|secondary)\(\s*_\("([^"]*\s+opslaan)"\)')


def test_submit_heet_opslaan():
    """§2.12 legt "Opslaan" vast als vaste microcopy voor admin-CRUD (#641).

    De form-builder had "Veld opslaan", "Instellingen opslaan" en "Sectie
    opslaan" — drie varianten voor dezelfde handeling, in één scherm. De knop
    staat in het formulier dat je bewerkt; wát je opslaat is uit de context al
    duidelijk.

    Buiten scope, bewust: de publieke kant (`formulier.html`, "Wijzigingen
    opslaan"). §2.12 Deel A gaat over de beheerkant, en het onderscheid
    eerste-inzending vs. eigen-inzending-bewerken kan daar bewust zijn.
    """
    fouten = []
    for pad in TEMPLATES:
        if pad.name in PUBLIEKE_FORMULIEREN:
            continue
        for nr, regel in enumerate(_zonder_commentaar(pad).splitlines(), 1):
            m = EIGEN_OPSLAAN.search(regel)
            if m:
                fouten.append(f"{pad.relative_to(APP)}:{nr}: {m.group(1)!r}")
    assert not fouten, (
        'Een admin-submit heet "Opslaan" (§2.12):\n  ' + "\n  ".join(fouten)
    )


def test_het_verplicht_sterretje_zit_niet_in_de_labeltekst():
    """Het sterretje hoort uit `label(required=…)` te komen, niet uit de tekst (#646).

    Plak je het sterretje aan de labeltekst — `label(_("E-mail") ~ (" *" if
    hoofdlid else ""), …)` — dan staat het bínnen het label-element en erft het
    `text-gray-700`. Naast een veld dat de parameter wél gebruikt, zie je dan twee
    kleuren sterretje op één rij. Precies dat meldde Koen op /lid-worden: Voornaam
    en Achternaam rood, E-mail en GSM grijs.

    Het is een regel-vormige afwijking (regex-detecteerbaar, vier keer dezelfde
    fout), dus ze hoort hier en niet in een handmatige controle per release.
    B2-conventie 2, docs/ui-conventies.md:383: rood, overal.
    """
    fouten = []
    for pad in TEMPLATES:
        tekst = _zonder_commentaar(pad)
        for nr, regel in enumerate(tekst.splitlines(), 1):
            # (a) het sterretje als string in een label()-aanroep
            if STERRETJE_IN_LABEL_CALL.search(regel):
                fouten.append(f"{pad.relative_to(APP)}:{nr}: {regel.strip()[:100]}")
                continue
            # (b) handgeschreven <label>-markup met een sterretje buiten de rode
            # span — dezelfde fout, zonder de macro.
            if "<label" in regel and "*" in RODE_SPAN.sub("", regel):
                fouten.append(f"{pad.relative_to(APP)}:{nr}: {regel.strip()[:100]}")
    assert not fouten, (
        "Geef het sterretje mee als ui.label(..., required=<bool>) — de parameter is\n"
        "een boolean, dus een vlag kan er rechtstreeks in:\n  " + "\n  ".join(fouten)
    )


def test_kpi_cijfers_zijn_gelijkvormig():
    """Zes KPI-cijfers, zes keer dezelfde opmaak: `text-3xl font-extrabold font-brand` (#647).

    Op /admin/activiteiten stond "Open inschrijvingen" in `text-blue-700` naast
    "Volzette onderdelen" in zwart; /admin/leden deed hetzelfde met Gezinnen. Het
    design-systeem legt voor KPI's alleen het **gewicht** vast (§Weight: extra-bold
    voor paginatitel, KPI-cijfers en het woordmerk) en noemt blauw enkel als
    tegel*achtergrond* (`blue-50 (KPI tiles)`). Een kleur op het cijfer zelf is
    ongedocumenteerd; de geërfde inktkleur is de bedoeling.

    Twee regels dus: geen kleurklasse op het cijfer, en wél `font-brand` — dat
    laatste ontbrak op het dashboard, waardoor hetzelfde soort cijfer daar in Inter
    stond en elders in Radio Canada Big.

    Bewust buiten scope: de dashboardtegels dragen hun kleur op de tegel
    (`bg-blue-50 text-blue-700` op de <a>), niet op het cijfer. Dat is de
    gedocumenteerde vorm en blijft staan — deze regel kijkt enkel naar de regel
    waarop het cijfer zelf staat.
    """
    fouten = []
    for pad in TEMPLATES:
        tekst = _zonder_commentaar(pad)
        for nr, regel in enumerate(tekst.splitlines(), 1):
            if not KPI_CIJFER.search(regel):
                continue
            plek = f"{pad.relative_to(APP)}:{nr}"
            kleuren = [k for k in KLEURKLASSE.findall(regel)]
            if kleuren:
                fouten.append(f"{plek}: kleurklasse op het cijfer: {kleuren}")
            if "font-brand" not in regel:
                fouten.append(f"{plek}: font-brand ontbreekt")
    assert not fouten, (
        "Een KPI-cijfer is `text-3xl font-extrabold font-brand`, zonder eigen kleur:\n  "
        + "\n  ".join(fouten)
    )


def test_een_leeslink_naar_de_bijlage_staat_enkel_in_leesmodus():
    """§2.12: de huidige bijlage staat nooit twee keer tegelijk op het scherm (#653).

    In bewerkmodus hoort ze in het uploadblok, naast de kiezer en haar
    verwijderactie. Een leeslink daarbuiten mag — je wil een bijlage kunnen openen
    zonder eerst te gaan bewerken — maar dan uitsluitend achter `x-show="!edit"`.
    Ontbreekt die, dan lekt ze de bewerkmodus in en staat "Huidige affiche
    bekijken" er twee keer, wat #653 was.

    Bewust alleen de bijlage, en niet de bredere structuurregel die #653
    voorstelde ("een x-data-blok met een bewerkvorm moet een x-show=\"!vlag\"
    bevatten"). Die is geprobeerd en werkt niet als gate: de bewerk-toggle draagt
    zélf een `x-show="!edit"` op zijn "Bewerken"-label, dus het blok lijkt altijd in
    orde — hij zou #653 niet gevangen hebben. Sluit je die knop uit, dan slaat hij
    aan op de onderdeelkop, die volgens de afweging in #648 juist mag blijven
    staan. Op elementniveau lopen kind-elementen van een correct verborgen blok
    weer binnen als valse treffers. Wat overblijft is deze regel: smal, en zonder
    enkele valse treffer.

    De regel kijkt naar links met een `…_asset_url` in de href. In het uploadblok
    komt die uit `ui.upload_field(current_url=…)` en staat er dus geen letterlijke
    `<a href>` in een template — precies daarom is dit machinaal te scheiden.
    """
    fouten = []
    for pad in TEMPLATES:
        for nr, regel in enumerate(_zonder_commentaar(pad).splitlines(), 1):
            if not BEWERKVORM.search(pad.read_text()):
                # Geen bewerkmodus in dit scherm, dus ook geen dubbele bijlage: op
                # een publieke kaart is de affichelink gewoon de link.
                continue
            for tag in BIJLAGE_LINK.findall(regel):
                if 'x-show="!' in regel:
                    continue
                fouten.append(f"{pad.relative_to(APP)}:{nr}: {tag[:90]}")
    assert not fouten, (
        'Zet een leeslink naar de bijlage achter x-show="!edit" (§2.12, #653):\n  '
        + "\n  ".join(fouten)
    )


def test_geen_hint_in_een_kolom_die_op_de_onderkant_uitlijnt():
    """Een `items-end`-vorm lijnt haar kolommen op de ONDERKANT uit (#656).

    Staat er dan onder een invoerveld nog een hintregel, dan is die kolom hoger en
    schuift alles erboven — dus het invoerveld — omhoog. Op /admin/betalingen gaf
    dat een bedragveld dat te hoog stond, en alleen bij een terugbetaling, want de
    hint staat achter een `{% if is_refund %}`. Geen marge- of paddingfout dus: de
    hint hoort niet in een kolom die op haar onderkant uitlijnt.

    `items-start` is niet de oplossing — dan lijnen de knoppen, die geen label
    boven zich hebben, uit met de labels in plaats van met de invoervelden. Zet de
    hint als eigen regel in de vorm: `w-full order-last`.

    De regel zoekt binnen het element dat `items-end` draagt naar een hint-alinea
    zonder `w-full`. Kolomgrenzen zijn met een regex niet te bepalen, dus dit kijkt
    per vorm en niet per kolom: ruimer dan strikt nodig, maar een hint binnen zo'n
    vorm hoort sowieso een eigen regel te zijn.
    """
    def blok_van(tekst: str, pos: int) -> str:
        """Het element dat `items-end` draagt, tot zijn eigen sluittag.

        Niet "tot het volgende items-end": `page_header` in de kit is het enige
        voorkomen in `_macros.html`, dus zo'n venster liep tot het einde van het
        bestand en sleepte elke hint uit de kit mee als valse treffer.
        """
        opens = [m for m in FLEX_OPEN.finditer(tekst) if m.start() < pos]
        if not opens:
            return ""
        start = opens[-1]
        tag = start.group(1)
        diepte = 0
        for t in re.finditer(rf"<{tag}\b|</{tag}>", tekst[start.start():]):
            diepte += -1 if t.group(0).startswith(f"</{tag}") else 1
            if diepte == 0:
                return tekst[start.start():start.start() + t.end()]
        return tekst[start.start():]

    fouten = []
    for pad in TEMPLATES:
        tekst = _zonder_commentaar(pad)
        for m in ITEMS_END.finditer(tekst):
            for tag in HINT_ALINEA.findall(blok_van(tekst, m.start())):
                if "w-full" in tag:
                    continue
                nr = tekst[:m.start()].count("\n") + 1
                fouten.append(f"{pad.relative_to(APP)}:{nr}: {tag[:90]}")
    assert not fouten, (
        "Zet de hint als eigen regel in de vorm (w-full order-last), niet in een "
        "kolom van een items-end-vorm (#656):\n  " + "\n  ".join(fouten)
    )


def test_formuliervelden_komen_uit_de_kit():
    """Een handgeschreven control is een control die uit de pas loopt (#659).

    Koen meldde dat op de "+ Product"-vorm het label "Afrekening" lager staat en de
    dropdown minder hoog is dan de tekstvelden. De diagnose staat omgekeerd: niet de
    dropdown is te klein, de tekstvelden zijn te groot. `_control_base` bevat
    `text-sm`; de select droeg dat wel, de vier handgeschreven inputs niet — grotere
    letter bij dezelfde `py-2` geeft een hoger veld. In dat ene bestand stonden 30
    handgeschreven controls tegen 2 uit de kit, met drie verschillende paddings.

    Wat deze regel NIET is: een toegankelijkheidsprobleem. De zichtbare focusring
    komt uit de base-layer in `scripts/build-css.sh` (`html :where(input…):focus`),
    die élk formulierveld raakt, ook een handgeschreven. De kit-klassen zetten er
    een eigen, iets andere ring overheen. Er is dus geen scherm zonder
    focus-indicatie; dit gaat over maatvoering en één bron van waarheid.

    De allowlist was een telling per bestand tijdens de omzetting; #663 heeft de
    laatste 93 gedaan, dus ze is leeg en deze regel is blokkerend.
    """
    fouten = []
    for pad in TEMPLATES:
        if pad.name == "_macros.html":
            continue
        naam = str(pad.relative_to(APP))
        aantal = sum(1 for tag in HANDGESCHREVEN_CONTROL.findall(pad.read_text())
                     if "border-gray-300" in tag)
        toegestaan = CONTROL_ALLOWLIST.get(naam, 0)
        if aantal > toegestaan:
            fouten.append(f"{naam}: {aantal} handgeschreven controls "
                          f"(toegestaan: {toegestaan})")
        elif aantal < toegestaan:
            fouten.append(f"{naam}: nog {aantal} van de {toegestaan} — verlaag het "
                          "getal in CONTROL_ALLOWLIST (of haal de regel weg)")
    assert not fouten, (
        "Gebruik ui.input_control() / ui.select_control() / ui.field_* (#659):\n  "
        + "\n  ".join(fouten)
    )


def test_geen_teal_badge():
    """§2.10 kent zes tonen; teal hoort er niet bij (#660).

    Hij is in #617 binnengeslopen om te vermijden dat er twee oranje badges naast
    elkaar stonden — status "Terug te betalen" plus type "Terugbetaling". #660 lost
    dat op aan de andere kant: de status wordt geel, gelijk aan "Openstaand", want
    dat ís hetzelfde soort toestand. De richting lees je aan de type-badge.

    De macro kent de toon nog wel; die weghalen zou elke bestaande aanroep stil
    laten terugvallen op grijs. Deze regel houdt hem uit de schermen.
    """
    fouten = _overtredingen(TEAL_BADGE)
    assert not fouten, (
        "Teal is geen semantische toon (§2.10) — kies groen/geel/rood/oranje/"
        "grijs/blauw:\n  " + "\n  ".join(fouten)
    )


def test_een_paginabrede_editor_heeft_annuleren():
    """§2.8: [Opslaan] [Annuleren] onderaan links (#664).

    Op /admin/paginas en /admin/tenants stond alleen Opslaan; de enige terugweg
    was de link bovenaan, na de hele editor. De zes aanmaakschermen deden het al
    goed — dat was het patroon: aanmaken kreeg Annuleren, bewerken een teruglink.

    Annuleren gaat naar de lijst. De teruglink bovenaan blijft staan: die is
    navigatie, niet "verwerp mijn wijzigingen".

    Bereik: templates die zelf de beheerschil uitbreiden. Een editor die als
    fragment leeft — `_cp_detail.html` wordt door zo'n pagina ingesloten — valt er
    niet onder; die is met #664 met de hand rechtgezet. De regel breder maken kan
    niet zonder de rij-formulieren op het activiteitdetail vals te raken: daar
    levert de bewerk-toggle het annuleren, niet een knop in de vorm.
    """
    fouten = []
    for pad in TEMPLATES:
        tekst = _zonder_commentaar(pad)
        if 'extends "admin_base.html"' not in tekst:
            continue
        if '_("Opslaan")' in tekst and '_("Annuleren")' not in tekst:
            fouten.append(str(pad.relative_to(APP)))
    assert not fouten, (
        "Zet [Annuleren] naast [Opslaan] in een paginabrede editor (§2.8):\n  "
        + "\n  ".join(fouten)
    )


def test_elk_bewerkformulier_heeft_annuleren_naast_opslaan():
    """§2.8, per FORMULIER in plaats van per pagina (#694).

    De regel hierboven kijkt naar paginabrede editors. Die grens was een compromis:
    haar docstring zei dat breder gaan de rij-formulieren op het activiteitdetail
    vals zou raken, "want daar levert de bewerk-toggle het annuleren". Dat argument
    is met #694 vervallen — §2.8 zegt uitdrukkelijk dat een toggle bovenaan de knop
    onderaan niet vervangt. Wie een formulier open heeft staan kijkt naar beneden,
    niet terug naar het icoon waarmee hij het opende.

    Meting bij het schrijven van deze regel: zeven formulieren in vier bestanden
    misten Annuleren — de drie in de formulierbouwer die Koen meldde, twee op het
    activiteitdetail, en de bewerkrijen in het gebruikers- en het medialijstje.
    Alle zeven zijn rechtgezet; deze gate houdt het zo.

    Waarom een gate en geen afspraak: er bestond geen controle die een ONTBREKENDE
    knop vangt — de andere regels kijken naar verboden klassen. Zo bleef de bouwer
    op 3 om 0 staan terwijl vier andere bewerkschermen het paar wél hadden.

    "Opslaan" is bewust de haak, niet elke submitknop: "Toevoegen", "Zoeken" en
    "Importeren" horen géén Annuleren te krijgen. Bij die drie is er niets om te
    verwerpen — je begint iets, je onderbreekt niets.
    """
    vorm = re.compile(r"<form\b.*?</form>", re.S)
    fouten = []
    for pad in TEMPLATES:
        for stuk in vorm.findall(_zonder_commentaar(pad)):
            if '_("Opslaan")' in stuk and '_("Annuleren")' not in stuk:
                regel = _zonder_commentaar(pad)[:_zonder_commentaar(pad).index(stuk)].count("\n") + 1
                fouten.append(f"{pad.relative_to(APP)}:{regel}")
    assert not fouten, (
        "Elk formulier met [Opslaan] hoort ook [Annuleren] te tonen (§2.8). Bij een "
        "toggle-paneel sluit Annuleren het paneel; bij een rij die altijd openstaat "
        "laadt hij het lijstfragment opnieuw, zodat het typwerk vervalt:\n  "
        + "\n  ".join(fouten)
    )


def test_geen_losse_glyphs_meer_voor_verwijderen_en_bewerken():
    """§1.5/§2.12 (#698): één betekenis per teken.

    `×` betekende in deze app al "sluiten" — de toast sluit ermee, en dat is een
    gratis handeling. Datzelfde teken gebruiken voor "verwijder deze optie met haar
    sprongregel en haar id" laat twee handelingen van heel verschillend gewicht er
    identiek uitzien. Het tandwiel betekent *instellingen*, en dat staat op het
    formulierscherm bovenaan als een échte knop die iets anders doet.

    Bereik: knop-macro's. De `×` in `fotos_album.html` en `_raakje_widget.html` zijn
    échte sluitknoppen en blijven — daarom kijkt deze regel naar `btn_danger`/
    `btn_secondary` met een glyph als label, en niet naar het teken op zichzelf.
    """
    fouten = []
    for pad in TEMPLATES:
        tekst = _zonder_commentaar(pad)
        for glyph, hoort in (("×", "trash-2"), ("⚙", "pencil")):
            for macro in ("btn_danger", "btn_secondary", "btn_primary", "btn_outline"):
                if f'{macro}("{glyph}"' in tekst:
                    fouten.append(
                        f"{pad.relative_to(APP)}: {macro}(\"{glyph}\") — gebruik "
                        f'lead_icon="{hoort}" met een leeg label')
    assert not fouten, "Losse glyphs op knoppen (§1.5, #698):\n  " + "\n  ".join(fouten)


def test_een_symboolknop_krijgt_ook_een_tooltip():
    """De `button`-macro geeft een knop zónder zichtbare tekst een `title` op grond
    van zijn `aria_label` (#698).

    Een bronregel op de macro, want dit is juist bedoeld om per knop niets te
    hoeven doen: staat het hier, dan is élke symboolknop in de app gedekt en kan de
    volgende het niet vergeten.
    """
    macros = (APP / "ui" / "templates" / "_macros.html").read_text(encoding="utf-8")
    kop = macros[macros.index("{% macro button("):macros.index("{% macro btn_primary(")]
    assert 'title="{{ aria_label }}"' in kop, (
        "de button-macro zet geen tooltip; dan moet elke symboolknop het zelf doen")
    assert "{% if not label %}" in kop, (
        "de tooltip hoort alleen op een knop zonder zichtbare tekst — anders "
        "herhaalt hij wat er al staat")
