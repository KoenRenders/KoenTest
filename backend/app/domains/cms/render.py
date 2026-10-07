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
    "p",
    "br",
    "hr",
    "span",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "ul",
    "ol",
    "li",
    # `del` en `ins` horen bij "wat de WYSIWYG-editor produceert": Trix schrijft
    # doorstreepte tekst als <del>. Stond er niet in, dus doorstrepen werkte in de
    # editor en was na het opslaan spoorloos — in het CMS net zo goed als in de
    # vergadernotities (#939, gemeten).
    "a",
    "strong",
    "b",
    "em",
    "i",
    "u",
    "s",
    "del",
    "ins",
    "blockquote",
    "pre",
    "code",
    "img",
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
}
# NB: 'rel' NIET vermelden op <a> — nh3 beheert dat zelf via link_rel en voegt
# standaard rel="noopener noreferrer" toe (het expliciet toelaten geeft een
# ValueError).
_ALLOWED_ATTRS = {
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "title", "width", "height"},
    # An ordered list's start is the author's own (Koen, 7 October 2026,
    # option 1 of the third look, #1699): the renderer writes her on the
    # <ol>, so the sanitiser must let her through — one attribute, one
    # element, nothing else.
    "ol": {"start"},
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
    r"(?P<between>(?:(?!<img\b|</figure>).)*)"
    r"<img\b(?P<attrs>[^>]*?)\s*/?>",
    re.DOTALL | re.IGNORECASE,
)
_HAS_ALT = re.compile(r"\balt\s*=", re.IGNORECASE)
_HAS_CLASS = re.compile(r"\bclass\s*=", re.IGNORECASE)

# The three sizes a page image can have (#1207). Koen asked for fixed sizes and
# not a free percentage: with a free number you end up with 37 %, 40 % and 45 %
# side by side on different pages, looking untidy without anyone seeing why.
#
# A WHITELIST and not a pass-through, and that is the security half: the value
# comes out of admin-written JSON and lands in a `class` attribute, which the
# allowlist in `_ALLOWED_ATTRS` permits on every tag. Mapping through this dict
# means an unknown value yields no class at all instead of whatever was typed.
#
# "vol" carries no class on purpose: that is the behaviour of every image from
# before this issue, so an existing page renders exactly as it did.
IMAGE_SIZES = {"klein": "cms-beeld-klein", "half": "cms-beeld-half", "vol": ""}


def _attributes_onto_image(match: "re.Match") -> str:
    """One Trix figure: put what its JSON carries onto the <img> below it.

    Was `_alt_onto_image` until #1207 added the size. Same mechanism, same
    reason: the editor keeps custom keys in the attachment JSON and drops
    anything written on the `<img>` itself.
    """
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
    extra = []
    # An alt already on the tag wins: somebody typed it in the HTML source panel,
    # and that is a deliberate choice. Same for a class.
    alt = data.get("alt")
    if isinstance(alt, str) and alt.strip() and not _HAS_ALT.search(attrs):
        extra.append(f'alt="{escape(alt.strip(), quote=True)}"')
    # #1207: the size travels in the same JSON as the alt, for the same measured
    # reason — see the block above `_TRIX_IMAGE`.
    klasse = IMAGE_SIZES.get(str(data.get("size") or "").strip())
    if klasse and not _HAS_CLASS.search(attrs):
        extra.append(f'class="{klasse}"')
    if not extra:
        return match.group(0)
    return f"{match.group('figure')}{match.group('between')}<img{attrs} {' '.join(extra)}>"


def image_attributes_from_attachment(html: Optional[str]) -> Optional[str]:
    """Lift a Trix image attachment's alt and size onto the <img> (#1173, #1207).

    Runs before sanitisation, which throws away the figure holding the JSON.
    Renamed from `image_alt_from_attachment` when the size joined the alt: a name
    that says only "alt" would be a lie about what it does.
    """
    if not html or "data-trix-attachment" not in html:
        return html
    return _TRIX_IMAGE.sub(_attributes_onto_image, html)


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
    # #1543: a list, not a value — see `_sites_html`. The second takes an account's
    # code after the colon; the colon is the only parameter form there is.
    "tenants": "De accounts met hun sites, met links (zonder account: onder Overige)",
    "tenants:raak": "De sites van één account; vervang raak door de code van het account",
    # #1567: a button to one of this tenant's forms, by its slug; the label after
    # the bar is optional (without it, the form's title).
    "form:berichten": "Een knop naar een formulier; vervang berichten door de slug van het formulier",
    # #1615: "het verticale streepje (|)" — "streepje" alone reads as a hyphen.
    "form:berichten|Contacteer ons": "Dezelfde knop met een eigen tekst na het verticale streepje (|)",
}

