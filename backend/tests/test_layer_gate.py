"""Laag-gate (#635): een UI-route bouwt een view-model en kiest een template.

Sinds de React-exit (#405) zit de scheiding tussen scherm en business-logica niet
meer in een netwerkgrens maar in discipline — en discipline die nergens wordt
afgedwongen, zakt terug. Deze gate dwingt ze af. Model: `test_import_boundaries.py`
(AST, geen regex: een regex mist `db.query` in een helper en slaat aan op
commentaar).

De drie regels, elk met de reden:

1. **Imports.** Een UI-module importeert uit een domein enkel `api.py`. Geen
   `<domein>.models` (dan schrijft ze zelf queries), geen `<domein>.router` of
   `*_router` (dan is de JSON-router de facto de servicelaag), geen `app.models`,
   en geen private naam uit een andere module — `forms/admin_ui.py` importeerde
   `_apply_fields` en `_validate_form_payload` uit `forms/router.py`.
2. **ORM-gebruik.** Een UI-module houdt `db` enkel vast om hem door te geven. Elke
   `db.<iets>` — query, commit, add, delete, flush — is een overtreding: de
   transactiegrens hoort in de service, zodat élke ingang (JSON-router, UI-route,
   script) dezelfde regel volgt. `db` doorgeven als argument mag.
3. **Wat de facade doorlaat.** `api.py` mag ORM-klassen exporteren voor de
   *services* van andere domeinen — dat is de architectuur — maar een UI-module
   mag ze er niet uit halen: dan is "via de facade" alsnog een rauwe query. Idem
   voor routerfuncties die via een facade doorgelust worden.

4. **De context komt uit een view-model** (#643-F). Een letterlijke dict als
   context van `TemplateResponse` is geen belofte: een verkeerde of vergeten
   sleutel merk je pas bij het renderen. `<Scherm>View(ViewModel).as_context()` is
   dat wél, en de template-variabelen-gate kan er dan tegen toetsen.

Plus een scoperegel (#635-J5): alles in `app/ui/` dat een `APIRouter` bevat, moet
op `_ui.py` eindigen. Anders ontsnapt een nieuw scherm aan de gate door zijn naam.

De allowlist bevat de overtreders van vóór dit issue en krimpt per stap naar leeg
(#635 stap I). Een regel toevoegen mag, maar niet stilzwijgend: het is een
zichtbare diff in deze test, met de reden in de commit.
"""
import ast
import importlib
import inspect
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parents[1] / "app"

# `_` is de vertaalfunctie (app.i18n), niet een private naam van een andere
# module — de hele codebase importeert hem zo. Enige uitzondering op regel 1.
VERTAALFUNCTIE = ("app.i18n", "_")

# app/ui/admin_api.py is JSON, geen UI: hij hangt onder /api/v1/admin, staat in het
# OpenAPI-schema en gebruikt de JWT-deurwachter (get_current_admin). Hij valt dus
# buiten de laag-gate, maar staat hier bij naam genoemd i.p.v. stil te ontsnappen
# aan de scoperegel hieronder. (#635 stap A: "beslis en documenteer".)
JSON_IN_UI_PAKKET = {"admin_api.py"}

# ── Allowlist ────────────────────────────────────────────────────────────────
# (module, regel) waarbij regel ∈ {"imports", "orm", "facade"}. Leeg = eindtoestand.
# Schermen die hun context nog als letterlijke dict doorgeven (#643-F). Krimpt met
# elke batch die op een view-model overgaat; payment staat er al niet meer in.
VIEWMODEL_ALLOWLIST: set[str] = {
    "app.domains.activities.admin_ui",
    "app.domains.activities.ui",
    "app.domains.auth.admin_ui",
    "app.domains.auth.ui",
    "app.domains.chatbot.ui",
    "app.domains.cms.admin_ui",
    "app.domains.cms.ui",
    "app.domains.forms.admin_ui",
    "app.domains.forms.ui",
    "app.domains.mdm.ui",
    "app.domains.media.admin_ui",
    "app.domains.media.ui",
    "app.domains.membership.ui",
    "app.ui.system_ui",
}

