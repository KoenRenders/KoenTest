"""Vervang placeholders in CMS-inhoud door actuele waarden uit de configuratie.

Beheerders typen in de CMS-editor codes zoals ``{{lidgeld_vol}}`` of
``{{halfprijs_start}}``. Bij het tonen op de publieke site worden die vervangen
door de echte waarden uit de app-configuratie (en dus uit de .env). Zo blijft de
tekst in sync met de ingestelde prijzen/datums zonder dat een beheerder de
bedragen handmatig moet bijwerken.

Let op: vervanging gebeurt alleen op de PUBLIEKE leesendpoints. De admin-/
editor-endpoints geven de ruwe codes terug, zodat ze bewerkbaar blijven.
"""
import json
import re
from html import escape, unescape
from typing import Dict, Optional

import nh3

# Sanitisatie-allowlist voor CMS-inhoud (#476): dezelfde soort bescherming als de
# oude DOMPurify (React), maar server-side. Enkel de tags/attributen die de
# WYSIWYG-editor produceert; nh3 verwijdert al de rest (<script>, on*-handlers) en
# staat enkel veilige URL-schema's toe (blokkeert javascript:). Toegepast op élk
# publiek renderpunt via render_cms_content.
_ALLOWED_TAGS = {
    "p", "br", "hr", "span", "div",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    # `del` en `ins` horen bij "wat de WYSIWYG-editor produceert": Trix schrijft
    # doorstreepte tekst als <del>. Stond er niet in, dus doorstrepen werkte in de
    # editor en was na het opslaan spoorloos — in het CMS net zo goed als in de
    # vergadernotities (#939, gemeten).
    "a", "strong", "b", "em", "i", "u", "s", "del", "ins",
    "blockquote", "pre", "code",
    "img", "table", "thead", "tbody", "tr", "th", "td",
}
# NB: 'rel' NIET vermelden op <a> — nh3 beheert dat zelf via link_rel en voegt
# standaard rel="noopener noreferrer" toe (het expliciet toelaten geeft een
# ValueError).
_ALLOWED_ATTRS = {
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "title", "width", "height"},
    "*": {"class"},
}


# An image saved by the WYSIWYG editor always sits inside a Trix `figure` (#1173),
# and its `alt` is not on the <img>. That is measured, not assumed: Trix' own parser
# turns EVERY <img> into an attachment — `case "img": e = {url:
# t.getAttribute("src"), contentType: "image"}` in trix.min.js — keeping only src,
# width and height. An `alt` passed to `insertHTML` is therefore gone before
# anything is saved.
#
# What Trix does keep is the JSON in `data-trix-attachment`: custom keys survive
# every round trip through the editor (measured in a headless Chromium — loaded and
# re-serialised twice, with an edit in between). So the insert button puts the alt
# in that JSON, and this function lifts it onto the <img> itself.
#
# Why here and not when saving: if the page stored a bare `<img alt="…">`, the
# editor would drop that alt the next time it opens the page — and it would then
# vanish silently on the second save. Keeping the figure in the stored document is
# what makes the alt stable.
#
# The figure itself disappears in `sanitize_cms_html`: it is not in the allowlist,
# and nh3 removes such a tag while keeping its children — so the <img> stays. Only
# the alt had to be moved onto it.
_TRIX_IMAGE = re.compile(
    r'(?P<figure><figure\b[^>]*\bdata-trix-attachment="(?P<json>[^"]*)"[^>]*>)'
    # Everything up to this figure's first <img>, and never past its end — so a
    # figure without an <img> cannot swallow the next one.
    r'(?P<between>(?:(?!<img\b|</figure>).)*)'
    r'<img\b(?P<attrs>[^>]*?)\s*/?>',
    re.DOTALL | re.IGNORECASE,
)
_HAS_ALT = re.compile(r'\balt\s*=', re.IGNORECASE)


