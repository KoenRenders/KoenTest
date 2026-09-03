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

Uitzonderingen staan expliciet in ALLOWLIST, met reden — zoals de allowlists in
de andere gates: een regel toevoegen mag, maar niet stilzwijgend.
"""
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