LAYER_ALLOWLIST: set[tuple[str, str]] = {
    # ── regel 1: imports uit models/router, of een private naam ──────────────
    ("app.domains.activities.admin_ui", "imports"),
    ("app.domains.activities.ui", "imports"),
    ("app.domains.auth.admin_ui", "imports"),
    ("app.domains.auth.ui", "imports"),
    ("app.domains.chatbot.ui", "imports"),
    ("app.domains.cms.admin_ui", "imports"),
    ("app.domains.cms.ui", "imports"),
    ("app.domains.forms.admin_ui", "imports"),
    ("app.domains.forms.ui", "imports"),
    ("app.domains.mail.ui", "imports"),
    ("app.domains.mdm.ui", "imports"),
    ("app.domains.media.admin_ui", "imports"),
    ("app.domains.media.ui", "imports"),
    ("app.domains.membership.ui", "imports"),
    # ── regel 2: rauw ORM-gebruik in de routebody ────────────────────────────
    ("app.domains.activities.admin_ui", "orm"),
    ("app.domains.activities.ui", "orm"),
    ("app.domains.auth.admin_ui", "orm"),
    ("app.domains.chatbot.ui", "orm"),
    ("app.domains.cms.admin_ui", "orm"),
    ("app.domains.cms.ui", "orm"),
    ("app.domains.forms.admin_ui", "orm"),
    ("app.domains.forms.ui", "orm"),
    ("app.domains.mail.ui", "orm"),
    ("app.domains.mdm.ui", "orm"),
    ("app.domains.media.admin_ui", "orm"),
    ("app.domains.media.ui", "orm"),
    ("app.domains.membership.ui", "orm"),
    ("app.domains.payment.ui", "orm"),
    ("app.domains.workflow.ui", "orm"),
    ("app.ui.tenants_ui", "orm"),
    # ── regel 3: ORM-klassen en routerfuncties die via een facade binnenkomen ─
    ("app.domains.activities.admin_ui", "facade"),
    ("app.domains.activities.ui", "facade"),
    ("app.domains.auth.admin_ui", "facade"),
    ("app.domains.chatbot.ui", "facade"),
    ("app.domains.cms.admin_ui", "facade"),
    ("app.domains.cms.ui", "facade"),
    ("app.domains.forms.admin_ui", "facade"),
    ("app.domains.forms.ui", "facade"),
    ("app.domains.mail.ui", "facade"),
    ("app.domains.mdm.ui", "facade"),
    ("app.domains.media.admin_ui", "facade"),
    ("app.domains.media.ui", "facade"),
    ("app.domains.membership.ui", "facade"),
    ("app.domains.payment.ui", "facade"),
    ("app.domains.workflow.ui", "facade"),
    ("app.ui.changes_ui", "facade"),
    ("app.ui.system_ui", "facade"),
    ("app.ui.tenants_ui", "facade"),
}


def _ui_paden() -> list[Path]:
    return sorted(
        list(APP.glob("domains/*/ui.py"))
        + list(APP.glob("domains/*/admin_ui.py"))
        + list(APP.glob("ui/*_ui.py"))
    )


def _module(pad: Path) -> str:
    return ".".join(pad.relative_to(APP.parent).with_suffix("").parts)


def _verboden_module(mod: str) -> bool:
    """Modules waar een UI-bestand niet uit mag importeren."""
    if mod.startswith("app.models"):
        return True
    delen = mod.split(".")
    if len(delen) >= 4 and delen[:2] == ["app", "domains"]:
        laatste = delen[3]
        return laatste == "models" or laatste == "router" or laatste.endswith("_router")
    return False


