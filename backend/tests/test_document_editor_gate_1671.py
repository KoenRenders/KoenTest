"""The document-editor gates (CR-17 phase 1, #1671, slice 2; C6 tests 3 and 14).

Three rules, each with a reason, proven by violations made during the build
(named in the docstrings; the proof was additive — a template written for
the gate, never an existing one edited):

1. **One toolbar (C6 3, gate 14 widened).** The editor exists in exactly
   one template (the `ui.document_editor` macro) and one script; a domain
   template that writes its own toolbar or editor configuration is the
   third copy of the editor — the drift #528 closed for the kit.
2. **Vendored and pinned (C6 14).** The bundle's checksum stands in
   scripts/vendor-manifest.txt; every `<script src>` goes through
   `statisch()` (so: /static/); the CSP header is unchanged — the editor
   loads from the same origin, so nothing had to give.
3. **Three sets (C6 9)** — an unknown set is a `ValueError`; that gate
   stands in test_schema_one_source_1671.py with the set-shape rules.
"""

import hashlib
import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
MACROS = APP / "ui" / "templates" / "_macros.html"
ADMIN_SHELL = APP / "ui" / "templates" / "admin_base.html"


def _templates() -> list[Path]:
    return sorted(APP.rglob("*.html"))


def test_the_editor_exists_in_one_template_only():
    """C6 3: `data-document-editor` may stand in exactly one template — the
    macro. Proven by writing the attribute into a throwaway domain template:
    this test failed naming her, and passes again once she is gone."""
    houders = [p for p in _templates() if "data-document-editor" in p.read_text()]
    assert houders == [MACROS], f"de editor staat buiten de macro: {houders}"


def test_no_template_writes_the_bundles_global_or_configuration():
    """C6 3: `RaakTiptap` (the bundle's global) and `schema_for` (the
    editor's configuration) belong to the script and the view-model — a
    template that names either hand-writes what the macro and the JS own."""
    for template in _templates():
        inhoud = template.read_text()
        assert "RaakTiptap" not in inhoud, f"{template.name} schrijft de editor zelf"
        assert "schema_for" not in inhoud, f"{template.name} schrijft editorconfiguratie"


def test_the_tiptap_bundle_loads_in_the_admin_shell_only():
    """C6 14: the vendored files load once in the shell (#634's rule 21 in
    spirit), and only in the admin — the editor is a back-office component
    until slice 3 puts her on the page screen."""
    for template in _templates():
        if template == ADMIN_SHELL:
            continue
        assert "tiptap-3.31.4" not in template.read_text(), (
            f"{template.name} laadt de bundel buiten de schil"
        )
    shell = ADMIN_SHELL.read_text()
    assert "vendor/tiptap-3.31.4.min.js" in shell
    assert "vendor/tiptap-3.31.4.css" in shell
    assert "document-editor.js" in shell


def test_the_bundle_matches_the_manifest():
    """C6 14: the bundle is pinned by checksum in scripts/vendor-manifest.txt
    — a rebuilt bundle that differs must be a decision, not a surprise."""
    bundle = APP / "static" / "vendor" / "tiptap-3.31.4.min.js"
    manifest = (ROOT / "scripts" / "vendor-manifest.txt").read_text()
    checksum = hashlib.sha256(bundle.read_bytes()).hexdigest()
    assert checksum in manifest, "de bundel klopt niet met scripts/vendor-manifest.txt"


def test_every_script_src_is_served_from_static():
    """C6 14: no `<script src=` outside /static/ — every src goes through
    `statisch()`. Proven by writing a template with a CDN src: this test
    failed naming her, and passes again once she is gone.

    The one sanctioned exception is the public analytics include
    (`_umami.html`, #176): her src is the tenant's configured analytics
    address, she stands on the public shell only, and no admin screen
    carries her — the editor shares no page with her."""
    patroon = re.compile(r'<script[^>]+src="([^"]*)"')
    fouten = []
    for template in _templates():
        if template.name == "_umami.html":
            continue
        for match in patroon.finditer(template.read_text()):
            if "statisch(" not in match.group(1):
                fouten.append(f"{template.name}: {match.group(1)}")
    assert not fouten, f"script buiten /static/: {fouten}"


def test_the_csp_is_unchanged():
    """C6 14: the CSP header is unchanged — the editor loads from our own
    origin, so widening her (an eval, a CDN) is a decision that belongs in
    a review, not in a bundelaanpassing. The pinned line is the one CR-17's
    C1 measured on 6 October 2026."""
    snippet = (ROOT / "caddy" / "parts" / "snippets.caddy").read_text()
    regel = next(
        (r for r in snippet.splitlines() if "Content-Security-Policy" in r and "default-src" in r),
        None,
    )
    assert regel is not None, "de CSP-regel ontbreekt uit caddy/parts/snippets.caddy"
    for onderdeel in (
        "default-src 'self'",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'",
        "style-src 'self' 'unsafe-inline'",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ):
        assert onderdeel in regel, f"de CSP veranderde: {onderdeel} ontbreekt"
