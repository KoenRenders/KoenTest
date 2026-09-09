"""Markdown → veilige HTML voor Raakje-antwoorden (#566).

Mistral levert zijn antwoord in markdown (de system-prompt gebruikt zelf
``**vet**`` en opsommingen). Vroeger rende de React-widget dat met
``react-markdown``; na de React-exit werd het antwoord als platte tekst
ge-echood, zodat de opmaaktekens letterlijk op het scherm kwamen.

Deze module zet de markdown server-side om naar HTML en saneert het resultaat
met nh3 (dezelfde stored-XSS-guard als de CMS-render, #476). LLM-uitvoer is
semi-vertrouwd, dus de allowlist is bewust strak: géén ``<img>``/``<table>``
(geen tracking-pixels of layout-injectie) — enkel tekstopmaak, lijsten en links.

**De parser is CommonMark sinds #790, en dat is geen smaakkwestie.** Hij was
python-markdown, en dat is géén CommonMark: het eist **vier** spaties om een
geneste lijst te herkennen. Modellen schrijven er **twee** — conform CommonMark,
en precies wat ``react-markdown`` in v1.14 correct nestte. Gevolg op het scherm:
de datums onder een activiteit werden broers van die activiteit, zodat
"15 januari 2026 om 19:32" er als een activiteit bij stond. Er is geen instelling
die python-markdown op twee spaties zet (``sane_lists`` gaat hier niet over), dus
het was de parser zelf. Een regressie uit de React-exit, ingeslopen bij #566.

``breaks`` staat UIT (#794), en dat is teruggedraaid ten opzichte van #790. Het
kwam van de ``nl2br``-extensie (#566), maar v1.14 draaide ``react-markdown``
**zonder plugins** — geen ``remark-breaks`` — dus daar viel een los regeleinde
samen tot een spatie en bleef een antwoord compact. Met ``breaks=True`` werd elk
regeleinde dat het model toevallig zet een zichtbare breuk, en dan begint de
locatie van een activiteit op een eigen regel. Een echte alinea-overgang (een lege
regel) werkt gewoon, want dat is CommonMark.

``hr`` staat niet in de allowlist, om dezelfde reden (#794): een streep door de
tekstballon draagt geen informatie, en nh3 haalt hem dus weg. Koppen blijven wél
staan — bewust asymmetrisch. nh3 verwijdert een tag maar houdt de tekst, dus een
gestripte kop wordt een losse zin midden in de flow: slechter dan de kop zelf.
Grendel wat leeg is, laat de systeem-prompt oplossen wat betekenis heeft.

Raw HTML in de markdown passeert de parser (de ``commonmark``-preset laat het
door) en wordt daarna door nh3 verwijderd. Dat is bewust dezelfde verdeling als
voorheen — python-markdown deed het net zo — en houdt nh3 de ENIGE XSS-grens.
Twee plekken die allebei half saneren is moeilijker te beoordelen dan één die het
helemaal doet.
"""
from __future__ import annotations

from typing import Optional

import nh3
from markdown_it import MarkdownIt

# Enkel de tags die de parser voor tekstopmaak produceert. nh3 verwijdert
# al de rest (<script>, on*-handlers) en staat enkel veilige URL-schema's toe
# (blokkeert javascript:). 'rel' NIET vermelden op <a> — nh3 beheert dat zelf.
_ALLOWED_TAGS = {
    # 'hr' hoort hier NIET (#794) — zie de opmerking bovenaan. 'br' blijft: het model
    # kan er zelf een zetten met twee spaties op het regeleinde, en dat is dan een
    # bedoelde breuk.
    "p", "br", "span",
    "strong", "b", "em", "i", "u", "s",
    "ul", "ol", "li",
    "a", "code", "pre", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6",
}
_ALLOWED_ATTRS = {"a": {"href", "title"}, "*": {"class"}}

# Eén parser voor het hele proces: hij is stateloos tussen `render()`-aanroepen.
# `breaks` expliciet op False, ook al is dat de standaard van de preset: de vorige
# stand was True en zonder deze regel is niet te zien dat het een keuze is.
_MD = MarkdownIt("commonmark", {"breaks": False})


def render_answer_markdown(text: Optional[str]) -> str:
    """Zet een Raakje-antwoord (markdown) om naar gesaneerde HTML.

    Leeg/None → lege string. Het resultaat is veilig om met ``| safe`` in een
    template te plaatsen.
    """
    if not text:
        return ""
    html = _MD.render(text)
    return nh3.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS)