_MAANDEN = [
    "",
    "januari",
    "februari",
    "maart",
    "april",
    "mei",
    "juni",
    "juli",
    "augustus",
    "september",
    "oktober",
    "november",
    "december",
]


def _format_price(value) -> str:
    """Belgische notatie: euroteken, punt → komma, twee decimalen.

    Het symbool hoort hier en niet in de CMS-tekst: de placeholder levert een
    volledig bedrag, zodat een redacteur "€" niet hoeft te typen (en niet kan
    vergeten). Zie #579 — zonder symbool las de publieke tekst "bedraagt 35,00".
    """
    return f"€{value:.2f}".replace(".", ",")


def _format_md(md: str) -> str:
    """ "MM-DD" → "16 april"."""
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


#: `{{tenants}}` and `{{tenants:<account code>}}` (#1543). The colon is the one
#: parameter form the placeholders have; measured before it was added, they had
#: none — `{{code}}` was a plain replacement from a fixed dict.
_SITES = re.compile(r"\{\{tenants(?::([a-z0-9-]+))?\}\}")


def sites_in_words(account_code: Optional[str], db=None) -> str:
    """The same accounts and sites as `_sites_html`, in words (#1615): what the
    editor's legend shows as the example of `{{tenants}}` and `{{tenants:<code>}}`
    — "Account A: Site 1, Site 2 · Overige: Site 3", or one account's site names.
    The legend shows words, never the cards' markup."""
    parts = []
    for group in _site_groups(account_code, db):
        names = ", ".join(site["name"] for site in group["sites"])
        parts.append(f"{group['heading']}: {names}" if group["heading"] else names)
    return " · ".join(part for part in parts if part)


def _sites_html(account_code: Optional[str], db=None) -> str:
    """The accounts with their active sites, each site a card (#1543, #1566).

    Without a code: every active account with a heading, and "Overige" last for
    the tenants without one, as the landing of #1525 listed them. With a code:
    that account's sites only, without a heading; an unknown or inactive code
    renders nothing. The platform appears under its account when it has one
    (#1542). The HTML comes from `_tenant_sites.html` (the card is the kit's
    `site_card`), where Jinja escapes names and addresses; it is placed AFTER
    the sanitiser: it is built in code, not typed by an author, and it carries
    `hx-boost="false"`, which an author may not. A card goes to another site;
    boosted, the site shell would swap only `#main` and keep this site's header
    around the other's page (measured in the e2e, #1543).

    `db` is the request's session where the caller has one — the public screens
    pass it — so the list costs no connection of its own and sees what the
    request sees. Without it (the editor's legend, the JSON API, the assistant's
    context) a short session of its own.
    """
    from app.ui import templates

    groups = _site_groups(account_code, db)
    if not groups:
        return ""
    return templates.env.get_template("_tenant_sites.html").render(groups=groups).strip()


def _site_groups(account_code: Optional[str], db=None) -> list[dict]:
    """What the sites placeholder lists, as data: per account its heading (None
    for one account asked by code) and its sites by name and address. One reader
    for the cards (`_sites_html`) and for the legend's words (`sites_in_words`)."""
    from app.database import SessionLocal
    from app.domains.mdm.api import OrganizationType, active_sites_by_account
    from app.i18n import _
    from app.kernel.tenant_config import platform_home_url, tenant_display_name, tenant_home_url

    own = db is None
    if own:
        db = SessionLocal()
    try:
        groups = []
        for account, sites in active_sites_by_account(db):
            if account_code is not None and (account is None or account.code != account_code):
                continue
            links = sorted(
                (
                    tenant_display_name(db, tenant_id=s.id),
                    platform_home_url(db, s.id)
                    if s.org_type is OrganizationType.PLATFORM
                    else tenant_home_url(db, tenant_id=s.id, code=s.code),
                )
                for s in sites
            )
            heading = None if account_code else (account.name if account else _("Overige"))
            groups.append(
                {"heading": heading, "sites": [{"name": name, "url": url} for name, url in links]}
            )
        return groups
    finally:
        if own:
            db.close()


#: `{{form:<slug>}}` and `{{form:<slug>|<button label>}}` (#1567), in the
#: family of `{{tenants}}`: a parameter after the colon, built after the
#: sanitiser. The label runs to the closing braces and holds none itself.
_FORM = re.compile(r"\{\{form:([a-z0-9]+(?:[-_][a-z0-9]+)*)(?:\|([^{}]*))?\}\}")