def _alt_onto_image(match: "re.Match") -> str:
    """One Trix figure: put the alt from its JSON on the <img> below it."""
    attrs = match.group("attrs")
    try:
        data = json.loads(unescape(match.group("json")))
    except (ValueError, TypeError):
        return match.group(0)
    if not isinstance(data, dict):
        return match.group(0)
    # Image attachments only. A file attachment (a PDF) is not an <img> and must not
    # become one; those are left exactly as they were before this issue.
    if not str(data.get("contentType") or "").lower().startswith("image"):
        return match.group(0)
    alt = data.get("alt")
    # An alt already on the tag wins: somebody typed it in the HTML source panel,
    # and that is a deliberate choice.
    if not isinstance(alt, str) or not alt.strip() or _HAS_ALT.search(attrs):
        return match.group(0)
    return (f"{match.group('figure')}{match.group('between')}"
            f'<img{attrs} alt="{escape(alt.strip(), quote=True)}">')


def image_alt_from_attachment(html: Optional[str]) -> Optional[str]:
    """Lift each Trix image attachment's alt onto the <img> itself (#1173).

    Runs before sanitisation, which throws away the figure holding the JSON.
    """
    if not html or "data-trix-attachment" not in html:
        return html
    return _TRIX_IMAGE.sub(_alt_onto_image, html)


def sanitize_cms_html(html: Optional[str]) -> Optional[str]:
    """Ontsmet admin-geschreven CMS-HTML vóór weergave (stored-XSS-guard, #476)."""
    if not html:
        return html
    return nh3.clean(html, tags=_ALLOWED_TAGS, attributes=_ALLOWED_ATTRS)


# Lijst met beschikbare codes — ook gebruikt om een legende in de editor te tonen.
PLACEHOLDER_LABELS = {
    "membership_price_full": "Lidgeld volledig (bv. 35,00)",
    "membership_price_half": "Lidgeld halftarief (bv. 17,50)",
    "half_price_start": "Startdatum halftarief (bv. 16 april)",
    "half_price_end": "Einddatum halftarief (bv. 16 september)",
    "next_year_from": "Vanaf deze datum lid voor volgend jaar (bv. 17 september)",
}

_MAANDEN = ["", "januari", "februari", "maart", "april", "mei", "juni",
            "juli", "augustus", "september", "oktober", "november", "december"]


def _format_price(value) -> str:
    """Belgische notatie: euroteken, punt → komma, twee decimalen.

    Het symbool hoort hier en niet in de CMS-tekst: de placeholder levert een
    volledig bedrag, zodat een redacteur "€" niet hoeft te typen (en niet kan
    vergeten). Zie #579 — zonder symbool las de publieke tekst "bedraagt 35,00".
    """
    return f"€{value:.2f}".replace(".", ",")


def _format_md(md: str) -> str:
    """"MM-DD" → "16 april"."""
    month, day = md.split("-")
    return f"{int(day)} {_MAANDEN[int(month)]}"


def _values() -> Dict[str, str]:
    from app.kernel.tenant_config import tenant_membership_config

    conf = tenant_membership_config()
    return {
        "membership_price_full": _format_price(conf["price_full"]),
        "membership_price_half": _format_price(conf["price_half"]),
        "half_price_start": _format_md(conf["half_start_md"]),
        "half_price_end": _format_md(conf["half_end_md"]),
        "next_year_from": _format_md(conf["next_year_from_md"]),
    }


def render_cms_content(content: Optional[str]) -> Optional[str]:
    """Vervang elke ``{{code}}`` door de bijbehorende configuratiewaarde en
    sanitize het resultaat (#476) — dé functie op elk publiek CMS-renderpunt."""
    if not content:
        return content
    for code, value in _values().items():
        content = content.replace(f"{{{{{code}}}}}", value)
    # Before sanitisation (#1173): that step removes the figure holding the alt.
    return sanitize_cms_html(image_alt_from_attachment(content))
