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
from collections.abc import Callable, Mapping
from contextvars import ContextVar
from html import escape, unescape
from typing import Dict, Optional

import nh3

from app.i18n import _
from app.kernel.clock import belgian_today

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
    # The figure of a published document (CR-17 #1671, slice 3): the wrapper
    # carries the placement (`prose-figure--…`) and the caption her words —
    # without her in the allowlist a published figure loses both, exactly
    # what slice 1's review E note warned about (#1673). Slice 3 is the
    # moment she first reaches the site: the page screen publishes
    # documents. A Trix-era figure wrapper also survives now; her `img`
    # keeps her own size class and the wrapper matches no style — measured
    # in test_figure_placements_1671.py's sibling, the legacy pin below.
    "figure",
    "figcaption",
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
    # element, nothing else. The same holds for a merged cell's spans
    # (8 October 2026): what the author merged, the site shows.
    "ol": {"start"},
    "th": {"colspan", "rowspan"},
    "td": {"colspan", "rowspan"},
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
    "membership_valid_until": "Het jaar waarin een nieuw lidmaatschap eindigt (bv. 2027)",
    # #1543: a list, not a value — see `_sites_html`. The second takes an account's
    # code after the colon; the colon is the only parameter form there is.
    "tenants": "De accounts met hun sites, met links",
    "tenants:raakmillegem": (
        "De sites van het account van één site; vervang raakmillegem door de code van die site"
    ),
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
    from app.domains.payment.api import membership_valid_period
    from app.kernel.tenant_config import tenant_membership_config

    conf = tenant_membership_config()
    return {
        "membership_price_full": _format_price(conf["price_full"]),
        "membership_price_half": _format_price(conf["price_half"]),
        "half_price_start": _format_md(conf["half_start_md"]),
        "half_price_end": _format_md(conf["half_end_md"]),
        "next_year_from": _format_md(conf["next_year_from_md"]),
        "membership_valid_until": str(membership_valid_period()[1].year),
    }


#: `{{tenants}}` and `{{tenants:<tenant code>}}` (#1543). The colon is the one
#: parameter form the placeholders have; measured before it was added, they had
#: none — `{{code}}` was a plain replacement from a fixed dict. Since CR-20 (F10)
#: the parameter names a tenant and lists the sites of that tenant's account: an
#: account is a party and has no code; the migration rewrote the stored
#: `{{tenants:<account code>}}` once.
_SITES = re.compile(r"\{\{tenants(?::([a-z0-9-]+))?\}\}")


def sites_in_words(tenant_code: Optional[str], db=None) -> str:
    """The same accounts and sites as `_sites_html`, in words (#1615): what the
    editor's legend shows as the example of `{{tenants}}` and `{{tenants:<code>}}`
    — "Account A: Site 1, Site 2 · Overige: Site 3", or the site names of one
    tenant's account. The legend shows words, never the cards' markup."""
    parts = []
    for group in _site_groups(tenant_code, db):
        names = ", ".join(site["name"] for site in group["sites"])
        parts.append(f"{group['heading']}: {names}" if group["heading"] else names)
    return " · ".join(part for part in parts if part)