def _form_button_html(slug: str, label: Optional[str], db=None) -> str:
    """A button to this tenant's form `slug`, or nothing (#1567).

    Nothing — never the raw code and never a button that leads nowhere — when
    the form does not exist in this tenant, is not open, or (the contact form)
    cannot take a message: `forms.api.form_button_target` decides. Without a
    label the button carries the form's title.

    The button is the kit's (`ui.btn_secondary`), so it looks like the one on
    the association's home. The label is text: what an author typed arrives
    here already through the sanitiser, with its entities; it is unescaped once
    and the macro escapes it again, so markup in a label shows as typed and is
    never executed. The address gets the tenant's prefix (`path_for`).
    """
    from app.database import SessionLocal
    from app.domains.forms.api import form_button_target
    from app.ui import path_for, templates

    own = db is None
    if own:
        db = SessionLocal()
    try:
        target = form_button_target(db, slug)
    finally:
        if own:
            db.close()
    if target is None:
        return ""
    title, path = target
    text = unescape(label).strip() if label and label.strip() else title
    # The macro module's attributes are the macros; mypy knows only the class.
    button = getattr(templates.env.get_template("_macros.html").module, "btn_secondary")
    return (
        # A span, not a block: an author types the code inside a paragraph.
        f'<span data-form-button="{escape(slug)}" class="inline-block">'
        f"{button(text, href=path_for(path))}</span>"
    )


_HEADING = re.compile(r"<(/?)h([1-3])(?=[\s>/])", re.IGNORECASE)


def headings_one_level_down(html: str) -> str:
    """Every heading of a page body shown one level down (#1656, CR-11 Q87):
    `<h1>` as `<h2>`, `<h2>` as `<h3>`, `<h3>` as `<h4>`. On a public page the
    page's title is the only h1, and the three levels the editor offers (Kop,
    Subkop, Kleine kop) stay three levels under it.

    Only the tag's name changes — its attributes and what stands in it stay.
    In ONE pass, so an h1 does not become an h3. For SANITISED html, and for
    showing only: the stored text is never touched, so rendering it again
    shifts from the source again, not from its own output."""
    return _HEADING.sub(lambda m: f"<{m.group(1)}h{int(m.group(2)) + 1}", html)


def render_cms_content(content: Optional[str], db=None, *, on_page: bool = False) -> Optional[str]:
    """Vervang elke ``{{code}}`` door de bijbehorende configuratiewaarde en
    sanitize het resultaat (#476) — dé functie op elk publiek CMS-renderpunt.
    `db` (#1543): the request's session, for the sites placeholder.

    `on_page` (#1656): the content is the body of a public page, under that
    page's own title — its headings are shown one level down
    (`headings_one_level_down`). The one place where that happens; the home
    intro, a card's text and the JSON answer are not a page body and keep
    their headings."""
    if not content:
        return content
    for code, value in _values().items():
        content = content.replace(f"{{{{{code}}}}}", value)
    # Before sanitisation (#1173): that step removes the figure holding the alt.
    content = sanitize_cms_html(image_attributes_from_attachment(content)) or ""
    if on_page:
        # After the sanitiser, before the blocks built in code (their headings
        # are their own).
        content = headings_one_level_down(content)
    # After it (#1543): the site cards are built and escaped in code — see `_sites_html`.
    content = _SITES.sub(lambda m: _sites_html(m.group(1), db), content)
    # And the form buttons (#1567), the same way.
    return _FORM.sub(lambda m: _form_button_html(m.group(1), m.group(2), db), content)


# ── Documents (CR-17 phase 1, #1671) ─────────────────────────────────────────
#
# A page's content is a structured document against `cms/schema.py`; the HTML
# below is a RENDERING of it, never the storage. The pipeline mirrors the old
# one on purpose — the same sanitiser over the output, the same substitutions
# after it — so a migrated page renders byte-for-byte as it did (R17, test 12):
# the round trip `render_document(parse_html(page.content)) == the old public
# output` is the migration's proof of losslessness.
#
# No legacy flags (Koen, 6 October 2026): a page whose paragraphs are Trix
# divs, or whose picture carries a Trix-era size, keeps her HTML — her words
# stand in the draft. A figure placed through the editor renders as the kit's
# picture with the public radius and shadow (C4.8). The document never decides
# pixels — the prose rules do.


