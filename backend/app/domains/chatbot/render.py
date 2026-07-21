"""Markdown → veilige HTML voor Raakje-antwoorden (#566).

Mistral levert zijn antwoord in markdown (de system-prompt gebruikt zelf
``**vet**`` en opsommingen). Vroeger rende de React-widget dat met
``react-markdown``; na de React-exit werd het antwoord als platte tekst
ge-echood, zodat de opmaaktekens letterlijk op het scherm kwamen.

Deze module zet de markdown server-side om naar HTML en saneert het resultaat
met nh3 (dezelfde stored-XSS-guard als de CMS-render, #476). LLM-uitvoer is
semi-vertrouwd, dus de allowlist is bewust strak: géén ``<img>``/``<table>``
(geen tracking-pixels of layout-injectie) — enkel tekstopmaak, lijsten en links.
"""
from __future__ import annotations

from typing import Optional

import markdown as _markdown
import nh3

# Enkel de tags die python-markdown voor tekstopmaak produceert. nh3 verwijdert
# al de rest (<script>, on*-handlers) en staat enkel veilige URL-schema's toe
# (blokkeert javascript:). 'rel' NIET vermelden op <a> — nh3 beheert dat zelf.
_ALLOWED_TAGS = {
    "p", "br", "hr", "span",
    "strong", "b", "em", "i", "u", "s",
    "ul", "ol", "li",
    "a", "code", "pre", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6",
}
_ALLOWED_ATTRS = {"a": {"href", "title"}, "*": {"class"}}


def render_answer_markdown(text: Optional[str]) -> str:
    """Zet een Raakje-antwoord (markdown) om naar gesaneerde HTML.

    Leeg/None → lege string. Het resultaat is veilig om met ``| safe`` in een
    template te plaatsen.
    """
    if not text:
        return ""
    html = _markdown.markdown(text, extensions=["sane_lists", "nl2br"])
    return nh3.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS)
