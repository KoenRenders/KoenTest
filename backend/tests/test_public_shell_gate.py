"""CR-11 pilot B, P1 (#1588): one public shell — what a public template may not
bring back (B7 gate 1).

Block 11 (Koen, 4 October 2026; `docs/design-system-end-state.md` §2.5): the
header and the footer of the public site are `site_base.html`'s, and what they
carry stands there once.

1. **a second header or footer** — a `<header`, a `<footer`, the classes
   `site-header` / `site-footer`, or the drawer's id in any template but the
   shell (an article's own `<header>` inside the content is not a shell: the
   rule reads templates that extend `site_base.html` and what they include);
2. **the newsletter's call outside the footer** — a link to `/nieuwsbrief` in a
   public template that is not the shell and not the newsletter's own pages;
3. **the account's items written twice** — "Uitloggen" or a link to `/admin` in
   the shell itself: both places (the menu and the drawer) call
   `_site_account.html`;
4. **the free footer block** — `footer_block` in any template: the CMS block
   `site-footer` is no longer rendered.

Proven red, additively — each rule on a throwaway text that adds one violation
to a clean one — and the gate counts what it read.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"
SHELL = "site_base.html"
#: The newsletter's own pages: they are where the call leads.
NEWSLETTER_PAGES = re.compile(r"^(_nb_|nieuwsbrief|newsletter)")

_COMMENT = re.compile(r"{#.*?#}", re.S)
_INCLUDE = re.compile(r'{%-?\s*include\s+"([^"]+)"')
_SHELL_PARTS = re.compile(
    r"<header\b|<footer\b|site-header|site-footer|site-nav-mobiel|site-drawer"
)
_NEWSLETTER = re.compile(r"""path_for\(\s*['"]/nieuwsbrief['"]\s*\)|href=["']/nieuwsbrief["']""")
_ACCOUNT = re.compile(r"""_\(\s*["']Uitloggen["']\s*\)|href=["']/admin["']""")


def _templates() -> dict[str, str]:
    return {p.name: _COMMENT.sub("", p.read_text()) for p in APP.rglob("templates/*.html")}


def _public_pages(templates: dict[str, str]) -> dict[str, str]:
    """Every template that extends the public shell, with what it includes."""

    def family(name: str, seen: set[str]) -> set[str]:
        if name in seen or name not in templates:
            return seen
        seen.add(name)
        for included in _INCLUDE.findall(templates[name]):
            family(included, seen)
        return seen

    pages = {}
    for name, text in templates.items():
        if re.search(r'{%-?\s*extends\s+"site_base\.html"', text):
            pages[name] = "\n".join(templates[n] for n in sorted(family(name, set())))
    return pages


def second_shell(text: str) -> list[str]:
    return _SHELL_PARTS.findall(text)


def newsletter_call(text: str) -> bool:
    return bool(_NEWSLETTER.search(text))


def test_the_gate_reads_the_public_pages():
    templates = _templates()
    pages = _public_pages(templates)
    assert len(pages) >= 10, sorted(pages)
    assert "home.html" in pages
    # The shell is what the rules would refuse anywhere else.
    assert second_shell(templates[SHELL]) and newsletter_call(templates[SHELL])


def test_no_public_page_brings_a_second_header_or_footer():
    wrong = {
        name: found
        for name, text in _public_pages(_templates()).items()
        if (found := second_shell(text))
    }
    assert not wrong, f"a header or footer outside the shell (rule 1): {wrong}"


def test_the_newsletters_call_stands_only_in_the_footer():
    wrong = sorted(
        name
        for name, text in _public_pages(_templates()).items()
        if newsletter_call(text) and not NEWSLETTER_PAGES.match(name)
    )
    assert not wrong, f"a call to the newsletter outside the footer (rule 2): {wrong}"


def test_the_shell_writes_the_account_items_nowhere_itself():
    templates = _templates()
    assert not _ACCOUNT.search(templates[SHELL]), (
        "the shell writes an account item itself — both places call _site_account.html (rule 3)"
    )
    assert templates[SHELL].count("account.items(") == 2
    assert _ACCOUNT.search(templates["_site_account.html"])


def test_no_template_renders_the_free_footer_block():
    wrong = sorted(name for name, text in _templates().items() if "footer_block" in text)
    assert not wrong, f"the `site-footer` block is no longer rendered (rule 4): {wrong}"


CLEAN = """{% extends "site_base.html" %}
{% block content %}<h1>{{ page.title }}</h1><div class="cms-content">{{ content|safe }}</div>{% endblock %}"""


@pytest.mark.parametrize(
    "addition",
    [
        '<footer class="mt-8">© Raak</footer>',
        '<header class="site-header">x</header>',
        '<div id="site-nav-mobiel"></div>',
    ],
)
def test_a_second_shell_part_is_refused(addition):
    assert not second_shell(CLEAN)
    assert second_shell(CLEAN.replace("{% endblock %}", addition + "{% endblock %}")), addition


def test_a_newsletter_call_on_a_page_is_refused():
    assert not newsletter_call(CLEAN)
    assert newsletter_call(CLEAN + """<a href="{{ path_for('/nieuwsbrief') }}">Nieuwsbrief</a>""")
    assert newsletter_call(CLEAN + '<a href="/nieuwsbrief">Nieuwsbrief</a>')