def _mark_html(mark: dict) -> tuple[str, str]:
    """The open and close tag of one mark. `del` and not `s`: the stored pages
    carry Trix' spelling, so the round trip holds; `em`/`strong` for the same
    reason."""
    if mark["type"] == "link":
        href = escape(mark.get("attrs", {}).get("href", ""), quote=True)
        return f'<a href="{href}">', "</a>"
    tag = {"bold": "strong", "italic": "em", "strike": "del"}[mark["type"]]
    return f"<{tag}>", f"</{tag}>"


def _inline_html(nodes: "list[dict] | None") -> str:
    """Inline content: text, marks, hard breaks and value nodes.

    A paragraph inside a table cell renders without its `<p>` (cell context,
    the shape tables have always had); everywhere else a paragraph keeps it.
    """
    parts = []
    for node in nodes or []:
        kind = node["type"]
        if kind == "text":
            text = escape(node.get("text", ""), quote=False)
            for mark in node.get("marks") or []:
                open_tag, close_tag = _mark_html(mark)
                text = f"{open_tag}{text}{close_tag}"
            parts.append(text)
        elif kind == "hardBreak":
            parts.append("<br>")
        elif kind == "value":
            code = node.get("attrs", {}).get("code", "")
            parts.append(escape(_values().get(code, ""), quote=False))
        else:
            raise ValueError(f"unknown inline node: {kind}")
    return "".join(parts)


def _blocks_html(blocks: "list[dict] | None", cell: bool = False) -> str:
    parts = []
    for node in blocks or []:
        parts.append(_block_html(node, cell))
    return "".join(parts)


def _block_html(node: dict, cell: bool = False) -> str:
    kind = node["type"]
    content = node.get("content")

    if kind == "paragraph":
        inner = _inline_html(content)
        return inner if cell else f"<p>{inner}</p>"

    if kind == "heading":
        # The document stores the author's choice; `render_document` shifts a
        # page body one level down through `headings_one_level_down` — the
        # ONE place that knows the shift (#1656, review B4a #1673).
        level = int(node.get("attrs", {}).get("level", 2))
        return f"<h{level}>{_inline_html(content)}</h{level}>"

    if kind in ("bulletList", "orderedList"):
        tag = "ul" if kind == "bulletList" else "ol"
        # A list item's paragraphs render bare, like today's Trix lists: no
        # <p> inside the <li> (measured: with it, every round trip failed).
        items = "".join(
            f"<li>{_blocks_html(item.get('content'), cell=True)}</li>" for item in content or []
        )
        # An ordered list's start is the author's own (Koen, 7 October 2026:
        # render her — option 1 of the third look, #1699). Only a start that
        # differs from the default lands on the <ol>: TipTap writes start=1
        # for every list she makes, and a start="1" would change the HTML
        # of pages that never asked for one.
        start = ""
        if kind == "orderedList":
            value = (node.get("attrs") or {}).get("start")
            if isinstance(value, int) and value != 1:
                start = f' start="{value}"'
        return f"<{tag}{start}>{items}</{tag}>"

    if kind == "table":
        # The rows carry their section: a table typed WITH <thead> renders
        # thead + tbody, a bare table renders bare rows — both exactly as
        # the sanitised HTML of today does (#1671).
        head = "".join(
            _block_html(row)
            for row in content or []
            if (row.get("attrs") or {}).get("section") == "head"
        )
        body = "".join(
            _block_html(row)
            for row in content or []
            if (row.get("attrs") or {}).get("section") == "body"
        )
        bare = "".join(
            _block_html(row) for row in content or [] if not (row.get("attrs") or {}).get("section")
        )
        return (
            "<table>"
            + (f"<thead>{head}</thead>" if head else "")
            + (f"<tbody>{body}</tbody>" if body else "")
            + bare
            + "</table>"
        )

    if kind == "tableRow":
        return f"<tr>{''.join(_block_html(c) for c in content or [])}</tr>"

    if kind in ("tableHeader", "tableCell"):
        tag = "th" if kind == "tableHeader" else "td"
        return f"<{tag}>{_blocks_html(content, cell=True)}</{tag}>"

    if kind == "figure":
        return _figure_html(node)

    raise ValueError(f"unknown block node: {kind}")


