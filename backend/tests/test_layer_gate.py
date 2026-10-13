"""Refuses a UI route that imports models or routers, touches the session, or passes its template context as a dict · hard · since #635.

Laag-gate (#635): een UI-route bouwt een view-model en kiest een template.

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
   dat wél, en de template-variabelen-gate kan er dan tegen toetsen. Sinds #1950
   ziet de gate ook een context die via een NAAM binnenkomt: een variabele die
   dezelfde functie een dict geeft (literal, `dict(...)`, comprehension), ook als er
   later sleutels bijkomen (`context["x"] = …`, `.update(…)`) of ze verspreid wordt
   (`{**context, …}`). Niet gevolgd, bewust: een context uit een helper (ook in
   dezelfde module), een parameter, en `view.as_context()` waar de aanroeper nog
   iets aan toevoegt. Bewezen met een additieve overtreding (een wegwerpfunctie
   `context = {"a": 1}` in `app/ui/organisaties_ui.py` → de gate noemt
   `app.ui.organisaties_ui`, daarna weggehaald) en met `_dict_contexts` op kleine
   bronnen, die ook tellen wat ze doorlopen.

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

from tests._bestanden import bestanden

APP = Path(__file__).resolve().parents[1] / "app"

# `_` is de vertaalfunctie (app.i18n), niet een private naam van een andere
# module — de hele codebase importeert hem zo. Enige uitzondering op regel 1.
VERTAALFUNCTIE = ("app.i18n", "_")

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

# Leeg, en dat is de bedoelde eindtoestand (#679 afgerond). Wat hier stond was
# het activiteitenbeheer, dat CRUD-functies aanriep die nog in
# `activities/router.py` woonden. Ze zijn met de bewerking zelf mee verhuisd naar
# `activities/service.py` — geen twintig doorgeeffacades, die zouden deze gate
# groen zetten zonder dat er iets verandert. Zet er niets bij zonder issue: een
# uitzondering hoort tijdelijk te zijn en een nummer te dragen.
LAYER_ALLOWLIST: set[tuple[str, str]] = set()


def _ui_paden() -> list[Path]:
    return bestanden(
        APP.glob("domains/*/ui.py"),
        APP.glob("domains/*/admin_ui.py"),
        APP.glob("ui/*_ui.py"),
        wat="alle UI-modules (domains/*/ui.py, admin_ui.py, ui/*_ui.py)",
        minstens=10,
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
                fouten.append(f"regel {node.lineno}: private naam {node.module}.{alias.name}")
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
    blokken = [
        f"  {mod}:\n" + "\n".join(f"    {r}" for r in fouten)
        for mod, fouten in sorted(treffers.items())
    ]
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
        "Een UI-module importeert uit een domein enkel api.py (#635 regel 1):", treffers
    )


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
        "Zet de query/commit in <domein>/service.py en roep die aan (#635 regel 2):", treffers
    )


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
                elif inspect.isfunction(obj) and obj.__module__.rsplit(".", 1)[-1].endswith(
                    "router"
                ):
                    fouten.append(f"{domein}.api.{naam} komt uit {obj.__module__} (routerfunctie)")
        if fouten:
            treffers[mod] = fouten
    assert not treffers, _melding(
        "Laat de service teruggeven wat het scherm nodig heeft (#635 regel 3):", treffers
    )


def test_een_scherm_ontsnapt_niet_aan_de_gate_via_zijn_naam():
    """#635-J5: alles in app/ui/ met een APIRouter heet `*_ui.py`.

    Zonder deze regel valt een nieuw scherm buiten de scope door het `admin_beheer.py`
    te noemen. (The one named exception, the JSON composer `admin_api.py`, lost its
    routes with CR-13 phase 4b and its name with phase 4c, #1251.)
    """
    fouten = []
    for pad in bestanden(APP.glob("ui/*.py"), wat="de modules in app/ui/", minstens=3):
        if pad.name.endswith("_ui.py"):
            continue
        if "APIRouter" in pad.read_text(encoding="utf-8"):
            fouten.append(f"app/ui/{pad.name} bevat een APIRouter maar heet geen *_ui.py")
    assert not fouten, "\n  ".join(["Hernoem het bestand of zet het bij de JSON-kant:"] + fouten)


def _dict_form(node: ast.AST) -> str | None:
    """What kind of dict an expression is, or None when it is none of the three:
    a literal (also with `**` spread), a comprehension, a call of `dict`."""
    if isinstance(node, ast.Dict):
        return "letterlijke dict"
    if isinstance(node, ast.DictComp):
        return "dict-comprehension"
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "dict":
        return "dict(...)"
    return None


def _own_nodes(function: ast.AST) -> list[ast.AST]:
    """The nodes of one function, without those of the functions inside it: a
    name means one thing per function, and a nested one is its own pass."""
    found: list[ast.AST] = []
    todo = list(ast.iter_child_nodes(function))
    while todo:
        node = todo.pop()
        found.append(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        todo.extend(ast.iter_child_nodes(node))
    return found


def _dict_contexts(source: str) -> tuple[int, list[str]]:
    """(how many template responses were walked, the contexts that are a dict).

    A dict is no promise (#643-F): a wrong or forgotten key shows only when the
    template renders. Followed, per function (#1950):

    - a context written as the argument — a literal (`{**context, "x": 1}`
      included), `dict(...)` or a comprehension (the form of #643);
    - a context passed as a NAME that the same function assigns one of those
      forms — also when keys are added afterwards (`context["x"] = …`,
      `context.update(…)`), because the dict is what it was assigned.

    Knowingly NOT followed: a context returned by a helper (in this module or
    another: `context = _build(request)`), a name that is a parameter or comes
    from an attribute, and a name assigned `view.as_context()` and then added to
    — that one holds what a view-model promised, and the keys added are the
    caller's. The gate ends where the syntax tree does.
    """
    walked = 0
    findings: list[str] = []
    for function in ast.walk(ast.parse(source)):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        nodes = _own_nodes(function)
        assigned: dict[str, tuple[int, str]] = {}
        for node in nodes:
            targets: list[ast.expr] = []
            value: ast.AST | None = None
            if isinstance(node, ast.Assign):
                targets, value = node.targets, node.value
            elif isinstance(node, ast.AnnAssign) and node.value is not None:
                targets, value = [node.target], node.value
            form = _dict_form(value) if value is not None else None
            if form is None:
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    assigned.setdefault(target.id, (node.lineno, form))
        for node in nodes:
            if not (
                isinstance(node, ast.Call)
                and getattr(node.func, "attr", None) == "TemplateResponse"
            ):
                continue
            walked += 1
            context = (
                node.args[2]
                if len(node.args) >= 3
                else next((k.value for k in node.keywords if k.arg == "context"), None)
            )
            form = _dict_form(context) if context is not None else None
            if form is not None:
                findings.append(f"regel {node.lineno}: {form} als context")
            elif isinstance(context, ast.Name) and context.id in assigned:
                line, form = assigned[context.id]
                findings.append(
                    f"regel {node.lineno}: context `{context.id}` is een {form} (regel {line})"
                )
    return walked, sorted(findings, key=lambda f: int(f.split()[1].rstrip(":")))


def _letterlijke_contexten(pad: Path) -> list[str]:
    """The contexts of this module that are a dict, in any form followed."""
    return _dict_contexts(pad.read_text(encoding="utf-8"))[1]


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
        "Bouw een <Scherm>View(ViewModel) en geef .as_context() door (#643-F):", treffers
    )


# ── The gate's own proof (#1950) ─────────────────────────────────────────────
# A gate that walks nothing is green for ever (#678). These tests run the detector
# on small sources: every form it follows must be seen, and what it knowingly does
# not follow must stay quiet — and still be WALKED, so "no finding" means "looked".

_RESPONSE = 'return templates.TemplateResponse(request, "page.html", {name})\n'

FLAGGED = {
    "a literal as the argument": "def f(request):\n    " + _RESPONSE.format(name='{"a": 1}'),
    "a literal with a spread": (
        "def f(request, context):\n    " + _RESPONSE.format(name='{**context, "b": 2}')
    ),
    "dict(...) as the argument": "def f(request):\n    " + _RESPONSE.format(name="dict(a=1)"),
    "a comprehension as the argument": (
        "def f(request):\n    " + _RESPONSE.format(name="{k: 1 for k in range(3)}")
    ),
    "a name assigned a literal": (
        'def f(request):\n    context = {"a": 1}\n    ' + _RESPONSE.format(name="context")
    ),
    "a name assigned dict(...)": (
        "def f(request):\n    context = dict(a=1)\n    " + _RESPONSE.format(name="context")
    ),
    "a name assigned a comprehension": (
        "def f(request):\n    context = {k: 1 for k in range(3)}\n    "
        + _RESPONSE.format(name="context")
    ),
    "a name with keys added by subscript": (
        'def f(request):\n    context = {"a": 1}\n    context["b"] = 2\n    '
        + _RESPONSE.format(name="context")
    ),
    "a name with keys added by update": (
        'def f(request):\n    context = {"a": 1}\n    context.update(b=2)\n    '
        + _RESPONSE.format(name="context")
    ),
    "an annotated name": (
        'def f(request):\n    context: dict = {"a": 1}\n    ' + _RESPONSE.format(name="context")
    ),
    "the context as a keyword": (
        'def f(request):\n    context = {"a": 1}\n    '
        'return templates.TemplateResponse(request, "p.html", context=context)\n'
    ),
    "an async route": (
        'async def f(request):\n    context = {"a": 1}\n    ' + _RESPONSE.format(name="context")
    ),
    "a name assigned in an if": (
        'def f(request, x):\n    if x:\n        context = {"a": 1}\n    '
        + _RESPONSE.format(name="context")
    ),
}

QUIET = {
    "a view-model": (
        "def f(request):\n    view = PageView(a=1)\n    "
        + _RESPONSE.format(name="view.as_context()")
    ),
    "a name assigned as_context()": (
        "def f(request):\n    context = PageView(a=1).as_context()\n    "
        + _RESPONSE.format(name="context")
    ),
    "as_context() with a key added (the caller's, not a dict assigned)": (
        'def f(request):\n    context = PageView(a=1).as_context()\n    context["oob"] = True\n    '
        + _RESPONSE.format(name="context")
    ),
    "a context handed in as a parameter": (
        "def f(request, context):\n    " + _RESPONSE.format(name="context")
    ),
    "a context from a helper (not followed)": (
        "def f(request):\n    context = _build(request)\n    " + _RESPONSE.format(name="context")
    ),
    "a dict of another function": (
        'def g():\n    context = {"a": 1}\n    return context\n\n'
        "def f(request, context):\n    " + _RESPONSE.format(name="context")
    ),
    "a dict assigned to another name": (
        'def f(request):\n    other = {"a": 1}\n    view = PageView(a=other)\n    '
        + _RESPONSE.format(name="view.as_context()")
    ),
}


@pytest.mark.parametrize("source", list(FLAGGED.values()), ids=list(FLAGGED))
def test_the_gate_follows_every_form_of_a_dict_context(source):
    walked, findings = _dict_contexts(source)
    assert walked == 1, "the detector did not walk the template response"
    assert len(findings) == 1 and "dict" in findings[0], findings


@pytest.mark.parametrize("source", list(QUIET.values()), ids=list(QUIET))
def test_the_gate_stays_quiet_where_it_does_not_follow(source):
    walked, findings = _dict_contexts(source)
    assert walked == 1, "the detector did not walk the template response"
    assert findings == [], findings


def test_a_nested_function_is_its_own_scope():
    """A name means one thing per function: the dict of the outer one is not the
    context of the inner."""
    source = (
        'def outer(request):\n    context = {"a": 1}\n\n'
        "    def inner(request, context):\n        "
        + _RESPONSE.format(name="context")
        + "    return inner\n"
    )
    walked, findings = _dict_contexts(source)
    assert walked == 1 and findings == []


def test_the_gate_walks_the_template_responses_of_the_screens():
    """It counts what it walks (#678): 234 template responses on 13 October 2026 (231 after #1931).
    The floor is a good deal under that and still far above what a broken
    discovery of the modules would give."""
    walked = sum(_dict_contexts(pad.read_text(encoding="utf-8"))[0] for pad in _ui_paden())
    assert walked >= 150, f"the gate walks only {walked} template responses"