def _sites_html(tenant_code: Optional[str], db=None) -> str:
    """The accounts with their active sites, each site a card (#1543, #1566).

    Without a code: every active account with a heading, and "Overige" last for
    the tenants whose account is inactive, as the landing of #1525 listed them.
    With a tenant's code: the sites of that tenant's account only, without a
    heading; an unknown code renders nothing. The platform appears under its account when it has one
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

    groups = _site_groups(tenant_code, db)
    if not groups:
        return ""
    return templates.env.get_template("_tenant_sites.html").render(groups=groups).strip()


def _site_groups(tenant_code: Optional[str], db=None) -> list[dict]:
    """What the sites placeholder lists, as data: per account its heading (None
    for the one account asked by a tenant's code) and its sites by name and
    address. One reader for the cards (`_sites_html`) and for the legend's words
    (`sites_in_words`)."""
    from app.database import SessionLocal
    from app.domains.mdm.api import active_sites_by_account, tenant_by_code
    from app.i18n import _
    from app.kernel.tenant_config import platform_home_url, tenant_display_name, tenant_home_url

    own = db is None
    if own:
        db = SessionLocal()
    try:
        groups = []
        asked = tenant_by_code(db, tenant_code) if tenant_code is not None else None
        if tenant_code is not None and asked is None:
            return []
        for account, sites in active_sites_by_account(db):
            if asked is not None and (account is None or account.id != asked.account_id):
                continue
            links = sorted(
                (
                    tenant_display_name(db, tenant_id=s.id),
                    platform_home_url(db, s.id)
                    if s.is_platform
                    else tenant_home_url(db, tenant_id=s.id, code=s.code),
                )
                for s in sites
            )
            heading = None if tenant_code else (account.name if account else _("Overige"))
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


#: The one class the mark "Groot" writes, and the one span the parser reads back.
LARGE_CLASS = "prose-large"


def _mark_html(mark: dict) -> tuple[str, str]:
    """The open and close tag of one mark. `del` and not `s`: the stored pages
    carry Trix' spelling, so the round trip holds; `em`/`strong` for the same
    reason."""
    if mark["type"] == "link":
        href = escape(mark.get("attrs", {}).get("href", ""), quote=True)
        return f'<a href="{href}">', "</a>"
    if mark["type"] == "large":
        # A span with one class, never a heading: the page keeps its one `h1`
        # (#1656) and the size is the prose rules' (#2095).
        return f'<span class="{LARGE_CLASS}">', "</span>"
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
            if code == "tenants":
                # The one value that renders a list: the placeholder stays text
                # here and `_SITES` replaces it after the sanitiser, as for a
                # typed `{{tenants}}` (the cards are built in code, #1543).
                parts.append("{{tenants}}")
            else:
                value_html = escape(_values().get(code, ""), quote=False)
                for mark in node.get("marks") or []:
                    open_tag, close_tag = _mark_html(mark)
                    value_html = f"{open_tag}{value_html}{close_tag}"
                parts.append(value_html)
        else:
            raise ValueError(f"unknown inline node: {kind}")
    return "".join(parts)


def _blocks_html(
    blocks: "list[dict] | None",
    cell: bool = False,
    preview: bool = False,
    db=None,
    late: "list[str] | None" = None,
) -> str:
    parts = []
    for node in blocks or []:
        parts.append(_block_html(node, cell, preview, db, late))
    # A cell or a list item holds bare paragraphs (no <p>); Enter in a cell
    # is the author's own line break — blocks joined with nothing ran her
    # lines together on the site (review B1, #1770). Outside a cell the
    # blocks carry their own margins; nothing joins them. A nested list starts
    # on its own line: no break before it (#2038 review A2: it showed as an empty
    # line before every sub-list).
    if not cell:
        return "".join(parts)
    joined = ""
    for index, (node, part) in enumerate(zip(blocks or [], parts, strict=True)):
        if index and node["type"] not in ("bulletList", "orderedList"):
            joined += "<br>"
        joined += part
    return joined


def _block_html(
    node: dict,
    cell: bool = False,
    preview: bool = False,
    db=None,
    late: "list[str] | None" = None,
) -> str:
    kind = node["type"]
    content = node.get("content")

    # A caller that renders for another place than the site (the letter, as a
    # mail) builds some blocks itself (`render_document(blocks=...)`): they are
    # built whole in code, so they stand after the sanitiser like the cards.
    builders = _BLOCKS.get()
    if builders is not None and kind in builders:
        block = builders[kind](node)
        if not block or late is None:
            return block
        late.append(block)
        return f"<div>{_LATE}{len(late) - 1}{_LATE}</div>"

    if kind in LETTER_BLOCKS:
        # The letter's own blocks (CR-17 phase 7): a page shows nothing of them.
        return ""

    if kind == "paragraph":
        inner = _inline_html(content)
        return inner if cell else f"<p>{inner}</p>"

    if kind == "heading":
        # The document stores the level it shows (CR-32 R21): no shift here.
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
        # A merged cell is the author's own (Koen, 8 October 2026): the
        # spans she merged show on the site as she made them. Only a real
        # span lands on the tag — the editor's 1s stay invisible, so an
        # ordinary table keeps today's HTML.
        attrs = node.get("attrs") or {}
        spans = ""
        for name in ("colspan", "rowspan"):
            value = attrs.get(name)
            if isinstance(value, int) and value > 1:
                spans += f' {name}="{value}"'
        return f"<{tag}{spans}>{_blocks_html(content, cell=True)}</{tag}>"

    if kind == "figure":
        return _figure_html(node)

    if kind in ("columns", "column"):
        # C4.6/C4.13: two sub-documents of equal width, 32 px between; the
        # alignment is the stored `align` (the editor adapter derives her,
        # #1679's design review B4) written as a class — the sanitiser
        # allows no data attributes, and the class is the look's own
        # vocabulary. A column renders her children bare: the wrapper
        # carries the grid, the columns the blocks.
        if kind == "columns":
            align = (node.get("attrs") or {}).get("align") or "top"
            cls = "prose-columns"
            if align == "middle":
                cls += " prose-columns--middle"
            ratio = (node.get("attrs") or {}).get("ratio")
            if ratio in ("wide-narrow", "narrow-wide"):
                cls += f" prose-columns--{ratio}"
            inner = _blocks_html(content, preview=preview, db=db, late=late)
            return f'<div class="{cls}">{inner}</div>'
        inner = _blocks_html(content, preview=preview, db=db, late=late)
        return f'<div class="prose-column">{inner}</div>'

    if kind == "button":
        return _button_html(node, preview=preview, db=db)

    if kind == "gallery":
        return _gallery_html(node, preview=preview, db=db)

    if kind == "section":
        # CR-32 F1–F3: a band of the page. A div, because the sanitiser's
        # allow-list has no `section` and a security allow-list does not grow
        # for a tag name; the tone is a class (a name, never a colour), the
        # plain tone carries none. The kit breaks the band out of the page's
        # container and puts the container back inside it (`build-css.sh`).
        attrs = node.get("attrs") or {}
        tone = attrs.get("tone")
        cls = "prose-section" + (f" prose-section--{tone}" if tone and tone != "plain" else "")
        eyebrow = attrs.get("eyebrow")
        top = f'<p class="prose-section-eyebrow">{escape(eyebrow)}</p>' if eyebrow else ""
        inner = _blocks_html(content, preview=preview, db=db, late=late)
        return f'<div class="{cls}">{top}{inner}</div>'

    if kind == "blockquote":
        # A quotation (#1985) holds blocks; her paragraphs render bare and a
        # line break joins them, as the Trix editor wrote her
        # (`<blockquote>Regel een<br>Regel twee</blockquote>`) — so a Trix
        # page whose quotation is her only difference converts, and the site's
        # prose rule for `blockquote` styles her. An empty one renders nothing.
        inner = _blocks_html(content, cell=True, preview=preview, db=db, late=late)
        return f"<blockquote>{inner}</blockquote>" if inner.strip() else ""

    if kind == "callout":
        # C4.13: text only, on a neutral surface with the line and radius
        # 14, 16 px inside — no title, icon or colour stripe. Her words are
        # inline content, sanitised with everything else. An empty callout
        # renders NOTHING (review S5 of 12 October 2026): on the site she
        # was an empty box of 34 px.
        words = _inline_html(content)
        if not words.strip():
            return ""
        return f'<div class="prose-callout">{words}</div>'

    if kind == "cards":
        # A card draws an icon — an <svg> the sanitiser would take out — so
        # the block is built whole, every word of the author's escaped, and
        # placed AFTER the sanitiser, as the sites cards and the form button
        # are (#1543, #1567). Here stands only the place it goes to.
        block = _cards_html(node, preview=preview, db=db)
        if not block:
            return ""
        if late is None:
            return block
        late.append(block)
        return f"<div>{_LATE}{len(late) - 1}{_LATE}</div>"

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
    # figure placed through the editor lands here. The sanitiser keeps the
    # wrapper since slice 3 (review E's note on #1673 resolved there): the
    # page screen publishes documents, and without the wrapper the visitor
    # loses the placement and the caption.
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


#: The look of a refused button in the admin preview (review S7 of 12 October
#: 2026): the kit's own notice — the same surface, line and left accent as
#: `ui.save_refusal`, on the span the sentences already carry. One constant,
#: one look: the sentences below say her in plain words.
REFUSED_CLS = (
    "prose-refused inline-block rounded-md border border-red-200 border-l-[3px] "
    "border-l-red-600 bg-red-50 px-3 py-1.5 text-sm text-ink"
)


#: The mark of a block that is placed after the sanitiser. Private-use
#: characters: nothing an author types and nothing the sanitiser changes.
_LATE = "\ue000cards\ue001"

#: Why a destination cannot be reached, in the words the admin preview shows —
#: one sentence per block and reason; on the site such a block shows nothing
#: (A4's one rule).
_UNREACHABLE = {
    ("button", "site-block"): _("Deze knop wijst naar een siteblok dat op geen eigen adres staat."),
    ("button", "page"): _("Deze knop wijst naar een pagina die niet (meer) bestaat."),
    ("button", "form"): _("Deze knop wijst naar een formulier dat geen inzendingen meer aanneemt."),
    # No "vereniging": the tenant that meets this sentence is by nature not
    # always one (review of 12 October 2026).
    ("button", "screen"): _("Deze knop wijst naar een scherm dat hier niet wordt aangeboden."),
    ("card", "site-block"): _("Deze kaart wijst naar een siteblok dat op geen eigen adres staat."),
    ("card", "page"): _("Deze kaart wijst naar een pagina die niet (meer) bestaat."),
    ("card", "form"): _("Deze kaart wijst naar een formulier dat geen inzendingen meer aanneemt."),
    ("card", "screen"): _("Deze kaart wijst naar een scherm dat hier niet wordt aangeboden."),
    ("gallery", "empty"): _(
        "Deze galerij toont niets: het album bestaat niet meer of heeft geen foto's."
    ),
    ("activities", "empty"): _("Dit blok toont niets: er zijn geen komende activiteiten."),
    ("albums", "empty"): _("Deze kaart toont niets: er is nog geen album met foto's."),
}


def _destination(attrs: dict, db) -> "tuple[str | None, str | None, bool]":
    """Where a button or a card leads: `(address, None, outside)` — or
    `(None, reason, False)` when the ONE destination it holds cannot be
    reached (Koen, 11 October 2026: a page of the site, a reference that
    survives a slug change; a form of the tenant; the one application screen
    of this CR, Lid worden; or an outside address, http(s), already refused at
    the save when it is anything else).

    The addresses go through `path_for` (#1477/B7): a tenant reached by her
    path prefix would be sent to the wrong door by a bare one. The form asks
    forms' own door — `form_button_target` decides whether the form exists
    and is open, the same door the `{{form:...}}` code uses.
    """
    from app.domains.forms.api import form_button_target
    from app.ui import path_for

    if attrs.get("page_id") is not None:
        from app.domains.cms.models import CmsPage
        from app.domains.cms.service import serves_at_address

        page = (
            db.query(CmsPage)
            # The tenant's own listener scopes her (the request sets the
            # contextvar; a bare session sees every tenant — how the tests
            # reach the seed).
            .filter(CmsPage.id == attrs["page_id"], CmsPage.is_published.is_(True))
            .first()
        )
        if page is None:
            return None, "page", False
        # The site's own blocks stand at no address of their own (review A2
        # of 12 October 2026): the page list asks the same
        # `serves_at_address`, so what the picker offers is exactly what the
        # resolver resolves.
        if not serves_at_address(page):
            return None, "site-block", False
        return path_for(f"/{page.slug}"), None, False
    if attrs.get("form_slug"):
        resolved = form_button_target(db, attrs["form_slug"])
        if resolved is None:
            return None, "form", False
        return resolved[1], None, False
    if attrs.get("screen"):
        # The one application screen is mounted behind the membership module
        # (main.py): for a tenant without her it is not offered in the dialog
        # and an existing one is unreachable — the same one rule as every
        # unreachable target (review A3 of 12 October 2026).
        from app.domains.mdm.api import module_enabled
        from app.kernel.modules import ModuleCode

        if not module_enabled(ModuleCode.MEMBERSHIP):
            return None, "screen", False
        return path_for("/lid-worden"), None, False
    return attrs.get("href") or "", None, True


def _resolved(attrs: dict, db) -> "tuple[str | None, str | None, bool]":
    """`_destination` with the caller's own session where she has one (the
    request's, the test's): one link is one query, not a session of her own.
    Without a caller she opens one, exactly as the form button does."""
    from app.database import SessionLocal

    if db is not None:
        return _destination(attrs, db)
    own_db = SessionLocal()
    try:
        return _destination(attrs, own_db)
    finally:
        own_db.close()


def _unreachable_html(block: str, reason: str) -> str:
    return f'<span class="{REFUSED_CLS}">{_UNREACHABLE[(block, reason)]}</span>'


#: The signed-in visitor a page is rendered for (CR-32 F14, B8.9): the shell's
#: `gebruiker` — a mapping that says `has_household` — or None (a visitor, the
#: preview, the chatbot, a mail). An input of `render_document`; held in a context
#: variable for the length of one render so the many nested calls need no new
#: parameter, and reset when it ends.
#: The blocks of a letter (CR-17 phase 7): the mail renderer builds them; a page
#: renders them as nothing.
LETTER_BLOCKS: tuple[str, ...] = ("activity", "calendar", "closing")

#: Blocks the CALLER builds (`render_document(blocks=...)`): kind → function of the
#: node, answering the block's HTML. Held for the length of a render, like the viewer.
_BLOCKS: ContextVar["Mapping[str, Callable[[dict], str]] | None"] = ContextVar(
    "cms_render_blocks", default=None
)

_VIEWER: ContextVar["Mapping | None"] = ContextVar("cms_render_viewer", default=None)


def _viewer_has_household() -> bool:
    viewer = _VIEWER.get()
    return bool(viewer and viewer.get("has_household"))


def _button_html(node: dict, preview: bool = False, db=None) -> str:
    """The kit's button with the author's label and her ONE resolved
    destination (#1679). What cannot be reached renders NOTHING on the site —
    never a button that leads nowhere (A4's one rule, the form button's own,
    #1567) — and the reason in the admin preview."""
    attrs = node.get("attrs") or {}
    label = escape(attrs.get("label") or "")
    variant = attrs.get("variant") or "secondary"
    address, reason, outside = _resolved(attrs, db)
    if address is None:
        return _unreachable_html("button", reason or "page") if preview else ""
    if attrs.get("screen") == "lid-worden" and _viewer_has_household():
        # One rule for every button to that screen (B8.9): a signed-in member with
        # a household is sent to the household, with the word for it. No block, no
        # second button — the same rule the home's band had.
        from app.ui import path_for

        address, label = path_for("/leden/gezin"), escape(_("Mijn gezin"))
    rel = ' rel="noopener noreferrer"' if outside else ""
    return (
        f'<a class="prose-button prose-button--{variant}" '
        f'href="{escape(address, quote=True)}"{rel}>{label}</a>'
    )


def button_address(node: dict, db=None) -> "tuple[str | None, bool]":
    """Where a button block leads — the address as the site's button resolves it
    (a path of the site, or an address outside it) — and whether it is outside; none
    when it cannot be reached. For a renderer of another place than the site (the
    letter, as a mail), which builds its own button and needs the one resolver."""
    address, _reason, outside = _resolved(node.get("attrs") or {}, db)
    return address, outside


def hero_view(page, db=None, *, preview: bool = False, viewer=None) -> "dict | None":
    """The hero a page opens with (CR-32 F5), as the template draws it — or
    None when the page opens with its title line. The hero is a property of
    the page, not of its document: the page's title is its h1 and stays the
    template's. The buttons are the button block's own, through the one
    resolver: the first is the primary, the second the secondary, and one
    that cannot be reached is left out on the site (the reason in the preview)."""
    hero = getattr(page, "hero", None)
    if getattr(page, "opening", "title_line") != "hero" or not hero:
        return None
    token = _VIEWER.set(viewer)
    try:
        actions = "".join(
            _button_html(
                {
                    "attrs": {
                        **{k: v for k, v in button.items() if k != "label"},
                        "label": button["label"],
                        "variant": "primary" if index == 0 else "secondary",
                    }
                },
                preview=preview,
                db=db,
            )
            for index, button in enumerate(hero.get("buttons") or [])
        )
    finally:
        _VIEWER.reset(token)
    return {
        "tone": hero["tone"],
        "eyebrow": hero.get("eyebrow") or "",
        "lead": hero.get("lead") or "",
        "actions_html": actions,
    }


def _activities_html(node: dict, preview: bool = False, db=None) -> str:
    """The upcoming activities as the home page showed them, at most `count`
    (CR-32 R15, F14): the activities module's list and its own partial
    (`_activiteiten_cards.html`), rendered through the template environment as the
    sites list is. A tenant without the module, or with nothing to show, gets
    nothing on the site and the reason in the preview."""

    from app.database import SessionLocal
    from app.domains.activities.api import list_activities
    from app.domains.mdm.api import module_enabled
    from app.kernel.modules import ModuleCode
    from app.ui import templates

    count = (node.get("attrs") or {}).get("count")
    if not module_enabled(ModuleCode.ACTIVITIES) or not isinstance(count, int):
        return _unreachable_html("activities", "empty") if preview else ""
    own_db = SessionLocal() if db is None else None
    session = db if db is not None else own_db
    try:
        activities = list_activities(session, scope="upcoming")[:count]
        if not activities:
            return _unreachable_html("activities", "empty") if preview else ""
        return (
            templates.env.get_template("_activiteiten_cards.html")
            .render(activities=activities, current_year=belgian_today().year, scope="upcoming")
            .strip()
        )
    finally:
        if own_db is not None:
            own_db.close()


def _albums_html(node: dict, preview: bool = False, db=None) -> str:
    """The album card (CR-32 R13, R14, F13): ONE `pub.photo_card` — the photo
    page's card, one picture slot — that moves through the latest `albums` albums
    and at most `photos` photos of each, one photo at a time, the cover first, then
    the next album; every `interval` seconds, in the visitor's browser (Alpine). The
    card links to the album it shows at that moment. It stands still with interval
    0, under `prefers-reduced-motion` (in the script) and in the admin preview. An
    album without a photo is skipped (`list_albums` holds only albums with one);
    with no album at all the block is nothing on the site and its reason in the
    preview."""
    from datetime import date

    from app.database import SessionLocal
    from app.domains.media.api import list_activity_photos, list_albums, media_url
    from app.ui import path_for, templates

    attrs = node.get("attrs") or {}
    albums_n, photos_n, interval = attrs.get("albums"), attrs.get("photos"), attrs.get("interval")
    if not (isinstance(albums_n, int) and isinstance(photos_n, int) and isinstance(interval, int)):
        return ""
    own_db = SessionLocal() if db is None else None
    session = db if db is not None else own_db
    try:

        def when(album):
            return album.sort_date or (album.dates[0].start_date if album.dates else None)

        latest = sorted(
            list_albums(session), key=lambda a: (when(a) or date.min, a.id), reverse=True
        )[:albums_n]
        short_date = templates.env.filters["kortedatum"]
        frames = []
        for album in latest:
            for photo in list_activity_photos(session, album.id)[:photos_n]:
                frames.append(
                    {
                        "src": media_url(photo["id"], thumb=True),
                        "name": album.name,
                        "date": short_date(when(album)) if when(album) else "",
                        "href": path_for(f"/activiteiten/{album.id}/fotos"),
                    }
                )
    finally:
        if own_db is not None:
            own_db.close()
    if not frames:
        return _unreachable_html("albums", "empty") if preview else ""
    first = frames[0]
    macro = getattr(templates.env.get_template("_public_macros.html").module, "photo_card")
    return str(
        macro(
            first["name"],
            first["href"],
            first["src"],
            None,
            frames=frames,
            interval=0 if preview else interval,
            date_text=first["date"],
        )
    ).strip()


def _gallery_html(node: dict, preview: bool = False, db=None) -> str:
    """One album as a grid of its photos (CR-32 R20): each a thumbnail that opens
    the photo. The data is the media module's, asked through its facade; an
    activity that is no album (any more) or holds no photo renders NOTHING on the
    site — the reason in the admin preview, as for a button that leads nowhere.
    The photos carry the kit's own look (the prose rules' radius and shadow)."""
    from app.database import SessionLocal
    from app.domains.media.api import list_activity_photos, list_albums, media_url

    activity_id = (node.get("attrs") or {}).get("activity_id")
    own_db = SessionLocal() if db is None else None
    session = db if db is not None else own_db
    try:
        photos = (
            list_activity_photos(session, activity_id)
            if isinstance(activity_id, int)
            and any(album.id == activity_id for album in list_albums(session))
            else []
        )
    finally:
        if own_db is not None:
            own_db.close()
    if not photos:
        return _unreachable_html("gallery", "empty") if preview else ""
    items = "".join(
        f'<a href="{media_url(photo["id"])}">'
        f'<img src="{media_url(photo["id"], thumb=True)}" alt="{escape(photo.get("title") or "", quote=True)}" '
        'loading="lazy"></a>'
        for photo in photos
    )
    return f'<div class="prose-gallery">{items}</div>'


def _cards_html(node: dict, preview: bool = False, db=None) -> str:
    """A block of link cards (C4.9, C4.13): layout, not data. How many stand
    in a row is the look's own rule, read from the block (`build-css.sh`). A
    card whose destination cannot be reached is left out on the site and shows
    its reason in the admin preview; a block with no card left renders
    nothing."""
    cards = [
        html
        for html in (_card_html(card, preview, db) for card in node.get("content") or [])
        if html
    ]
    if not cards:
        return ""
    return f'<div class="prose-cards">{"".join(cards)}</div>'


def _card_html(node: dict, preview: bool = False, db=None) -> str:
    """One card: the whole card is the link (the title's link is stretched
    over it by the look's rules), so there is one link and no nested one."""
    from app.domains.media.api import media_url
    from app.ui.kit.icons import icon_paths

    attrs = node.get("attrs") or {}
    # A card with no destination at all is a text card (CR-32 R4): no link and
    # nothing to resolve. One with a destination that cannot be reached stays
    # left out, as before.
    from app.domains.cms.schema import destinations_set

    text_card = not destinations_set(attrs)
    address, reason, outside = (None, None, False) if text_card else _resolved(attrs, db)
    if address is None and not text_card:
        return _unreachable_html("card", reason or "page") if preview else ""
    top = ""
    if attrs.get("media_id") is not None:
        # Decorative: the title beside it is the link's name.
        top = (
            f'<img class="prose-card-picture" src="{media_url(attrs["media_id"])}" '
            'alt="" loading="lazy">'
        )
    elif attrs.get("icon") in icon_paths():
        top = (
            '<span class="prose-card-icon" aria-hidden="true">'
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            f'stroke-linejoin="round">{icon_paths()[attrs["icon"]]}</svg></span>'
        )
    rel = ' rel="noopener noreferrer"' if outside else ""
    if text_card:
        title = f'<span class="prose-card-title">{escape(attrs.get("title") or "")}</span>'
    else:
        title = (
            f'<a class="prose-card-title" href="{escape(address or "", quote=True)}"{rel}>'
            f"{escape(attrs.get('title') or '')}</a>"
        )
    number = (
        f'<span class="prose-card-number">{escape(attrs["number"])}</span>'
        if attrs.get("number")
        else ""
    )
    body = f'<p class="prose-card-text">{escape(attrs["text"])}</p>' if attrs.get("text") else ""
    line = (
        f'<span class="prose-card-line">{escape(attrs["line"])}</span>' if attrs.get("line") else ""
    )
    labels = [escape(label) for label in attrs.get("labels") or [] if label.strip()]
    marks = f'<span class="prose-card-labels">{" · ".join(labels)}</span>' if labels else ""
    cls = "prose-card prose-card--text" if text_card else "prose-card"
    return f'<div class="{cls}">{number}{top}{title}{line}{body}{marks}</div>'


def render_document(
    document,
    db=None,
    *,
    target: str = "site",
    preview: bool = False,
    viewer=None,
    blocks: "Mapping[str, Callable[[dict], str]] | None" = None,
) -> str:
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
        document = json.loads(document)
    if target == "text":
        return _document_text(document, db)
    return flat_html(
        render_document_parts(document, db, preview=preview, viewer=viewer, blocks=blocks)
    )


#: What renders each data block of `schema.DATA_BLOCKS`: one function per block.
_DATA_BLOCKS = {
    "activities": lambda node, preview, db: _activities_html(node, preview=preview, db=db),
    "albums": lambda node, preview, db: _albums_html(node, preview=preview, db=db),
}


def render_document_parts(
    document, db=None, *, preview: bool = False, viewer=None, blocks=None
) -> "list[tuple]":
    """The page as parts, in order (CR-32 phase 5): `("prose", html)` for what the
    author wrote — the stretch of blocks between two data blocks — and
    `("data", html)` for a data block of a module (the activity list). A data block
    is the module's own markup, with its own classes, and it does not stand inside
    the prose styling: the page template puts each part in its own container, the
    prose in `prose-raak`, a data block beside it.

    A data block stands at the root, or in a column of a columns block at the root
    (the grammar and `schema._validate_node`, #2101). A columns block that holds one
    is a third kind of part, `("columns", ratio, cells)`: each cell a list of parts
    split as at the root. A columns block without a data block stays in the prose,
    so no page without one changes.

    The visitor the page is rendered for (`viewer`, F14) is an input: held for the
    length of the call, so a button to "Word lid" can send a member with a household
    to the household instead."""
    if isinstance(document, str):
        document = json.loads(document)
    token = _VIEWER.set(viewer)
    blocks_token = _BLOCKS.set(blocks)
    try:
        return _split_parts((document or {}).get("content") or [], preview, db, root=True)
    finally:
        _VIEWER.reset(token)
        _BLOCKS.reset(blocks_token)


def _holds_data_block(columns: dict) -> bool:
    from app.domains.cms.schema import DATA_BLOCKS

    return any(
        child.get("type") in DATA_BLOCKS
        for column in columns.get("content") or []
        for child in column.get("content") or []
    )


def _split_parts(nodes: list, preview: bool, db, *, root: bool) -> "list[tuple]":
    """The nodes of the root, or of one cell, as parts: the prose in runs, a data block
    apart. Only the root cuts a columns block that holds a data block out of the prose."""
    from app.domains.cms.schema import DATA_BLOCKS

    parts: list[tuple] = []
    run: list[dict] = []

    def close_run() -> None:
        if run:
            parts.append(("prose", _finish_prose(list(run), preview, db)))
            run.clear()

    for node in nodes:
        if node.get("type") in DATA_BLOCKS:
            close_run()
            block = _DATA_BLOCKS[node["type"]](node, preview=preview, db=db)
            if block:
                parts.append(("data", block))
        elif root and node.get("type") == "columns" and _holds_data_block(node):
            close_run()
            cells = [
                _split_parts(column.get("content") or [], preview, db, root=False)
                for column in node.get("content") or []
            ]
            if any(cells):
                ratio = (node.get("attrs") or {}).get("ratio")
                parts.append(("columns", ratio if ratio != "equal" else None, cells))
        else:
            run.append(node)
    close_run()
    return parts


def flat_html(parts: "list[tuple]") -> str:
    """The parts as one string: for a caller that wants the page's HTML and not its
    containers. A columns part is drawn with the prose's own grid classes."""
    out: list[str] = []
    for part in parts:
        if part[0] == "columns":
            modifier = f" prose-columns--{part[1]}" if part[1] else ""
            cells = "".join(
                f'<div class="prose-column">{flat_html(cell)}</div>' for cell in part[2]
            )
            out.append(f'<div class="prose-columns{modifier}">{cells}</div>')
        else:
            out.append(part[1])
    return "".join(out)


def _finish_prose(blocks: list[dict], preview: bool, db) -> str:
    """One stretch of the author's blocks as safe HTML: built, sanitised, the
    blocks built in code placed after the sanitiser, then the substitutions the
    text may carry — the codes first, then the sites cards and a form button."""
    late: list[str] = []
    html = _blocks_html(blocks, preview=preview, db=db, late=late)
    html = sanitize_cms_html(html) or ""
    for index, block in enumerate(late):
        html = html.replace(f"<div>{_LATE}{index}{_LATE}</div>", block)
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
                # An item holds blocks, not only inlines: a nested list (or a
                # paragraph after her) lost her words when only the inline
                # parts were read (review B2, #1770). Blocks walk in order;
                # an inline-only item keeps her one line.
                for b in item.get("content") or []:
                    if b.get("type") in ("bulletList", "orderedList", "table", "figure"):
                        walk(b)
                    else:
                        words = _inline_text(b.get("content") or [])
                        if number is None:
                            lines.append(f"- {words}")
                        else:
                            lines.append(f"{number}. {words}")
                            number += 1
        elif kind == "table":
            for row in content:
                cells = []
                for cell in row.get("content") or []:
                    words = " ".join(
                        _inline_text(p.get("content") or []) for p in cell.get("content") or []
                    )
                    cells.append(words)
                lines.append(" | ".join(cells))
        elif kind == "figure":
            alt = (node.get("attrs") or {}).get("alt") or ""
            if alt:
                lines.append(alt)
        elif kind in ("columns", "column", "blockquote", "section"):
            eyebrow = (node.get("attrs") or {}).get("eyebrow") if kind == "section" else None
            if eyebrow:
                lines.append(eyebrow)
            for child in content:
                walk(child)
        elif kind == "callout":
            # Her words are content, not attributes (the review's B3: read
            # from where they stand, never silently dropped).
            words = _inline_text(content)
            if words:
                lines.append(words)
        elif kind in ("button", "card", "cards"):
            attrs = node.get("attrs") or {}
            words = " ".join(
                str(attrs.get(k, ""))
                for k in ("label", "number", "title", "line", "text")
                if attrs.get(k)
            )
            if words:
                lines.append(words)
            for child in content:
                walk(child)

    def _inline_text(nodes: list) -> str:
        words = []
        for node in nodes:
            kind = node["type"]
            if kind == "text":
                words.append(unescape(node.get("text", "")))
            elif kind == "hardBreak":
                words.append(" ")
            elif kind == "value":
                code = node.get("attrs", {}).get("code", "")
                words.append(
                    "{{tenants}}" if code == "tenants" else unescape(_values().get(code, ""))
                )
        # A word split over two marks ("wo" + "rd", each bold) is one word:
        # joining with a space made "wo rd" of her (review B2, #1770). The
        # spaces the author typed sit IN her text nodes; a hardBreak is the
        # only inline that stands for a break of her own.
        text = "".join(words)
        for code, value in _values().items():
            text = text.replace(f"{{{{{code}}}}}", value)
        return text.strip()

    walk(document)
    text = "\n\n".join(line for line in lines if line.strip())
    # The same substitutions the site carries, as their words (#1615's rule:
    # a placeholder is shown in WORDS, never its markup).
    text = _SITES.sub(lambda m: sites_in_words(m.group(1), db), text)
    return _FORM.sub(lambda m: unescape(m.group(2) or "").strip() or m.group(1), text)
