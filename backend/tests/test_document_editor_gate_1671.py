"""The document-editor gates (CR-17 phase 1, #1671, slice 2; C6 tests 3 and 14).

Three rules, each with a reason, proven by violations made during the build
(named in the docstrings; the proof was additive — a throwaway template
written for the gate, never an existing one edited):

1. **One toolbar (C6 3, gate 14 widened).** The editor exists in exactly
   one template (the `ui.document_editor` macro) and one script; a domain
   template that writes its own toolbar or editor configuration is the
   third copy of the editor — the drift #528 closed for the kit.
2. **Vendored and pinned (C6 14).** The bundle's checksum stands in
   scripts/vendor-manifest.txt; the CSP header is pinned exactly — the
   editor loads from our own origin, so widening her (an eval, a CDN) is a
   decision that belongs in a review, not in a bundle change. Every script
   src goes through `statisch()` — that rule lives in ONE gate, widened in
   `test_ui_conventions_gate.py` (rule 33, #773), not duplicated here.
3. **Three sets (C6 9)** — an unknown set is a `ValueError`; that gate
   stands in test_schema_one_source_1671.py with the set-shape rules.
"""

import hashlib
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
MACROS = APP / "ui" / "templates" / "_macros.html"

#: The CSP the shared Caddy serves, pinned exactly (C6 14; CR-17's C1
#: measured her on 6 October 2026). The header's NAME is Caddy's
#: `{$CSP_HEADER_NAME}` map; the VALUE is what a browser sees, and this is
#: it, character for character. The editor loads from /static/vendor/ —
#: inside 'self' — so any change here is a decision, not a necessity.
PINNED_CSP = (
    "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
    "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://{$STATS_UAT_DOMAIN} "
    "https://{$STATS_PROD_DOMAIN}; connect-src 'self' https://{$STATS_UAT_DOMAIN} "
    "https://{$STATS_PROD_DOMAIN}; frame-ancestors 'none'; base-uri 'self'; "
    "form-action 'self'; object-src 'none'"
)


def _templates() -> list[Path]:
    return sorted(APP.rglob("*.html"))


def test_the_editor_exists_in_one_template_only():
    """C6 3: `data-document-editor` may stand in exactly one template — the
    macro. Proven by writing the attribute into a throwaway domain template:
    this test failed naming her, and passes again once she is gone."""
    holders = [p for p in _templates() if "data-document-editor" in p.read_text()]
    assert holders == [MACROS], f"the editor stands outside the macro: {holders}"


def test_no_template_writes_the_bundles_global_or_configuration():
    """C6 3: `RaakTiptap` (the bundle's global) and `schema_for` (the
    editor's configuration) belong to the script and the view-model — a
    template that names either hand-writes what the macro and the JS own."""
    for template in _templates():
        content = template.read_text()
        assert "RaakTiptap" not in content, f"{template.name} writes the editor itself"
        assert "schema_for" not in content, f"{template.name} writes editor configuration"


def test_the_editor_files_load_only_where_an_editor_stands():
    """C6 14 + B4 (Koen, 7 October 2026, option a): the bundle, her chrome,
    the shared figure rules and the editor's script load with the
    `ui.document_editor` macro — on the pages that carry an editor, and
    only there. Never in the admin shell: a back-office screen without an
    editor carries none of her 441 KB of JavaScript. Slice 2 loaded the
    shell for the whole back office (one editor page existed); slice 3
    put the editor on the page screen, and Koen chose the per-page load.
    Proven by adding the bundle back to the admin shell: this test failed
    naming her, and passes again once the shell carries none of it."""
    for template in _templates():
        if template == MACROS:
            continue
        content = template.read_text()
        assert "tiptap-3.31.4" not in content, f"{template.name} loads the bundle outside the macro"
        assert "document-editor.js" not in content, (
            f"{template.name} loads the editor's script outside the macro"
        )
    macros = MACROS.read_text()
    assert "vendor/tiptap-3.31.4.min.js" in macros, "the macro no longer loads the bundle"
    assert "vendor/tiptap-3.31.4.css" in macros, "the macro no longer loads the editor's chrome"
    assert "document-editor.js" in macros, "the macro no longer loads the editor's script"
    # On real lines, not anywhere in the file: the macro's comments name the
    # files too, and a gate a comment satisfies is no gate (measured).
    macro_links = [
        line.strip()
        for line in macros.splitlines()
        if ("<link" in line or "<script" in line) and "prose-figures.css" in line
    ]
    assert macro_links, "the macro no longer links the figure rules"


def test_the_bundle_matches_the_manifest():
    """C6 14: the bundle is pinned by checksum in scripts/vendor-manifest.txt
    — a rebuilt bundle that differs must be a decision, not a surprise (the
    build script itself refuses a drifted rebuild)."""
    bundle = APP / "static" / "vendor" / "tiptap-3.31.4.min.js"
    manifest = (ROOT / "scripts" / "vendor-manifest.txt").read_text()
    checksum = hashlib.sha256(bundle.read_bytes()).hexdigest()
    assert checksum in manifest, "the bundle does not match scripts/vendor-manifest.txt"
    # The licences travel with the bundle (review B2, #1699): MIT asks that
    # the notice goes along with the copies, and the build drops them.
    licences = APP / "static" / "vendor" / "tiptap-3.31.4.LICENSES"
    assert licences.exists() and "tiptap" in manifest, "the licence notice is missing"


def test_the_csp_is_unchanged():
    """C6 14: the CSP header is pinned exactly — a gate that checks seven
    parts lets an added CDN through (the review's remark, #1699). The
    pinned value is the one CR-17's C1 measured on 6 October 2026."""
    snippet = (ROOT / "caddy" / "parts" / "snippets.caddy").read_text()
    line = next(
        (r for r in snippet.splitlines() if "Content-Security-Policy" in r and "default-src" in r),
        None,
    )
    assert line is not None, "the CSP line is missing from caddy/parts/snippets.caddy"
    value = line.split('"', 2)[1] if '"' in line else ""
    assert value == PINNED_CSP, f"the CSP changed:\n  pinned: {PINNED_CSP}\n  actual: {value}"
