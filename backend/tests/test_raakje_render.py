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


def test_een_zacht_regeleinde_blijft_op_dezelfde_regel():
    """#794 — dit draait #790 terug, en de reden hoort erbij.

    Bij #790 stond `breaks=True`, overgenomen van de `nl2br`-extensie uit #566. Maar
    v1.14 draaide `react-markdown` **zonder plugins** — geen `remark-breaks` — dus
    daar viel een los regeleinde samen tot een spatie en bleef een antwoord compact.
    Met `breaks=True` werd elk regeleinde dat het model toevallig zet een zichtbare
    breuk, en begon de locatie van een activiteit op een eigen regel.

    Rood op de code van #790: die zette hier een `<br>`.
    """
    html = render_answer_markdown("- **Wandeling** (Miloheem)\n  15 januari, gratis")

    assert "<br" not in html, (
        f"een zacht regeleinde wordt nog steeds een breuk:\n{html}")
    assert "Miloheem" in html and "15 januari" in html


def test_een_lege_regel_geeft_nog_steeds_een_nieuwe_alinea():
    """De tegenproef op de vorige: `breaks` uitzetten mag niet doorschieten.

    Zonder deze test zou "plak alles aan elkaar" ook groen staan, en dan loopt een
    antwoord van twee alinea's als één blok tekst door.
    """
    html = render_answer_markdown("Eerste alinea.\n\nTweede alinea.")

    assert html.count("<p>") == 2, f"de alinea-overgang is verdwenen:\n{html}"


def test_een_scheidingslijn_haalt_de_ballon_niet_uit_elkaar():
    """#794 — `hr` staat niet meer in de allowlist.

    Let op de vorm van de assertie: hij kijkt naar de UITVOER, niet naar de
    brontekst. Zoeken of `---` verdwenen is zou ook slagen terwijl de streep er
    gewoon staat — nh3 verwijdert de tag, niet het bronteken.

    Koppen blijven bewust wél toegestaan: nh3 houdt de tekst van een verwijderde tag,
    dus een gestripte kop wordt een losse zin midden in de flow. Een streep draagt
    geen informatie, dus die kost niets om weg te halen.
    """
    html = render_answer_markdown("Eerste deel\n\n---\n\nTweede deel")

    assert "<hr" not in html, f"de tekstballon wordt nog in stukken gesneden:\n{html}"
    assert "Eerste deel" in html and "Tweede deel" in html

    # De asymmetrie, in dezelfde test zodat ze niet los van elkaar sneuvelt:
    kop = render_answer_markdown("## Activiteiten")
    assert "<h2>" in kop, "koppen horen wél toegestaan te blijven (#794)"


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


def test_de_systeemprompt_zegt_hoe_een_activiteitenlijst_eruitziet():
    """#794 — de eigenlijke oorzaak zat in de prompt, niet in de renderer.

    Dezelfde vraag gaf op dezelfde commit de ene keer één regel per activiteit en de
    andere keer koppen met sublijsten en strepen ertussen. Dat is logisch: over de
    présentatievorm stond er niets in `SYSTEM_PERSONA`, dus was ze aan het toeval
    overgelaten.

    **Wat deze test wel en niet doet.** Ze bewaakt dat de instructie er stáát; ze kan
    niet bewijzen dat het model haar volgt — dat kan geen enkele test, en daarom zijn
    de twee grendels hierboven (`breaks` uit, `hr` geweerd) er ook. Zonder deze test
    verdwijnt de instructie ooit stilletjes bij een herschrijving van de persona en
    komt het toeval terug.
    """
    from app.domains.chatbot.context import SYSTEM_PERSONA

    assert "EEN opsommingsregel per activiteit" in SYSTEM_PERSONA
    for verboden in ("GEEN sublijst", "GEEN scheidingslijn", "GEEN\n  koppen"):
        assert verboden.replace("\n  ", " ") in " ".join(SYSTEM_PERSONA.split()), (
            f"de persona verbiedt '{verboden}' niet meer")


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
