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


def test_geneste_opsomming_met_twee_spaties():
    """#790 — de regressie die een datum tot activiteit maakte.

    Modellen springen geneste lijsten in met **twee** spaties; dat is wat CommonMark
    voorschrijft en wat `react-markdown` in v1.14 correct nestte. python-markdown
    eist er vier en maakte van de subregels BROERS, zodat "15 januari 2026 om 19:32"
    als eigen activiteit in de lijst stond.

    Deze test is rood op de oude renderer — dat is het punt: hij toetst het
    onderwerp en niet de gelukkige toestand.
    """
    html = render_answer_markdown(
        "- **Wandelen** (Miloheem)\n"
        "  - 15 januari 2026 om 19:32\n"
        "  - 21 mei 2026 om 19:00\n"
        "- **Comedy Festival** (Miloheem)\n")

    assert html.count("<ul>") == 2, (
        "de datums staan niet in een eigen lijst — ze zijn broers van de activiteit "
        f"geworden:\n{html}")
    # De geneste <ul> hoort BINNEN het <li> van de activiteit te staan, niet ernaast.
    eerste_li = html.index("<li>")
    assert eerste_li < html.index("<ul>", eerste_li), (
        f"de geneste lijst staat naast het item in plaats van erin:\n{html}")
    assert html.count("<li>") == 4  # twee activiteiten + twee datums


def test_een_zacht_regeleinde_blijft_een_regeleinde():
    """`breaks=True` vervangt de `nl2br`-extensie van de oude parser.

    Zonder deze test zou "zet de parser om" ook groen staan met twee regels die aan
    elkaar geplakt worden — CommonMark negeert een enkel regeleinde standaard.
    """
    html = render_answer_markdown("regel een\nregel twee")

    assert "<br" in html, f"het zachte regeleinde is verdwenen:\n{html}"


def test_ruwe_html_wordt_gesaneerd():
    # LLM-uitvoer is semi-vertrouwd: <script> en on*-handlers mogen er nooit door.
    html = render_answer_markdown("Hoi<script>alert(1)</script> en <img src=x onerror=alert(1)>")
    assert "<script>" not in html and "onerror" not in html
    assert "Hoi" in html


def test_javascript_link_scheme_geweerd():
    """Een `javascript:`-URL mag nooit een klikbare link worden.

    De vorm van de assertie is bij #790 aangepast, en de reden hoort erbij. Ze zocht
    de tekst `javascript:` ergens in de uitvoer. Met python-markdown klopte dat: die
    maakte er een `<a>` van, nh3 gooide de href weg en enkel het woord "klik" bleef
    staan. markdown-it is strenger — het weigert het schema al bij het parsen en
    laat de hele regel als **gewone tekst** staan, dus `[klik](javascript:alert(1))`
    verschijnt letterlijk. Dat is veiliger én het liet de oude assertie omvallen op
    tekst die niets doet.

    Wat we dus toetsen is de invariant zelf: geen enkele `href` wijst naar
    `javascript:`. Met daarbij een positieve controle — een gewone https-link wordt
    wél een link — want zonder haar staat deze test ook groen als er nooit meer een
    link gerenderd wordt.
    """
    import re

    html = render_answer_markdown("[klik](javascript:alert(1))")
    hrefs = re.findall(r'href="([^"]*)"', html)
    assert not [h for h in hrefs if h.strip().lower().startswith("javascript:")], (
        f"er staat een klikbare javascript-link in:\n{html}")

    goed = render_answer_markdown("[Raak](https://example.org/pagina)")
    assert 'href="https://example.org/pagina"' in goed, (
        f"een gewone link wordt niet meer gerenderd — dan bewijst de test hierboven "
        f"niets:\n{goed}")


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