def _figure_html(node: dict) -> str:
    # The address comes from media.api — the one place that knows its shape
    # (CR-15 §C4.6); no module writes it itself (the media seam gate).
    from app.domains.media.api import media_url

    attrs = node.get("attrs", {})
    media_id = attrs.get("media_id")
    src = media_url(media_id)
    # The kit's figure — the only rendering: radius and shadow come from the
    # prose rules, never from the file (C4.8). A Trix-era picture keeps her
    # page on the HTML fallback (no legacy sizes, Koen 6 October 2026); a
    # figure placed through the editor lands here. NOTE (review E, #1673): the
    # sanitiser over the output still drops the <figure> wrapper until slice 4
    # allows it — slice 2's editor is the first to place one.
    placement = attrs.get("placement") or "full"
    alt = escape(attrs.get("alt") or "", quote=True)
    size = ""
    if attrs.get("width") and attrs.get("height"):
        size = f' width="{attrs["width"]}" height="{attrs["height"]}"'
    figure = (
        f'<figure class="prose-figure prose-figure--{placement}">'
        f'<img src="{src}" alt="{alt}"{size} loading="lazy">'
    )
    if attrs.get("caption"):
        figure += f"<figcaption>{escape(attrs['caption'])}</figcaption>"
    return figure + "</figure>"


def render_document(document, db=None, *, on_page: bool = False, target: str = "site") -> str:
    """A validated document (dict or JSON string) to site HTML (CR-17, C4.2) —
    or to plain text (``target="text"``): the words the chatbot's context
    reads, no tags at all.

    The same net as the old path, in the same order: build the HTML from the
    schema's nodes, sanitise the OUTPUT (nh3, the same allowlist), then the
    substitutions the text may carry — the five configuration codes first
    (a code stays TEXT in the document; the renderer replaces it as
    `render_cms_content` does today, the value BLOCK is phase 5), then the
    sites cards and a form button — code built and escaped, placed after the
    sanitiser as before (#1543, #1567). The text target walks the same schema
    and carries the same substitutions, reduced to their words.
    """
    if isinstance(document, str):
        import json

        document = json.loads(document)
    if target == "text":
        return _document_text(document, db)
    html = _blocks_html(document.get("content") or []) if document else ""
    html = sanitize_cms_html(html) or ""
    if on_page:
        html = headings_one_level_down(html)
    for code, value in _values().items():
        html = html.replace(f"{{{{{code}}}}}", value)
    html = _SITES.sub(lambda m: _sites_html(m.group(1), db), html)
    return _FORM.sub(lambda m: _form_button_html(m.group(1), m.group(2), db), html)


def _document_text(document, db=None) -> str:
    """The words of a document: what the chatbot's context reads (C2 cms,
    *Readers*). Blocks in order, blank lines between them; a value block its
    current value; a figure its alt text; the sites cards and a form button
    their words, not their markup."""

    if not document:
        return ""
    lines: list[str] = []

    def walk(node: dict) -> None:
        kind = node["type"]
        content = node.get("content") or []
        if kind == "doc":
            for child in content:
                walk(child)
            return
        if kind == "paragraph":
            lines.append(_inline_text(content))
        elif kind == "heading":
            lines.append(_inline_text(content))
        elif kind in ("bulletList", "orderedList"):
            # An ordered list numbers from her start (option 1, #1699): the
            # chatbot reads what the author wrote — "5." stays "5.", not a
            # bare dash that could be any list.
            number = (node.get("attrs") or {}).get("start") if kind == "orderedList" else None
            for item in content:
                words = " ".join(
                    _inline_text(b.get("content") or []) for b in item.get("content") or []
                )
                if number is None:
                    lines.append(f"- {words}")
                else:
                    lines.append(f"{number}. {words}")
                    number += 1
        elif kind == "table":
            for row in content:
                cells = [
                    " ".join(
                        _inline_text(p.get("content") or []) for p in cell.get("content") or []
                    )
                    for cell in row.get("content") or []
                ]
                lines.append(" | ".join(cells))
        elif kind == "figure":
            alt = (node.get("attrs") or {}).get("alt") or ""
            if alt:
                lines.append(alt)
        elif kind in ("button", "callout", "linkCard", "card", "cards"):
            attrs = node.get("attrs") or {}
            words = " ".join(
                str(attrs.get(k, "")) for k in ("heading", "label", "title", "line") if attrs.get(k)
            )
            if words:
                lines.append(words)

    def _inline_text(nodes: list) -> str:
        words = []
        for node in nodes:
            kind = node["type"]
            if kind == "text":
                words.append(unescape(node.get("text", "")))
        text = " ".join(words)
        for code, value in _values().items():
            text = text.replace(f"{{{{{code}}}}}", value)
        return text.strip()

    walk(document)
    text = "\n\n".join(line for line in lines if line.strip())
    # The same substitutions the site carries, as their words (#1615's rule:
    # a placeholder is shown in WORDS, never its markup).
    text = _SITES.sub(lambda m: sites_in_words(m.group(1), db), text)
    return _FORM.sub(lambda m: unescape(m.group(2) or "").strip() or m.group(1), text)
