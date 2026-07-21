"""Raakje-regressies (v2.0.0): markdown-rendering (#566), STT-mic in de widget
(#567) en TTS-toggle (#568). De invariant die telt: het antwoord toont opmaak
i.p.v. ruwe markdown, en LLM-uitvoer wordt gesaneerd (geen stored/reflected XSS).
"""
from app.domains.chatbot.render import render_answer_markdown


# ── #566: markdown → veilige HTML ───────────────────────────────────────────

def test_bold_wordt_strong():
    html = render_answer_markdown("Kom naar **Irrland**!")
    assert "<strong>Irrland</strong>" in html
    assert "**" not in html


def test_opsomming_wordt_lijst():
    html = render_answer_markdown("- Irrland\n- Brood en Spelen")
    assert "<ul>" in html and html.count("<li>") == 2


def test_ruwe_html_wordt_gesaneerd():
    # LLM-uitvoer is semi-vertrouwd: <script> en on*-handlers mogen er nooit door.
    html = render_answer_markdown("Hoi<script>alert(1)</script> en <img src=x onerror=alert(1)>")
    assert "<script>" not in html and "onerror" not in html
    assert "Hoi" in html


def test_javascript_link_scheme_geweerd():
    html = render_answer_markdown("[klik](javascript:alert(1))")
    assert "javascript:" not in html


def test_lege_invoer():
    assert render_answer_markdown(None) == ""
    assert render_answer_markdown("") == ""


# ── #566 end-to-end: het /raakje/vraag-fragment rendert de markdown ─────────

def test_antwoordfragment_rendert_markdown_niet_als_ruwe_tekst(client, monkeypatch):
    from app.config import settings
    from app.domains.chatbot import service
    monkeypatch.setattr(settings, "chat_enabled", True)
    # Gecontroleerd markdown-antwoord i.p.v. afhankelijk van de mock-provider.
    monkeypatch.setattr(service, "run_chat",
                        lambda *a, **k: "Kom naar **Irrland**!\n\n- 16 augustus\n- 29 augustus")
    resp = client.post("/raakje/vraag", data={"vraag": "Wat is er te doen?"})
    assert resp.status_code == 200
    assert "<strong>Irrland</strong>" in resp.text   # markdown werd gerenderd
    assert "<li>" in resp.text
    assert "**Irrland**" not in resp.text             # geen ruwe markdown meer


# ── #567/#568: de zwevende widget draagt mic + voorlees-toggle + scripts ────

def test_widget_heeft_mic_en_tts(client, monkeypatch):
    from app.config import settings
    monkeypatch.setattr(settings, "chat_enabled", True)
    html = client.get("/").text
    assert 'data-stt-target="#raakje-widget-vraag"' in html   # STT-mic (#567)
    assert "data-tts-toggle" in html                          # TTS-toggle (#568)
    assert "/static/stt.js" in html and "/static/tts.js" in html
