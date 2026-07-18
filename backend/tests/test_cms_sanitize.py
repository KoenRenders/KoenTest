"""CMS-inhoud wordt bij render gesanitized (#476, stored-XSS-guard) — de
server-side vervanger van de oude DOMPurify. Enkel de door de editor geproduceerde
tags/attributen blijven; scripts, event-handlers en javascript:-URL's verdwijnen.
"""
from app.domains.cms.api import sanitize_cms_html


def test_strips_script_and_event_handlers():
    dirty = '<p onclick="steal()">Hallo <script>evil()</script>wereld</p>'
    clean = sanitize_cms_html(dirty)
    assert "<script>" not in clean
    assert "onclick" not in clean
    assert "evil()" not in clean
    assert "Hallo" in clean and "wereld" in clean and "<p>" in clean


def test_blocks_javascript_url_but_keeps_safe_link():
    dirty = '<a href="javascript:alert(1)">x</a> <a href="https://raakmillegem.be">ok</a>'
    clean = sanitize_cms_html(dirty)
    assert "javascript:" not in clean
    assert 'href="https://raakmillegem.be"' in clean


def test_keeps_editor_formatting():
    ok = ("<h2>Titel</h2><p><strong>vet</strong> <em>schuin</em></p>"
          "<ul><li>een</li><li>twee</li></ul><blockquote>citaat</blockquote>")
    clean = sanitize_cms_html(ok)
    for tag in ("<h2>", "<strong>", "<em>", "<ul>", "<li>", "<blockquote>"):
        assert tag in clean


def test_trix_output_tags_survive_sanitisation():
    """#520: Trix produceert o.a. <div>, <strong>, <em>, <h1>, <a>, <blockquote>,
    <pre>, <ul>/<li> — die moeten de sanitisatie overleven (geen inhoudsverlies bij
    de editor-omschakeling van execCommand naar Trix), terwijl een script nog steeds
    sneuvelt."""
    trix = ('<h1>Kop</h1><div>Regel met <strong>vet</strong> en <em>schuin</em>.</div>'
            '<ul><li>een</li><li>twee</li></ul><blockquote>citaat</blockquote>'
            '<pre>code</pre><a href="https://raakmillegem.be">link</a>'
            '<script>evil()</script>')
    clean = sanitize_cms_html(trix)
    for tag in ("<h1>", "<div>", "<strong>", "<em>", "<ul>", "<li>",
                "<blockquote>", "<pre>", 'href="https://raakmillegem.be"'):
        assert tag in clean, tag
    assert "<script>" not in clean and "evil()" not in clean


def test_none_and_empty_passthrough():
    assert sanitize_cms_html(None) is None
    assert sanitize_cms_html("") == ""
