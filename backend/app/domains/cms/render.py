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
    "form:berichten|Contacteer ons": "Dezelfde knop met een eigen tekst na het streepje",
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
    from app.database import SessionLocal
    from app.domains.mdm.api import OrganizationType, active_sites_by_account
    from app.i18n import _
    from app.kernel.tenant_config import platform_home_url, tenant_display_name, tenant_home_url
    from app.ui import templates

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
        if not groups:
            return ""
        return templates.env.get_template("_tenant_sites.html").render(groups=groups).strip()
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


def render_cms_content(content: Optional[str], db=None) -> Optional[str]:
    """Vervang elke ``{{code}}`` door de bijbehorende configuratiewaarde en
    sanitize het resultaat (#476) — dé functie op elk publiek CMS-renderpunt.
    `db` (#1543): the request's session, for the sites placeholder."""
    if not content:
        return content
    for code, value in _values().items():
        content = content.replace(f"{{{{{code}}}}}", value)
    # Before sanitisation (#1173): that step removes the figure holding the alt.
    content = sanitize_cms_html(image_attributes_from_attachment(content)) or ""
    # After it (#1543): the site cards are built and escaped in code — see `_sites_html`.
    content = _SITES.sub(lambda m: _sites_html(m.group(1), db), content)
    # And the form buttons (#1567), the same way.
    return _FORM.sub(lambda m: _form_button_html(m.group(1), m.group(2), db), content)