def _import_overtredingen(pad: Path) -> list[str]:
    fouten = []
    for node in ast.walk(ast.parse(pad.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        if _verboden_module(node.module):
            fouten.append(f"regel {node.lineno}: import uit {node.module}")
            continue
        for alias in node.names:
            if alias.name.startswith("_") and (node.module, alias.name) != VERTAALFUNCTIE:
                fouten.append(f"regel {node.lineno}: private naam "
                              f"{node.module}.{alias.name}")
    return fouten


def _orm_overtredingen(pad: Path) -> list[str]:
    """Elke `db.<attr>`. Een kale `db` als argument doorgeven blijft toegestaan."""
    return [
        f"regel {node.lineno}: db.{node.attr}"
        for node in ast.walk(ast.parse(pad.read_text(encoding="utf-8")))
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "db"
    ]


def _facade_namen(pad: Path) -> dict[str, set[str]]:
    """Per domein de namen die dit UI-bestand uit `<domein>.api` haalt."""
    uit_api: dict[str, set[str]] = {}
    for node in ast.walk(ast.parse(pad.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.ImportFrom) or not node.module:
            continue
        delen = node.module.split(".")
        if len(delen) == 4 and delen[:2] == ["app", "domains"] and delen[3] == "api":
            uit_api.setdefault(delen[2], set()).update(a.name for a in node.names)
    return uit_api


def _melding(regel: str, treffers: dict[str, list[str]]) -> str:
    blokken = [f"  {mod}:\n" + "\n".join(f"    {r}" for r in fouten)
               for mod, fouten in sorted(treffers.items())]
    return f"{regel}\n" + "\n".join(blokken)


def test_ui_importeert_geen_models_routers_of_private_namen():
    """#635 regel 1: uit een domein komt alleen `api.py`, en daaruit alleen publieks."""
    treffers = {}
    for pad in _ui_paden():
        mod = _module(pad)
        if (mod, "imports") in LAYER_ALLOWLIST:
            continue
        fouten = _import_overtredingen(pad)
        if fouten:
            treffers[mod] = fouten
    assert not treffers, _melding(
        "Een UI-module importeert uit een domein enkel api.py (#635 regel 1):", treffers)


def test_ui_raakt_de_sessie_niet_zelf_aan():
    """#635 regel 2: `db` gaat door de UI heen, niet erin."""
    treffers = {}
    for pad in _ui_paden():
        mod = _module(pad)
        if (mod, "orm") in LAYER_ALLOWLIST:
            continue
        fouten = _orm_overtredingen(pad)
        if fouten:
            treffers[mod] = fouten
    assert not treffers, _melding(
        "Zet de query/commit in <domein>/service.py en roep die aan (#635 regel 2):",
        treffers)


def test_de_facade_geeft_de_ui_geen_ormklassen_of_routerfuncties():
    """#635 regel 3: een ORM-klasse via `api.py` is alsnog een rauwe query.

    Deze regel importeert echt — statisch zie je niet dat `mdm.api.Member` een
    mapped class is, of dat `membership.api.create_member` via een lazy
    `__getattr__` uit de router komt.
    """
    treffers = {}
    for pad in _ui_paden():
        mod = _module(pad)
        if (mod, "facade") in LAYER_ALLOWLIST:
            continue
        fouten = []
        for domein, namen in _facade_namen(pad).items():
            try:
                api = importlib.import_module(f"app.domains.{domein}.api")
            except Exception as exc:  # pragma: no cover - alleen bij een kapotte facade
                pytest.fail(f"{mod}: {domein}.api niet importeerbaar: {exc}")
            for naam in sorted(namen):
                obj = getattr(api, naam, None)
                if obj is None:
                    continue
                if hasattr(obj, "__table__"):
                    fouten.append(f"{domein}.api.{naam} is een ORM-klasse")
                elif (inspect.isfunction(obj)
                      and obj.__module__.rsplit(".", 1)[-1].endswith("router")):
                    fouten.append(f"{domein}.api.{naam} komt uit "
                                  f"{obj.__module__} (routerfunctie)")
        if fouten:
            treffers[mod] = fouten
    assert not treffers, _melding(
        "Laat de service teruggeven wat het scherm nodig heeft (#635 regel 3):",
        treffers)


def test_een_scherm_ontsnapt_niet_aan_de_gate_via_zijn_naam():
    """#635-J5: alles in app/ui/ met een APIRouter heet `*_ui.py`.

    Zonder deze regel valt een nieuw scherm buiten de scope door het `admin_beheer.py`
    te noemen. De JSON-composer staat bij naam in JSON_IN_UI_PAKKET.
    """
    fouten = []
    for pad in sorted(APP.glob("ui/*.py")):
        if pad.name.endswith("_ui.py") or pad.name in JSON_IN_UI_PAKKET:
            continue
        if "APIRouter" in pad.read_text(encoding="utf-8"):
            fouten.append(f"app/ui/{pad.name} bevat een APIRouter maar heet geen *_ui.py")
    assert not fouten, "\n  ".join(["Hernoem het bestand of zet het bij de JSON-kant:"] + fouten)


def _letterlijke_contexten(pad: Path) -> list[str]:
    """TemplateResponse-aanroepen met een dict-literal als context."""
    fouten = []
    for node in ast.walk(ast.parse(pad.read_text(encoding="utf-8"))):
        if not (isinstance(node, ast.Call)
                and getattr(node.func, "attr", None) == "TemplateResponse"):
            continue
        context = node.args[2] if len(node.args) >= 3 else next(
            (k.value for k in node.keywords if k.arg == "context"), None)
        if isinstance(context, ast.Dict):
            fouten.append(f"regel {node.lineno}: letterlijke dict als context")
    return fouten


def test_de_template_context_komt_uit_een_view_model():
    """#643 regel 4: geen dict-literal als template-context.

    Een dict is geen belofte. Geef je `{"totaal": ...}` door aan een template die
    `total` leest, dan rendert Jinja stil leeg (StrictUndefined vangt dat pas bij
    het renderen) en heeft mypy niets om op te controleren. Een `ViewModel` legt
    op één plek vast wat het scherm krijgt, en de template-variabelen-gate kan er
    statisch tegen toetsen.
    """
    treffers = {}
    for pad in _ui_paden():
        mod = _module(pad)
        if mod in VIEWMODEL_ALLOWLIST:
            continue
        fouten = _letterlijke_contexten(pad)
        if fouten:
            treffers[mod] = fouten
    assert not treffers, _melding(
        "Bouw een <Scherm>View(ViewModel) en geef .as_context() door (#643-F):",
        treffers)
