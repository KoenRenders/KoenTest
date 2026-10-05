"""Gate: when a view transition runs is decided in ONE place (#1591).

`ui.htmx_ux` — the script both shells share — lets a view transition run only
for a navigation: a boosted request, or a swap that updates the address. Until
#1591 that was said per swap, with `transition:false` in an `hx-swap`, an
`HX-Reswap` header or an `htmx.ajax` call: the Assistent's button and panel
(K8), a refusal's banner and a recalculated total (#1599), a proposal for a
form. Eleven places, and every swap that forgot it cross-faded the whole page.

So a template, a route or a script that sets `transition:` itself is refused:
it either repeats the rule (and hides that the rule exists) or fights it. A
swap that must have a transition and is no navigation does not exist yet; when
one does, it is a change to the rule, with its reason, not an exception beside
it.

Proven red with ADDITIVE violations (run, restored): `hx-swap="innerHTML
transition:false"` added to an element of `home.html`; `"HX-Reswap":
"innerHTML transition:true"` added to a header dict in `app/ui/__init__.py`;
`swap: 'outerHTML transition:false'` added to `raakje-panel.js` — each named
by the first test. The second test was proven by removing `ui.htmx_ux()` from
`site_base.html`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_serverrendered

APP = Path(__file__).resolve().parents[1] / "app"
_SETTING = re.compile(r"transition\s*:\s*(?:true|false)\b")
_JINJA_COMMENT = re.compile(r"{#.*?#}", re.S)


def _sources() -> dict[str, str]:
    found = {}
    for path in APP.rglob("*"):
        if path.suffix not in (".html", ".py", ".js") or "vendor" in path.parts:
            continue
        if "tests" in path.parts or "__pycache__" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".html":
            text = _JINJA_COMMENT.sub("", text)
        found[str(path.relative_to(APP))] = text
    assert len(found) > 400, f"only {len(found)} files read — the walk looks nowhere"
    assert "ui/templates/_macros.html" in found and "static/raakje-panel.js" in found
    assert "ui/__init__.py" in found
    return found


def settings(text: str) -> list[str]:
    return _SETTING.findall(text)


def test_no_template_route_or_script_sets_a_transition_itself():
    found = [
        f"{rel}: {len(settings(text))} × `transition:` — the rule stands in `ui.htmx_ux`"
        for rel, text in sorted(_sources().items())
        if settings(text)
    ]
    assert found == []


def test_both_shells_run_the_rule():
    """The rule is the listener in `ui.htmx_ux`; a shell that switches view
    transitions on without it cross-fades every swap again."""
    sources = _sources()
    kit = sources["ui/templates/_macros.html"]
    script = kit[kit.index("{% macro htmx_ux()") :]
    script = script[: script.index("{%- endmacro %}")]
    assert "addEventListener('htmx:beforeTransition'" in script
    assert "if (d.boosted) return;" in script and "e.preventDefault();" in script
    for needed in ("HX-Push-Url", "HX-Replace-Url", "[hx-push-url], [hx-replace-url]"):
        assert needed in script, f"the rule no longer reads {needed}"
    shells = [rel for rel, text in sources.items() if '"globalViewTransitions":true' in text]
    assert sorted(shells) == ["ui/templates/admin_base.html", "ui/templates/site_base.html"], shells
    for rel in shells:
        assert "{{ ui.htmx_ux() }}" in sources[rel], f"{rel} runs view transitions without the rule"


@pytest.mark.parametrize(
    "violation",
    [
        '<div hx-get="/x" hx-swap="innerHTML transition:false"></div>',
        'headers={"HX-Reswap": "innerHTML transition:true"}',
        "htmx.ajax('GET', url, { swap: 'outerHTML transition: false' })",
    ],
)
def test_a_setting_is_recognised_and_css_is_not(violation):
    assert settings(violation)
    assert not settings(".a{transition:opacity .2s}  transition: transform 150ms ease;")
    assert not settings("a view transition is for a navigation: a boosted request")
