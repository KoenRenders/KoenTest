"""UI-fundament (#396/#398, §21): Jinja-templates + htmx/Alpine, server-rendered.

Elke component levert zijn schermen als ``ui.py`` (routes: view-model bouwen,
template kiezen) + ``templates/`` (dom: alleen tonen). Dit pakket levert de
gedeelde machinerie: de template-omgeving (met de component-template-mappen),
de UI-kit-macro's en de shells (base-layouts).
"""

import functools
import hashlib
import inspect
import logging
from collections.abc import Callable
from functools import lru_cache
from pathlib import Path

from fastapi import HTTPException
from fastapi.templating import Jinja2Templates
from jinja2 import (
    Environment,
    FileSystemLoader,
    StrictUndefined,
    Undefined,
    make_logging_undefined,
    pass_context,
)

from app.config import settings
from app.kernel.phone import readable_phone
from app.kernel.refusals import as_refusal

_UI_DIR = Path(__file__).parent

# Component-template-mappen haken hier in (fase 0+ voegen paden toe).
_DOMAINS = _UI_DIR.parent / "domains"
template_dirs: list[str] = [str(_UI_DIR / "templates")] + sorted(
    str(p) for p in _DOMAINS.glob("*/templates") if p.is_dir()
)

# ── Undefined-beleid (#643) ───────────────────────────────────────────────────
# In React ving TypeScript een verkeerde propnaam vóór de browser; Jinja rendert
# een verkeerde variabelenaam standaard als lege string. Zo kon een route `totaal`
# doorgeven terwijl de template `total` las, met 830 groene tests en een leeg vak
# op het scherm — de structurele oorzaak achter #613/#616.
#
# Dev, test en HDEV draaien daarom StrictUndefined: een onbestaande variabele is
# een fout, en de render-gate (#622) betrapt hem vóór de deploy. UAT en PROD
# rendern leeg mét een WARNING in de log: een typo mag daar nooit een 500 worden
# voor een bezoeker.
_STRICT_ENVS = {"dev", "test", "hdev"}
_undefined = (
    StrictUndefined
    if settings.app_env in _STRICT_ENVS
    else make_logging_undefined(logger=logging.getLogger("app.ui.undefined"), base=Undefined)
)

# LET OP — `autoescape=True` is hier XSS-kritisch. Starlette zet autoescape zelf
# wanneer je `directory=` meegeeft, maar NIET wanneer je een eigen `env=`
# meegeeft: dan is het jouw environment en jouw verantwoordelijkheid. Zonder deze
# regel gaat élke `{{ }}` ongeëscapet naar de browser. De lint-gate bewaakt dat
# de regel hier letterlijk blijft staan.
_env = Environment(loader=FileSystemLoader(template_dirs), undefined=_undefined, autoescape=True)

templates = Jinja2Templates(env=_env)

# Taalbeleid (#407-T): {{ _("...") }} beschikbaar in alle templates, volgend
# op de actieve tenant-taal.
from app.i18n import install_jinja_i18n  # noqa: E402

install_jinja_i18n(templates.env)

# CR-12: `{{ code | code_label("meeting_status") }}` and `| tone(...)`. The one
# way a template turns a code into text, so the Dutch words of a status live in
# the label table and not in a dictionary inside a screen. Registered here, next
# to gettext, because the two answer the same question for two kinds of string:
# `_()` for a sentence, `code_label` for a fact about a code.
from app.kernel.codes import install_enum_guard, install_jinja_codes  # noqa: E402

install_jinja_codes(templates.env)

# CR-12, the twelfth gate: no enum member reaches the output. Three times in
# this change request a member ended up in a `value=` attribute — the
# subscriber filter, the audience choice and the attendance button — and none
# of the eleven gates could find it, because a member that is RENDERED is not a
# comparison. This hooks `finalize`, which Jinja calls for every `{{ }}`, so
# every render test in the suite is a detector at once. The same strict/lenient
# line as `StrictUndefined` above, and for the same reason.
install_enum_guard(templates.env, strict=settings.app_env in _STRICT_ENVS)


# #974: de opmaak zelf staat in `app.i18n.long_date`, zodat een domein dezelfde
# woorden kan gebruiken zonder de UI-laag te importeren.
from app.i18n import long_date as _langedatum  # noqa: E402

templates.env.filters["langedatum"] = _langedatum

# #1051: dezelfde datum zonder jaartal, voor de deadline-regel op de publieke
# kaart — het jaar staat in de datumregel erboven.
from app.i18n import long_date_no_year as _datumzonderjaar  # noqa: E402

templates.env.filters["datumzonderjaar"] = _datumzonderjaar

# #1238 punt 6: de korte, Belgische datum. Het ledenportaal was het enige scherm dat
# een geboortedatum kaal afdrukte (`1955-10-30`), tien pixels naast een invoerveld dat
# `30-10-1955` toont — en dat scherm gaat als schermafdruk naar een publieke
# uitlegpagina. `strftime` kon daar niet: dat portaal rendert uit een geserialiseerd
# view-model, waarin de datum al een string is.
from app.i18n import short_date as _short_date  # noqa: E402
from app.i18n import short_datetime as _short_datetime  # noqa: E402

templates.env.filters["kortedatum"] = _short_date
templates.env.filters["short_datetime"] = _short_datetime


def _maandkort(d) -> str:
    """Korte Nederlandse maand voor het datumblok op activiteitenkaarten
    (Ontwerpspoor golf 1, #913): 'sep', 'okt' — zelfde babel-bron als
    `langedatum`, dus dezelfde taalinstelling."""
    if d is None:
        return ""
    from babel.dates import format_date

    from app.i18n import current_locale

    return format_date(d, format="MMM", locale=current_locale.get()).rstrip(".")


templates.env.filters["maandkort"] = _maandkort


def _paragraphs(text: str | None):
    """Plain text as paragraphs (#1647): a blank line starts a paragraph, a
    single line break starts a new line. The text is ESCAPED first — whatever
    it holds reaches the page as text, never as markup — and only then gets
    the `<p>` and the line elements this function writes itself.

    A line the author ended with ONE Enter is an element of its own
    (`<span data-line>`, #1688), not a `<br>`: the page gives it a little
    space above, so a statement that wraps can be told from the next
    statement. That is what an Enter means on the poster too
    (`designstudio.richtext`: the step onto a line after an Enter is 1.6 of
    the type size instead of 1.3 — about a quarter of a line more; a blank
    line is a line more). The page follows the same order — a small space at
    an Enter, a larger one at a blank line — in its own scale: 8 and 16 px.
    A paragraph of one line stays a plain `<p>`.
    """
    import re as _re

    from markupsafe import Markup, escape

    blocks = [b.strip() for b in _re.split(r"\n\s*\n", (text or "").replace("\r\n", "\n"))]

    def paragraph(block: str) -> Markup:
        lines = [line.strip() for line in block.split("\n") if line.strip()]
        if len(lines) == 1:
            return Markup("<p>") + escape(lines[0]) + Markup("</p>")
        return (
            Markup("<p>")
            + Markup("").join(
                Markup("<span data-line>") + escape(line) + Markup("</span>") for line in lines
            )
            + Markup("</p>")
        )

    return Markup("").join(paragraph(block) for block in blocks if block)


templates.env.filters["alineas"] = _paragraphs


# Geldbedragen in nl-BE-notatie (#735): `{{ bedrag|geld }}` → "35,00". Het euroteken
# staat in de sjablonen, zodat de opmaak eromheen (kleur, uitlijning) daar blijft.
from app.kernel.geld import bedrag as _bedrag  # noqa: E402

templates.env.filters["geld"] = _bedrag
# #1675: a stored phone number as a person reads it — the one formatter, for
# every template that SHOWS a number. An input, a `tel:` link and an export
# keep the stored value (`test_phone_numbers_are_shown_readable`).
templates.env.filters["phone"] = readable_phone
# Also as a global, for the kit: a FILTER is resolved when a template is compiled,
# so `|geld` inside `_macros.html` breaks every environment that loads the kit
# without this filter (the hand-built ones of the shell tests); a global is
# looked up only when the macro runs (`ui.amount`, #1556).
templates.env.globals["geld"] = _bedrag


# Een meetwaarde per opmaaksoort (#875): `{{ waarde|meetwaarde(c.format) }}`. Eén
# plek voor alle vijf de soorten die de universe declareert — het paneel kende er
# één en drukte de rest rauw af, met `0E-20` als resultaat.
from app.kernel.meetwaarden import meetwaarde as _meetwaarde  # noqa: E402

templates.env.filters["meetwaarde"] = _meetwaarde


# Relatietype leesbaar tonen (#476): ruwe code → label i.p.v. "HOOFDLID".
#
# CR-12 phase 2: this used to be a dictionary of three Dutch words. The label
# now comes from `mdm.relation_type_labels`, so the screen and an export show
# the same word and an English-language unit sees English. The filter stays
# because the templates know it by name; it is now one line around
# `code_label`.
def _relatielabel(code) -> str:
    from app.kernel.codes import code_label

    return code_label("relation_type", code) or "—"


templates.env.filters["relatielabel"] = _relatielabel


# ConfirmDialog (#514/#595): moet een PLAIN string teruggeven, geen Markup. Als macro
# (Markup) escapte de Jinja-`~`-concatenatie in `attrs='hx-post="…" ' ~
# confirm_attrs(…)` de dubbele quotes van hx-post/target/swap (→ `&#34;`), waardoor
# htmx die attributen niet meer las en delete-knoppen niets deden. Een gewone
# functie (plain str) laat `'plain' ~ 'plain'` = plain zonder escaping. De naam
# wordt attribuut-veilig ge-escaped (bv. een ' in een naam breekt de attr niet).
#
# Sinds #595 levert dit `data-confirm` i.p.v. `hx-confirm`: het native browser-
# confirm() is verbannen (lint-gate). De globale `htmx:confirm`-handler in
# ui.confirm_host() ziet `data-confirm` en toont de in-app bevestig-modal.
def _confirm_attrs(type_label, name) -> str:
    from markupsafe import escape

    from app.i18n import _

    return (
        f'data-confirm=\'{escape(type_label)} "{escape(name)}" '
        f"{escape(_('definitief verwijderen?'))}'"
    )


templates.env.globals["confirm_attrs"] = _confirm_attrs


def checked_figures(items) -> list:
    """The items of `ui.figures` as `KeyFigure`s (`docs/design-system-end-state.md`
    §3.8). The value object refuses an item that carries two figures — a
    `TypeError` at render (CR-11 B7 test 18)."""
    from app.kernel.key_figure import KeyFigure

    return [i if isinstance(i, KeyFigure) else KeyFigure(**i) for i in items]


templates.env.globals["checked_figures"] = checked_figures


# Gezinslabel (golf 9, #913): één bron voor "hoe heet dit gezin op het scherm"
# — de HOOFDLID-selectie stond in vijf kopieën (Jinja, mdm/ui 2x,
# payment-verrijking, audit-resolver).
def _gezinslabel(family) -> str:
    from app.domains.membership.api import family_label

    return family_label(family)


templates.env.globals["gezinslabel"] = _gezinslabel


# A7 (#913, golf 4): "de weg terug" is een gevalideerde INTERNE retourcontext, nooit
# de Referer-header. Een `?terug=`-parameter komt uit de URL en is dus door de
# gebruiker (of een mail-link) te vervalsen: zonder validatie wordt de terugknop een
# open redirect. Alleen een pad binnen deze site telt; al het andere — een absolute
# URL, het scheme-relatieve `//evil.example`, een backslash-variant die browsers
# stilletjes normaliseren, controltekens — valt terug op de canonieke plek van het
# record (de fallback), zodat de knop altijd ergens zinnigs heen gaat.
def veilige_terug(waarde: str | None, fallback: str) -> str:
    if (
        not waarde
        or not waarde.startswith("/")
        or waarde.startswith("//")
        or "\\" in waarde
        or any(ord(t) < 0x20 for t in waarde)
    ):
        return fallback
    return waarde


# ── The way back of a record page (CR-11 block 5, #1557) ────────────────────
#
# A record page's first line leads back to where the visitor came from, as it was
# left, and names it: "‹ Activiteiten" from the list (with its filter in the URL),
# "‹ Betaling van …" from a booking. The origin travels as `?terug=<local path>`
# on the link that opened the record; this is the one place that turns it into a
# label and an href. A screen never writes that link itself.

#: (path prefix, labeler(db, url) -> str | None). A domain registers the origins
#: only it can name — a booking's "Betaling van <naam>" is the payment domain's.
_ORIGIN_LABELERS: list[tuple[str, Callable[..., str | None]]] = []


def register_origin(prefix: str, labeler: Callable[..., str | None]) -> None:
    """Let a domain name an origin under `prefix` (a local path). `labeler(db,
    url)` returns the label, or None to leave it to the list's menu name."""
    if (prefix, labeler) not in _ORIGIN_LABELERS:
        _ORIGIN_LABELERS.append((prefix, labeler))


def _menu_name(href: str) -> str | None:
    """The menu label of the list `href` lives under: the longest menu path it
    starts with."""
    from app.i18n import _

    path = href.split("?")[0].split("#")[0]
    best = max(
        ((h, label) for h, label in _ADMIN_NAV if path == h or path.startswith(h + "/")),
        key=lambda item: len(item[0]),
        default=None,
    )
    return _(best[1]) if best else None


def way_back(db, terug: str | None, list_href: str) -> dict:
    """The way back of a record page: `{label, href, keep}`.

    `list_href` is the entity's list — where the record leads back to when it was
    opened from nowhere. With a valid `terug` (a local path, `veilige_terug`)
    the link goes there instead and is named after it: a registered origin's own
    label, else the menu name of the list it points into. `keep` is the query
    the record's own links carry on (`terug=…`), so the origin survives a tab
    change and the edit state.
    """
    from urllib.parse import urlencode

    origin = veilige_terug(terug, "")
    href = origin or list_href
    label = None
    if origin:
        path = origin.split("?")[0].split("#")[0]
        for prefix, labeler in _ORIGIN_LABELERS:
            if path == prefix or path.startswith(prefix + "/"):
                label = labeler(db, origin)
                if label:
                    break
    label = label or _menu_name(href) or _menu_name(list_href) or ""
    return {"label": label, "href": href, "keep": urlencode({"terug": origin}) if origin else ""}


def record_frame(request, db, list_href: str) -> dict:
    """What a record page's head needs from the request (#1557): the way back and
    whether the page is in its edit state (`?bewerken=1`).

    Read through `filterparams`, so a fragment answer that carries the head along
    out of band — a save inside the record — still knows both: htmx sends the
    page's own URL as `HX-Current-URL`, and the save's own URL has neither.

    A boosted navigation is the exception (#1558): it is an htmx request too, but
    its `HX-Current-URL` is the page being LEFT. "Annuleren" in the editor links
    to the same record without `?bewerken=1`; merged with the page it leaves, the
    editor would open again. A navigation's own address is the whole truth.
    """
    boosted = request.headers.get("hx-boosted") == "true"
    params = dict(request.query_params) if boosted else filterparams(request)
    return {
        "way_back": way_back(db, params.get("terug"), list_href),
        "head_editing": params.get("bewerken") == "1",
    }


def list_return(path: str, **state) -> str:
    """The address a list hands its rows as their way back: the list's page path
    with its state — only what differs from empty, so a plain list stays a plain
    path."""
    from urllib.parse import urlencode

    query = urlencode({k: v for k, v in state.items() if v not in (None, "")})
    return f"{path}?{query}" if query else path


# #718: de navigatiebalk van een schil reist out-of-band mee (#714) — maar dat mag
# ALLEEN bij een gebooste navigatie.
#
# htmx licht een `hx-swap-oob`-element uit het antwoord vóór de gewone swap. Bij een
# gebooste navigatie is dat precies wat we willen: het antwoord is een volledige
# pagina, maar `_boosted_swap_headers` (main.py) laat er via HX-Reselect enkel `#main`
# uit swappen, dus zonder die out-of-band-truc zou de navigatie nooit meebewegen en
# bleef de actieve markering achter.
#
# Bij élk ander htmx-verzoek werkt diezelfde truc averechts. Negen formulieren doen
# `hx-target="body" hx-swap="innerHTML"` en krijgen een volledige pagina terug: htmx
# haalt de navigatie eruit, zet ze in het bestaande DOM, en vervangt dan het hele
# lichaam door wat overblijft — zonder navigatie. Het logo bleef staan omdat het
# buiten die container valt. Eén keer verversen bracht alles terug, want de server
# stuurde wél correcte HTML; het ging mis bij het samenvoegen.
#
# Vandaar deze ene vlag in plaats van negen aangepaste formulieren: de out-of-band
# navigatie is er voor een DEEL-antwoord, en `HX-Boosted` is exact de voorwaarde
# waaronder er maar een deel geswapt wordt — dezelfde voorwaarde die
# `_boosted_swap_headers` gebruikt om de reselect te zetten.
def _nav_oob(request) -> bool:
    return request.headers.get("HX-Boosted") == "true"


templates.env.globals["nav_oob"] = _nav_oob


def _beheer_account(request) -> dict | None:
    """Accountchip rechtsboven in de beheerschil (golf 2, #913, beslissing i).

    Bewust DB-loos: de e-mail komt rechtstreeks uit de sessiecookie, dus de schil
    hoeft geen gebruikerscontext van elk scherm te eisen. Naam en rol volgen
    wanneer een latere golf een gedeelde gebruikerscontext invoert."""
    if request is None:
        return None
    try:
        from app.domains.auth.api import SESSION_COOKIE, read_session_value

        email = read_session_value(request.cookies.get(SESSION_COOKIE))
    except Exception:  # noqa: BLE001 - de schil mag nooit breken op een chip
        return None
    if not email:
        return None
    import re as _re

    delen = [d for d in _re.split(r"[._-]+", email.split("@")[0]) if d]
    initialen = "".join(d[0] for d in delen[:2]).upper() or email[:2].upper()
    return {"email": email, "initialen": initialen}


templates.env.globals["beheer_account"] = _beheer_account


# Golf 2-nazorg (#913, Koens pakket-2-feedback): linksboven staat niet langer het
# Raak-woordmerk maar de TENANTNAAM met het productlabel "Werkruimte" eronder —
# de beheerschil is een product dat ook niet-Raak-organisaties bedient
# (design-system §12-beslissing a). De naam komt uit de tenant-instellingen en
# wordt per tenant gecachet: schilchrome, één query per proces per tenant. Een
# hernoemde tenant verschijnt na een herstart — dat is de bewuste prijs; de
# instelling wijzigt zelden en de schil mag geen query per paginaweergave kosten.
_werkruimte_cache: dict[int, str] = {}


def _werkruimte_naam() -> str:
    from app.kernel.tenancy import current_tenant_id

    # ContextVar kan None dragen buiten een request; 0 is dan de cachesleutel
    # en tenant_display_name valt zelf terug op de default.
    tid = current_tenant_id.get() or 0
    naam = _werkruimte_cache.get(tid)
    if naam is None:
        try:
            from app.database import SessionLocal
            from app.kernel.tenant_config import tenant_display_name

            db = SessionLocal()
            try:
                naam = tenant_display_name(db, tenant_id=tid)
            finally:
                db.close()
        except Exception:  # noqa: BLE001 - chrome mag nooit een scherm breken
            naam = "Werkruimte"
        _werkruimte_cache[tid] = naam
    return naam


templates.env.globals["werkruimte_naam"] = _werkruimte_naam


def _assistant_in_shell() -> bool:
    """Does the back office's shell carry the Assistent (CR-11 K8, #1562)?

    What is known without a query: the environment's switch, and the two
    modules it needs — the assistant itself and the reporting it reads. The
    tenant's own switch and the visitor's role are the trigger's to ask (the
    route behind it, in the reporting domain): shell chrome may not cost a query
    per page view."""
    from app.domains.mdm.api import module_enabled
    from app.kernel.modules import ModuleCode

    return (
        _settings.admin_chat_enabled
        and module_enabled(ModuleCode.CHATBOT)
        and module_enabled(ModuleCode.REPORTING)
    )


templates.env.globals["assistant_in_shell"] = _assistant_in_shell

# Omgevings-indicator (#464): [HDEV]/[UAT] in titel + gekleurde band. Als globale
# beschikbaar in álle templates (publiek + admin); PROD blijft schoon.
from app.config import settings as _settings  # noqa: E402

templates.env.globals["omgeving"] = _settings.app_env


# Screenshot flag (#1238): the capture tool says only *that* this is a capture; the
# shell decides for itself not to render the environment banner. One source — the
# alternative was a style rule injected by the tool, i.e. a second place that knows
# what that banner looks like and drifts the moment the banner changes.
#
# The header can never take the banner off a real test environment, and that is the
# point of the second condition: only APP_ENV=dev honours it, and `dev` is the only
# value the tool ever runs against (docker-compose.dev.yml, scripts/e2e-local.sh and
# the e2e CI job all set it). So HDEV, UAT and PROD keep the banner whatever a caller
# sends. Together with the tool's own localhost guard that is two locks on the door
# the banner exists to keep shut.
#
# `pass_context` rather than a request parameter: the shells are also rendered bare in
# the markup tests, where `request` is undefined. Reading it from the render context
# yields None there instead of an UndefinedError, so the shells can call this without
# the `request is defined` dance — and the failure direction is the safe one (no
# request, no flag, banner shown).
SCREENSHOT_HEADER = "X-Raak-Screenshot"


@pass_context
def _is_screenshot(ctx) -> bool:
    if _settings.app_env != "dev":
        return False
    request = ctx.get("request")
    headers = getattr(request, "headers", None)
    if headers is None:
        return False
    return headers.get(SCREENSHOT_HEADER) == "1"


templates.env.globals["is_screenshot"] = _is_screenshot


# Cache-busting voor statische bestanden (#481 voor de CSS, #773 voor de rest).
#
# Zonder versie in de URL beslist de browser zelf hoe lang hij een bestand vers vindt
# — de server stuurt enkel een ETag en een Last-Modified. Bij de CSS was dat sinds
# #481 opgelost; de JavaScript werd kaal geladen, en dat is één keer duur geweest: de
# fix uit #751 stond een uur op HDEV terwijl de browser nog de `stt.js` van de dag
# ervóór draaide. Drie symptomen tegelijk, alle drie van een bug die al gerepareerd
# was. Er komt geen foutmelding bij; het oude bestand doet gewoon nog wat het deed.
#
# De versie komt uit de INHOUD en niet uit een tijdstempel. Dat verschil is de kern:
# een tijdstempel wijzigt bij elke deploy en gooit dan de cache van elke bezoeker weg,
# ook voor de bestanden die niemand heeft aangeraakt. Een inhoudshash wijzigt precies
# wanneer het bestand wijzigt, en geen moment eerder.
def statisch_hash(pad: Path) -> str:
    """De eerste acht tekens van de MD5 van de inhoud; `0` als het bestand ontbreekt.

    MD5 en niet iets sterkers: dit is een cache-sleutel en geen handtekening. Er valt
    hier niets te vervalsen — wie het bestand kan wijzigen, kan ook de hash wijzigen.
    """
    try:
        return hashlib.md5(pad.read_bytes()).hexdigest()[:8]
    except OSError:
        return "0"


_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"


@lru_cache(maxsize=None)
def statisch(naam: str) -> str:
    """`statisch("stt.js")` → `/static/stt.js?v=1a2b3c4d`.

    Gecachet, dus een wijziging tijdens het draaien komt er pas na een herstart in —
    net zoals de oude `css_version`, die de hash bij het importeren berekende. In dev
    herstart uvicorn bij elke bestandswijziging, dus daar merk je er niets van.
    """
    return f"/static/{naam}?v={statisch_hash(_STATIC_DIR / naam)}"


def path_for(pad: str) -> str:
    """Een intern pad, voorzien van de tenant-prefix wanneer dat nodig is (#889).

    Kwam je via `/raakmillegem/...` op een platform-host binnen, dan hoort *Home* naar
    `/raakmillegem/` te wijzen en niet naar `/`. Vandaag staat er `/fotos` in de adresbalk
    terwijl je bij Millegem zit, en weet alleen een cookie dat nog. Drie dingen worden
    daarmee tegelijk goed:

    - **de URL zegt waar je bent**;
    - **een gedeelde link werkt** — stuur `/fotos` door en de ontvanger komt zonder jouw
      cookie ergens anders uit;
    - **de cookie wordt een vangnet in plaats van het mechanisme.** Nu is hij dragend, en
      wie zijn cookies wist verdwaalt.

    Doet niets wanneer de afdeling op haar eigen hostnaam draait: daar zou een prefix
    alleen maar lelijke URL's opleveren.

    `/admin`, `/static` en `/api` worden nooit geprefixt, en die uitzondering staat HIER
    en niet bij elke aanroeper: beheerschermen worden niet via een prefix bereikt, en een
    regel die je op tientallen plaatsen moet onthouden is een regel die iemand vergeet.
    """
    from app.kernel.tenancy import current_platform_host, current_tenant_code

    if not pad.startswith("/") or pad.startswith(("/admin", "/static", "/api")):
        return pad
    code = current_tenant_code.get()
    if not (current_platform_host.get() and code):
        return pad
    return f"/{code}" if pad == "/" else f"/{code}{pad}"


templates.env.globals["statisch"] = statisch


def _form_guard_token() -> str:
    """The signed render time of a public form (#1297), see `ui.form_guard_fields`."""
    from app.kernel.form_guard import issue_token

    return issue_token()


templates.env.globals["form_guard_token"] = _form_guard_token
templates.env.globals["path_for"] = path_for

# Canonieke admin-navigatie (React-exit 405-d, #405): één bron voor alle
# server-rendered beheer-schermen i.p.v. een kopie per module.
# Ontwerpspoor golf 2 (#913, triage A3/j): het menu draagt WERKGEBIEDEN — een
# vlak menu van veertien items was op de kantelgrens, en elke module die op de
# ERP-horizon bijkomt zou de verhuis duurder maken. De groepen zijn de bron;
# `_ADMIN_NAV` wordt eruit afgeleid voor wie de vlakke lijst nodig heeft
# (de render-gate bezoekt élk item, groep of niet).
_ADMIN_NAV_LAYOUT: list[tuple[str | None, list[str | tuple[str, str]]]] = [
    (None, ["/admin/werkbank"]),
    (
        "Werking",
        [
            "/admin/activiteiten",
            "/admin/leden",
            "/admin/formulieren",
        ],
    ),
    (
        "Inhoud",
        [
            "/admin/paginas",
            "/admin/media",
            "/admin/ai-context",
        ],
    ),
    (
        "Financieel",
        [
            "/admin/betalingen",
        ],
    ),
    # Communicatie (#258): wat naar buiten gaat. De vergaderingen gaan naar het
    # bestuur, de nieuwsbrief (#984, CR-05) naar leden en niet-leden.
    (
        "Communicatie",
        [
            "/admin/vergaderingen",
            "/admin/nieuwsbrieven",
            # Design Studio (#1007, CR-10): affiches en sociale beelden uit een activiteit.
            "/admin/ontwerpen",
        ],
    ),
    # Inzicht (Rapporten is niet enkel financieel; het dashboard verdient een
    # menuplek) staat vlak boven Systeem — volgorde beslist door Koen, 14 sep.
    (
        "Inzicht",
        [
            ("/admin", "Dashboard"),
            "/admin/rapporten",
        ],
    ),
    (
        "Systeem",
        [
            ("/admin/gebruikers", "Gebruikers"),
            ("/admin/ledenwijzigingen", "Wijzigingen"),
            ("/admin/e-maillog", "E-maillog"),
            # #971: twee items en geen één, want het zijn twee dingen. Een ORGANISATIE
            # is een rechtspersoon — naam, rechtsvorm, ondernemingsnummer, rekening —
            # en een TENANT is een site met haar instellingen. Meestal vallen ze samen,
            # maar de ACCOUNT-organisatie is geen tenant en stond daardoor nergens in
            # dit menu; net zij is de vzw met een ondernemingsnummer.
            # CR-22 S7 (#1712): the natural persons of this tenant, before the
            # organisation — master data, in the tenant workspace only.
            ("/admin/personen", "Personen"),
            ("/admin/organisaties", "Organisaties"),
            ("/admin/tenants", "Tenants"),
            # #1535: a tenant workspace's own organisation and site settings, in
            # the place where the platform workspace has Organisaties and Tenants.
            ("/admin/organisatie", "Onze organisatie"),
            ("/admin/instellingen", "Instellingen"),
            # GEEN Design system hier (#878). De balk is voor schermen waar een bestuurder
            # werk doet; `/admin/design-system` is naslag over knoppen, kleuren en afstanden —
            # nuttig bij het bouwen, niet bij het besturen. De route blijft bestaan achter
            # `require_admin_ui`, en je gaat ernaartoe via Info. "Uit het menu" is dus iets
            # anders dan "weg": ruim de route niet op omdat er niets meer naar wijst.
            ("/admin/info", "Info"),
        ],
    ),
]


def _resolve_layout() -> list[tuple[str | None, list[tuple[str, str]]]]:
    """The layout with every module item's label taken from the registry (#1476).

    A module's item is named in the layout by its href only: the label lives
    once, in `kernel.modules`, beside the module that owns it. The layout keeps
    what the registry does not know — the groups and their order — and the
    shell items (Dashboard, Gebruikers, Info, …) that belong to no module.
    """
    from app.kernel.modules import MODULES

    labels = {href: label for module in MODULES for href, label in module.admin_items}
    return [
        (group, [item if isinstance(item, tuple) else (item, labels[item]) for item in items])
        for group, items in _ADMIN_NAV_LAYOUT
    ]


#: The icon of each menu item (CR-11 block 1, #1482). Below 1 440 px the
#: sidebar is a rail of icons alone, the label a tooltip, so every item of the
#: layout has one — `tests/test_admin_frame_gate.py` holds that. None is a
#: verb's glyph (design-system-end-state §1.5, one meaning per glyph).
_ADMIN_NAV_ICONS: dict[str, str] = {
    "/admin/werkbank": "list-todo",
    "/admin/activiteiten": "calendar-days",
    "/admin/leden": "users",
    "/admin/formulieren": "clipboard-list",
    "/admin/paginas": "panels-top-left",
    "/admin/media": "image",
    "/admin/ai-context": "book-open",
    "/admin/betalingen": "wallet",
    "/admin/vergaderingen": "presentation",
    "/admin/nieuwsbrieven": "newspaper",
    "/admin/ontwerpen": "palette",
    "/admin": "layout-dashboard",
    "/admin/rapporten": "chart-pie",
    "/admin/gebruikers": "user-cog",
    "/admin/ledenwijzigingen": "history",
    "/admin/e-maillog": "inbox",
    "/admin/personen": "user",
    "/admin/organisaties": "building-2",
    "/admin/tenants": "globe",
    # #1535: one meaning per glyph — the own organisation is an organisation, and
    # it never stands in the same menu as Organisaties.
    "/admin/organisatie": "building-2",
    "/admin/instellingen": "settings",
    "/admin/info": "info",
}

#: #1535: the items of one workspace kind only. Platform administration —
#: every tenant, every organisation — is in the platform workspace's menu; a
#: tenant workspace has its own organisation and settings in their place.
PLATFORM_ONLY_ITEMS = frozenset({"/admin/organisaties", "/admin/tenants"})
TENANT_ONLY_ITEMS = frozenset({"/admin/personen", "/admin/organisatie", "/admin/instellingen"})


def _on_platform_workspace() -> bool:
    """Is this request in the platform workspace? From the cached platform id
    and the request's tenant: the menu is built on every page, without a query."""
    from app.domains.mdm.api import platform_tenant_id
    from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id

    platform = platform_tenant_id()
    return platform is not None and (current_tenant_id.get() or DEFAULT_TENANT_ID) == platform


#: The full menu, every module on — what a VERENIGING sees.
_ADMIN_NAV_GROEPEN: list[tuple[str | None, list[tuple[str, str]]]] = _resolve_layout()

_ADMIN_NAV: list[tuple[str, str]] = [item for _, _items in _ADMIN_NAV_GROEPEN for item in _items]


def refusal_response(request, errors, message_line: str, *, send: bool = False):
    """Why a form was refused, for its message line — and nothing else, so the
    form keeps what was typed (CR-11 block 9, #1561; public since #1589).

    An HTML 422 is swapped (#1515); the headers send it to `message_line` (a
    selector) instead of to the form's own target, whatever `hx-select` or
    `hx-swap` the form carries for its good answer. `errors` have a `field` (the
    form's name of a field, "" for the form as a whole) and a `message`; `send`
    words the banner for a form that is sent ("Verzenden kan nog niet…") instead
    of a record that is saved.

    """
    return templates.TemplateResponse(
        request,
        "_save_refusal.html",
        {"errors": list(errors), "send": send},
        status_code=422,
        headers={
            "HX-Retarget": message_line,
            "HX-Reswap": "innerHTML",
            "HX-Reselect": "[data-save-refusal]",
        },
    )


def says_why_in(line: str, *also: type[Exception]):
    """A refusal of this route goes to a message line of ITS form (#1831).

    For a page with several forms — a card per person, a form per question. A
    refusal of one answered a bare JSON error there, and the page showed the
    general message, "Er ging iets mis … probeer opnieuw", for something no retry
    mends. The rule's own sentence existed and never reached the screen.

    `line` is the selector of the form's message line, with the route's path
    parameters in braces (`#persoon-{person_id}-melding`). The answer is
    `refusal_response` — the banner alone, so the form keeps what was typed and
    the other forms are not touched. The sentence stands under "Opslaan is niet
    gelukt." as a whole-form message: the record form, which marks the field
    itself, serves one form per page.

    A refusal is an `HTTPException` with a status the visitor can do something
    about (`kernel.refusals.as_refusal`), whose detail is the
    sentence — and any exception type in `also`, a domain's own refusal that the
    application would answer as JSON, whose text is the sentence.
    """
    caught = (HTTPException, *also)

    def wrap(route):
        def refused(refusal: Exception, kwargs: dict):
            # `as_refusal` lets through what is no refusal: a 404, a 403.
            sentence = as_refusal(refusal)
            return refusal_response(kwargs["request"], [sentence], line.format(**kwargs))

        if inspect.iscoroutinefunction(route):

            @functools.wraps(route)
            async def answering(**kwargs):
                try:
                    return await route(**kwargs)
                except caught as refusal:
                    return refused(refusal, kwargs)

            return answering

        @functools.wraps(route)
        def answering_sync(**kwargs):
            try:
                return route(**kwargs)
            except caught as refusal:
                return refused(refusal, kwargs)

        return answering_sync

    return wrap


def is_fragment_request(request) -> bool:
    """Vraagt htmx hier een fragment, of navigeert de gebruiker naar deze pagina?

    Een lijstscherm geeft bij een htmx-verzoek alleen zijn kaartenfragment terug
    (zoeken/filteren) en anders de hele pagina. `HX-Request` alleen volstaat sinds
    #634 niet meer om die twee te onderscheiden: een gebooste navigatie — een klik
    op een nav-link — is óók een htmx-verzoek en draagt dus dezelfde header. Wie
    daarop vertakt, stuurt bij het navigeren een fragment terug, en de schil zoekt
    dan tevergeefs naar #main: het scherm loopt leeg.

    `HX-Boosted` is precies het onderscheid: htmx zet die alleen bij een gebooste
    link of formulier.
    """
    kop = request.headers
    return bool(kop.get("hx-request")) and kop.get("hx-boosted") != "true"


def filterparams(request) -> dict:
    """De filterstand van dit scherm, waar hij ook vandaan komt (#671).

    Een filterbalk vraagt haar lijst met `?status=…&q=…`, maar een **mutatie** post
    naar een eigen endpoint zonder die parameters. Wie enkel `request.query_params`
    las, kreeg na elke opslag de ongefilterde lijst terug — en omdat alleen het
    fragment geswapt wordt, bleef de balk de oude keuze tonen.

    Sinds `ui.filter_bar` `hx-push-url` zet, staat de filterstand in de browser-URL
    en stuurt htmx die bij élk verzoek mee als `HX-Current-URL`. Deze helper leest
    dus eerst die header en valt terug op de query-string — die tweede weg blijft
    nodig voor een gewone GET zonder htmx (een gedeelde link, een F5).

    Eén helper voor de vier modules die hun filter zo lezen (betalingen, leden,
    e-maillog, tenants): vier eigen varianten is precies hoe dit ontstaan is. Ze
    leest wat er ís — niet elk scherm heeft dezelfde parameters.
    """
    from urllib.parse import parse_qsl, urlsplit

    huidig = request.headers.get("hx-current-url")
    if huidig:
        params = dict(parse_qsl(urlsplit(huidig).query, keep_blank_values=True))
        # Een htmx-GET van de filterbalk zelf draagt de nieuwe stand in zijn eigen
        # query-string; die is verser dan de URL waar de gebruiker vandaan komt.
        params.update(dict(request.query_params))
        return params
    return dict(request.query_params)


# Hoeveel rijen er op een pagina passen (#1083). Eén bron: de route toetst
# hiertegen en de keuzelijst in de meta-regel wordt hieruit gevuld. Stonden de
# waarden op twee plaatsen, dan kon je een optie kiezen die de server weigert —
# en dan valt hij stil terug op 50, wat leest als een kapotte keuzelijst.
PER_PAGE_OPTIONS = (25, 50, 100)
PER_PAGE_DEFAULT = 50


def per_page_from(value) -> int:
    """De gekozen paginagrootte uit de querystring, of de standaard.

    Whitelist en geen `min/max`: alles wat uit een URL komt is invoer, en een
    `per_page=100000` zou hier anders een pagina van honderdduizend rijen worden.
    """
    try:
        gekozen = int(value)
    except (TypeError, ValueError):
        return PER_PAGE_DEFAULT
    return gekozen if gekozen in PER_PAGE_OPTIONS else PER_PAGE_DEFAULT


def sort_description(column_label: str, direction: str, is_date: bool = False) -> str:
    """De actieve sortering in woorden, voor de meta-regel boven een tabel (#1083).

    §2.3 vraagt die regel bij een sorteerbare lijst: welke rij bovenaan staat en
    waarom, zonder de kolomkoppen af te gaan. Hier en niet per scherm, want de
    twee schermen die hem vandaag vragen zouden hem elk net anders formuleren —
    en het derde zou dat weer anders doen.

    Een datumkolom krijgt "nieuwste/oudste eerst": dát is wat iemand van een
    logboek wil weten, en "op Datum, aflopend" zegt hetzelfde met meer moeite.
    """
    from app.i18n import _

    if is_date:
        return _("nieuwste eerst") if direction == "desc" else _("oudste eerst")
    sjabloon = _("op %(kolom)s, aflopend") if direction == "desc" else _("op %(kolom)s, oplopend")
    return sjabloon % {"kolom": column_label}


@functools.cache
def _right_of_screen() -> dict[str, object]:
    """The address of every screen a gate guards → the right that gate asks,
    read from the running routes (`require_right` leaves it on its gate). The
    menu asks this instead of keeping a list of its own beside the routes."""
    from app.main import app  # lazy: `app.main` imports this module

    found: dict[str, object] = {}

    def walk(items, prefix: str = "") -> None:
        for item in items:
            context = getattr(item, "include_context", None)
            if context is not None:
                walk(item.original_router.routes, prefix + (context.prefix or ""))
            elif "GET" in (getattr(item, "methods", None) or ()) and hasattr(item, "dependant"):
                for dependency in item.dependant.dependencies:
                    right = getattr(dependency.call, "right", None)
                    if right is not None:
                        found[prefix + item.path] = right

    walk(app.routes)
    return found


def nav_for(active: str, rights, modules=None) -> list[dict]:
    """The navigation groups of the admin shell for someone who holds `rights`;
    `active` is the address of the screen.

    Per work area since #913: [{"label": ..|None, "items": [...]}].

    By right (CR-24): an item is shown when the viewer holds the right its
    screen asks — the right of that screen's own gate, so a link that would
    answer "no access" is never offered, and a screen that asks no right is not
    in the menu at all. One rule for everyone: until CR-24 a user without the
    general set of roles got one hand-made group with Betalingen alone.

    Module-aware (CR-19, #1476): an item of a module that is off for this
    tenant is left out (`kernel.modules.nav_item_shown`), and a group left
    empty goes with it. `modules` is the enabled set; by default the one of
    this request. So this is called per request — a constant computed at
    import time would freeze the menu of no tenant at all."""
    from app.domains.mdm.api import current_enabled_modules
    from app.i18n import _
    from app.kernel.modules import nav_item_shown

    enabled = modules if modules is not None else current_enabled_modules()
    hidden = TENANT_ONLY_ITEMS if _on_platform_workspace() else PLATFORM_ONLY_ITEMS
    asked = _right_of_screen()
    groepen = [
        (
            label,
            [
                (h, lbl)
                for h, lbl in items
                if h not in hidden
                and nav_item_shown("admin_items", h, enabled)
                and asked.get(h) in rights
            ],
        )
        for label, items in _ADMIN_NAV_GROEPEN
    ]
    return [
        {
            "label": _(label) if label else None,
            # #1526: the untranslated label names the group in the browser's
            # memory of what is folded; a translation must not forget it.
            "key": label,
            "items": [
                {
                    "href": href,
                    "label": _(lbl),
                    "active": href == active,
                    "icon": _ADMIN_NAV_ICONS[href],
                }
                for href, lbl in items
            ],
        }
        for label, items in groepen
        if items
    ]


def admin_nav(active: str, request, modules=None) -> list[dict]:
    """The menu for whoever this request's gate let in: the rights that gate
    read (`request.state.rights`), so the menu costs no question of its own. A
    request no gate has seen holds none, and its menu is empty."""
    return nav_for(active, getattr(request.state, "rights", frozenset()), modules)


def _current_user(db, request) -> dict | None:
    """Ingelogde gebruiker uit de sessie-cookie (#467): naam + admin_home, of None.
    Mag het renderen nooit breken."""
    if request is None:
        return None
    try:
        from app.domains.auth.api import (
            SESSION_COOKIE,
            back_office_home,
            has_household,
            login_person_for_email,
            read_session_value,
        )

        email = read_session_value(request.cookies.get(SESSION_COOKIE))
        if not email:
            return None
        naam = email
        voornaam = email.split("@")[0]
        person = login_person_for_email(db, email)
        if person is not None:
            naam = f"{person.first_name} {person.last_name}".strip() or email
            voornaam = (person.first_name or "").strip() or naam
        return {
            "email": email,
            "naam": naam,
            # #1588: the header's account button says the first name; the menu
            # and the drawer the full one.
            "voornaam": voornaam,
            # The way into the back office for whoever has one (#1499, #1740):
            # the workbench, for everyone with a back-office role (CR-24 Q13,
            # Q16); None for everyone else. Asked of the auth domain — after
            # signing in on the site nobody lands there by himself any more,
            # so the menu is the way.
            "admin_home": back_office_home(db, email),
            "is_member": person is not None,
            # CR-22 (#1707): an account is a person too, so "there is a person"
            # no longer means "there is a household" — Mijn gezin asks this.
            "has_household": has_household(person),
        }
    except Exception:
        return None


def _site_logo_url(db) -> str | None:
    """De URL van het verenigingslogo, of None. Mag het renderen nooit breken."""
    try:
        from app.domains.media.api import media_url, tenant_logo

        asset = tenant_logo(db)
        return media_url(asset.id) if asset is not None else None
    except Exception:
        return None


def _footer_organisatie(db, organisatie) -> dict | None:
    """Het organisatieblok in de footer (#924), of None als er niets te tonen is.

    Naam, adres en contact van de vereniging zelf. Tot nu stond dat als vrije
    tekst in een CMS-pagina; nu komt het uit de entiteit, en het CMS-blok blijft
    eronder staan zodat er bij de deploy niets verdwijnt.

    Geeft None terug als er niets ingevuld is: een leeg blok met alleen een naam
    erin ziet eruit als een renderfout, en de footer heeft al een naam onderaan.
    """
    if organisatie is None:
        return None
    from app.domains.mdm.api import Address, BankAccount, ContactDetail

    adres = (
        db.query(Address)
        .filter(Address.organization_id == organisatie.id, Address.deleted_at.is_(None))
        .execution_options(include_all_tenants=True)
        .one_or_none()
    )
    regels: list[str] = []
    gemeente = None
    if adres is not None:
        bus = f" bus {adres.bus_number}" if adres.bus_number else ""
        regels.append(f"{adres.street} {adres.house_number}{bus}")
        if adres.postal_code is not None:
            regels.append(f"{adres.postal_code.postal_code} {adres.postal_code.municipality}")
            gemeente = adres.postal_code.municipality
    # `include_all_tenants=True`: `tenant_id` is op een organisatierij niet de
    # scope (zie `ContactDetail`), dus de gewone filter zou hier het verkeerde
    # antwoord geven in plaats van geen.
    # Keyed on the CODE: the callers below look up with "EMAIL" and "PHONE".
    # The column holds the plain code (contact types have no enum, see
    # `mdm.codes.CONTACT`); `code_of` keeps this correct whichever it holds.
    from app.kernel.codes import code_of as _code_of

    contacten = {
        _code_of(c.contact_type_code): c.value
        for c in db.query(ContactDetail)
        .filter(ContactDetail.organization_id == organisatie.id, ContactDetail.deleted_at.is_(None))
        .execution_options(include_all_tenants=True)
        .all()
    }
    # De eerste rekening: `sort_order` bepaalt welke er getoond wordt zodra er
    # meer dan één is (#945).
    rekening = (
        db.query(BankAccount)
        .filter(BankAccount.organization_id == organisatie.id, BankAccount.deleted_at.is_(None))
        .order_by(BankAccount.sort_order, BankAccount.id)
        .execution_options(include_all_tenants=True)
        .first()
    )
    blok = {
        "name": organisatie.name,
        "address_lines": regels,
        # #1588: the town, for the footer's "Nieuws uit <plaats>".
        "municipality": gemeente,
        "email": contacten.get("EMAIL") or None,
        "phone": contacten.get("PHONE") or None,
        "iban": (rekening.iban if rekening else None) or None,
        "bic": (rekening.bic if rekening else None) or None,
    }
    heeft_inhoud = regels or blok["email"] or blok["phone"] or blok["iban"] or blok["bic"]
    return blok if heeft_inhoud else None


def legal_parts(organisation: dict | None) -> list[dict]:
    """What the footer's legal line says about the organisation after "© year
    name" (CR-11 pilot B, #1588; end state §2.5): the address on one line, the
    e-mail address, the phone number, the account number — each only when it is
    filled in, so a missing one leaves no empty separator, and each ONCE (the
    footer has no separate contact block any more).

    One source: the organisation the site shows (`_footer_organisatie`, #1550).
    `kind` names the part for the template and the tests; `href` makes the
    e-mail address and the phone number links."""
    if not organisation:
        return []
    parts: list[dict] = []
    if organisation["address_lines"]:
        parts.append({"kind": "address", "text": ", ".join(organisation["address_lines"])})
    if organisation["email"]:
        parts.append(
            {
                "kind": "email",
                "text": organisation["email"],
                "href": f"mailto:{organisation['email']}",
            }
        )
    if organisation["phone"]:
        parts.append(
            {
                "kind": "phone",
                "text": readable_phone(organisation["phone"]),
                "href": "tel:"
                + "".join(c for c in organisation["phone"] if c.isdigit() or c == "+"),
            }
        )
    if organisation["iban"]:
        bic = f" ({organisation['bic']})" if organisation["bic"] else ""
        parts.append({"kind": "iban", "text": f"{organisation['iban']}{bic}"})
    return [{"href": None, **part} for part in parts]


def _externe_url(waarde: str) -> str | None:
    """De waarde als absolute http(s)-URL, of ``None`` als ze dat niet is.

    De tweede helft van #1160: een waarde zonder schema is voor de browser een
    RELATIEF pad, dus ``0470 12 34 56`` in een ``href`` wordt een link naar
    ``https://<ons domein>/0470 12 34 56``. Dat gold ook voor een echt netwerk
    met een verkeerd ingevulde waarde, dus de controle hangt aan de link en niet
    aan de soort. Geen gok naar wat iemand bedoelde: ``www.facebook.com/raak``
    krijgt er geen ``https://`` voor, want dan raadt de footer een adres.
    """
    from urllib.parse import urlsplit

    try:
        stuk = urlsplit((waarde or "").strip())
    except ValueError:  # een waarde die niet eens te ontleden valt
        return None
    if stuk.scheme in ("http", "https") and stuk.netloc:
        return waarde.strip()
    return None


def _sociale_links(db, organisatie) -> list[dict]:
    """De sociale links van de organisatie, in vaste volgorde (#945, #1160).

    **De bron zegt wat een netwerk is.** `contact_type_codes.is_social_network`
    draagt die beslissing; dit scherm houdt er geen lijst meer van bij. Tot #1160
    stond de regel omgekeerd — bekende codes eerst, en *alles wat de module niet
    kende* achteraan erbij — met een handgeschreven uitzonderingslijst
    ``{"EMAIL", "PHONE", "WEBSITE"}`` ernaast. Die lijst miste ``MOBILE``, dus het
    mobiele nummer van de vereniging stond als vierde icoon in de footer van elke
    publieke pagina. Een achtste contactsoort zou hetzelfde doen.

    De openheid van #945 blijft: een vijfde netwerk is nog altijd één rij in
    `contact_type_codes` (nu met ``is_social_network = true``) plus één rij in
    `contact_details` — geen kolom, geen sjabloonregel. Wat verdwijnt is de
    restcategorie, want "een code die ik niet ken" is geen netwerk maar een
    contactsoort die dit scherm nog niet kent.

    De volgorde komt van de CODE en niet uit de rij-inhoud: een footer waarin de
    iconen van plaats wisselen omdat iemand een waarde bewerkte, ziet er stuk uit.
    Alfabetisch op code is stabiel onder elke bewerking, en het is toevallig ook
    precies de volgorde die de oude vaste lijst had (FACEBOOK, INSTAGRAM, TIKTOK).
    """
    if organisatie is None:
        return []
    from app.domains.mdm.api import ContactDetail, ContactTypeCode

    # CR-12 phase 2: `is_social_network` still lives on the code table — it is
    # a property of the code (#1160) — but since the split the word next to it
    # comes from the label table, via `code_label()`.
    from app.kernel.codes import code_label, code_of

    netwerken = {
        c.code: code_label("contact_type", c.code)
        for c in db.query(ContactTypeCode)
        .filter(ContactTypeCode.is_social_network.is_(True))
        .execution_options(include_all_tenants=True)
        .all()
    }
    if not netwerken:
        return []
    # `code_of`: the column holds the plain code — contact types have no enum,
    # precisely so that a fifth social network is one row (#1160) — and
    # `code_of` returns it unchanged. Kept so this reads the same as every
    # other code lookup.
    rijen = {
        code_of(c.contact_type_code): c.value
        for c in db.query(ContactDetail)
        .filter(
            ContactDetail.organization_id == organisatie.id,
            ContactDetail.contact_type_code.in_(list(netwerken)),
            ContactDetail.deleted_at.is_(None),
        )
        .execution_options(include_all_tenants=True)
        .all()
    }
    links = []
    for code in sorted(netwerken):
        url = _externe_url(rijen.get(code) or "")
        if url:
            links.append({"code": code, "label": netwerken[code] or code.title(), "url": url})
    return links


#: Where a public link lands when that is not its own path: /archief is a
#: redirect to /activiteiten/archief (#405-e), and `navlink` underlines the
#: link on the page it lands on.
_PUBLIC_NAV_LANDS_ON = {"/archief": "/activiteiten/archief"}


def _public_nav(field: str) -> list[dict]:
    """The site shell's links of one registry field, for this request (#1476)."""
    from app.domains.mdm.api import current_enabled_modules
    from app.i18n import _
    from app.kernel.modules import MODULES, nav_item_shown

    enabled = current_enabled_modules()
    return [
        {
            "href": item[0],
            "label": _(item[1]),
            "match": _PUBLIC_NAV_LANDS_ON.get(item[0]),
            # Only an account-menu item brings an icon (CR-22 Q38).
            "icon": item[2] if len(item) > 2 else None,
        }
        for module in MODULES
        for item in getattr(module, field)
        if nav_item_shown(field, item[0], enabled)
    ]


#: Mijn gezin, the one item of the account menu that needs a household.
HOUSEHOLD_HOME = "/leden/gezin"


def account_nav(db, *, household: bool = True) -> list[dict]:
    """The account menu of the public site (CR-22 S3, #1706; R14): ONE list for
    the header's menu, the drawer and the menu on the account pages. Its first
    item is the landing page, called "Mijn " + the site's name (Q32, Q35); the
    rest comes from the modules' `member_items`, each with its own icon.

    `household` (#1707): whether the signed-in person is in one. Mijn gezin is
    listed only then — an account has no household, and the item would open a
    page that sends him back (R14: "what applies to him")."""
    from app.i18n import _
    from app.kernel.tenant_config import tenant_display_name

    home = {
        "href": "/mijn",
        "label": _("Mijn %(site)s") % {"site": tenant_display_name(db)},
        "match": None,
        "icon": "house",
    }
    # Mijn gegevens (CR-22 S6a, #1710): always there — everyone with an account
    # page is a person.
    details = {
        "href": "/mijn/gegevens",
        "label": _("Mijn gegevens"),
        "match": None,
        "icon": "user",
    }
    # The order of the menu is its own (CR-22 A3): Mijn gezin before Mijn
    # inschrijvingen, whatever order the registry lists the modules in; an item
    # this list does not name yet (Mijn aankopen, CR-21) comes after them.
    order = {HOUSEHOLD_HOME: 0, "/mijn/inschrijvingen": 1}
    modules = sorted(_public_nav("member_items"), key=lambda n: order.get(n["href"], len(order)))
    if not household:
        modules = [item for item in modules if item["href"] != HOUSEHOLD_HOME]
    return [home, details, *modules]


def site_context(db, request=None) -> dict:
    """Gedeelde context van de SiteShell (site_base.html): navigatie-pagina's,
    de voet (nieuwsbrief, sociale links, sponsors, de juridische regel). Eén
    plek, elke publieke route neemt hem mee."""
    from datetime import date

    from app.domains.auth.api import csrf_from_request
    from app.domains.cms.api import CmsPage
    from app.domains.mdm.api import Organization, OrganizationType, TenantKind, module_enabled
    from app.domains.media.api import MediaAsset, MediaKind, media_url
    from app.i18n import _
    from app.kernel.modules import ModuleCode
    from app.kernel.tenant_config import _actieve_tenant, tenant_public_chat_enabled

    # Dezelfde tenantresolutie als de rest van de configuratie (#924): buiten een
    # verzoek — een script, een test — is er geen context, en dan hoort de
    # standaardtenant te gelden in plaats van "geen organisatie".
    organisatie = (
        db.query(Organization)
        .filter(Organization.id == _actieve_tenant(None))
        .execution_options(include_all_tenants=True)
        .one_or_none()
    )
    # #1550: whose data the site shows. The tenant's kind stays the tenant's own
    # (wordmark, sponsor heading); the footer and its links show this one.
    from app.kernel.tenant_config import site_organization_id

    bron_id = site_organization_id(db)
    bron = (
        organisatie
        if organisatie is not None and organisatie.id == bron_id
        else db.query(Organization)
        .filter(Organization.id == bron_id)
        .execution_options(include_all_tenants=True)
        .one_or_none()
    )

    pages = (
        db.query(CmsPage)
        .filter(
            CmsPage.is_published == True,  # noqa: E712
            CmsPage.show_in_nav == True,
        )  # noqa: E712  (#465)
        .order_by(CmsPage.sort_order.asc(), CmsPage.title.asc())
        .all()
    )
    # #1569: the pages that say themselves that they stand in the footer. One
    # list for the footer and for the newsletter form's small print.
    footer_pages = (
        db.query(CmsPage)
        .filter(CmsPage.is_published.is_(True), CmsPage.show_in_footer.is_(True))
        .order_by(CmsPage.sort_order.asc(), CmsPage.title.asc())
        .all()
    )
    # CR-11 pilot B (#1588): the free CMS block `site-footer` is no longer
    # rendered — the footer's legal line carries the organisation's details from
    # the entity, one source. The block stays as data until it is removed in the
    # back office.
    footer_organisation = _footer_organisatie(db, bron)
    # #1057: de footer toont alleen de logo's die daarvoor aangevinkt zijn. De
    # Design Studio blijft élk actief sponsorlogo aanbieden — dat is met opzet: een
    # logo dat niet in de footer hoort, hoort daarom nog niet van de affiche geweerd.
    sponsors = (
        db.query(MediaAsset)
        .filter(
            MediaAsset.kind == MediaKind.SPONSOR,
            MediaAsset.is_active == True,  # noqa: E712
            MediaAsset.show_in_footer == True,
        )  # noqa: E712
        .order_by(MediaAsset.sort_order, MediaAsset.id)
        .all()
    )
    from app.config import settings
    from app.kernel.tenant_config import (
        get_setting,
        site_color_style,
        site_name_default,
        tenant_display_name,
        tenant_site_header_color,
        umami_tracking,
    )

    base_url = (get_setting(db, "base_url") or "").rstrip("/")
    # #808: sinds de React-exit (#405) werd het trackingscript NERGENS meer
    # gerenderd — `Analytics.tsx` verdween zonder Jinja-vervanger. Gemeten in de
    # Umami-databank van PROD: laatste bezoek 9 september 17:41 UTC, 33 bezoeken die
    # dag daarvóór, nul erna. Dat uur is precies de omschakeling van `prod-frontend`
    # naar `prod-backend`.
    umami_src, umami_website_id = umami_tracking(db)
    user = _current_user(db, request)

    return {
        "nav_pages": pages,
        "footer_pages": footer_pages,
        # CR-19 (#1476): the module links of the header, from the registry —
        # what a module that is off lists or serves is not there.
        "public_nav": _public_nav("public_items"),
        "member_nav": account_nav(db, household=bool(user and user["has_household"])),
        # CR-22 Q39: a company tenant has accounts and no members — the hint above
        # the registration form words itself by it.
        "has_members": module_enabled(ModuleCode.MEMBERSHIP),
        # #1588: the legal line's parts. (The newsletter column's heading is
        # the word "Nieuwsbrief" in the shell since #1647; "Nieuws van <the
        # site's name>" of #1606 is gone, with its key here.)
        "legal_parts": legal_parts(footer_organisation),
        # #1616 (Koen, 5 October 2026): the legal line names the ORGANISATION
        # behind the site (#1550), not the site — the address and the numbers
        # after it are that organisation's. Everything else that names the site
        # keeps `site_name` (#1546).
        "legal_name": site_name_default(db),
        # #1473: the address comes from media; the footer writes none itself.
        "sponsors": [
            {"title": s.title, "link_url": s.link_url, "url": media_url(s.id)} for s in sponsors
        ],
        "current_year": date.today().year,
        # CR-19 (#1477): and only with the chatbot module on for this tenant —
        # the bubble would otherwise post to a route that answers 404. #1568: and
        # with the tenant's own switch for the public site on; one rule
        # (`tenant_public_chat_enabled`), which the chat endpoints read too.
        "chat_enabled": tenant_public_chat_enabled(db) and module_enabled(ModuleCode.CHATBOT),
        "stt_mode": settings.stt_mode,  # spraakinvoer in de widget (#567)
        # #1251: the longest question the public Raakje takes — the field's
        # `maxlength`, from the setting its route refuses above.
        "chat_max_input_chars": settings.chat_max_input_chars,
        "gebruiker": user,
        # Branding per tenant (#407/#519): naam/tagline/Facebook uit de
        # tenant-config. GEEN Millegem-specifieke defaults meer — die lekten
        # naar andere tenants (multi-tenancy-fout). Leeg = niet tonen, net als
        # Instagram/TikTok/privacy (#493): elke tenant zet zijn eigen waarden.
        # Open Graph per PAGINA (#881), met de sitewaarden als terugval. Altijd
        # aanwezig en niet via `|default()`: de sjablonen renderen onder
        # StrictUndefined, en een ontbrekende naam hoort daar te falen in plaats van
        # leeg te renderen. Een pagina die niets overschrijft krijgt exact de tags
        # die ze vandaag heeft.
        #
        # Waarom dit nodig was: titel en omschrijving kwamen van de SITE, dus wie een
        # album deelde las de naam van de vereniging in plaats van die van het album —
        # en er was helemaal geen `og:image`, dus nooit een beeld.
        "og_title": None,
        "og_description": None,
        "og_image": None,
        "site_name": tenant_display_name(db),
        "site_tagline": get_setting(db, "tagline") or "",
        # #992: the public header's own colour, or None for the shell's.
        # Validated again on read, so it can go into a style attribute.
        "site_header_color": tenant_site_header_color(db),
        # #1622: the tokens of the tenant's own brand and accent colour, for
        # the body's style; "" = the stylesheet's palette.
        "site_color_style": site_color_style(db),
        # Het logo van de vereniging (#258), als het er is: de header toont het
        # in plaats van het ingetypte woordmerk, en de vergader-PDF gebruikt
        # hetzelfde logo. Eén bron, twee afnemers — daarom staat het bij de
        # media en niet in de vergadermodule. Als URL en niet als bytes: de
        # browser haalt het gewoon op, en de mediaroute cachet het al.
        "site_logo_url": _site_logo_url(db),
        # CR-19 (#1496): what the header shows without a logo. A company shows
        # its own name. #1588: an association shows its name too (the typed
        # RaaK wordmark left with decision 11), so None only says "no name of
        # its own" and the template falls back on `site_name`.
        # #1543: the platform too shows its own name — it is in the site shell
        # since its home became a page, and it carries no Raak brand (#821).
        "site_wordmark": (
            tenant_display_name(db)
            if organisatie is not None
            and organisatie.kind in (TenantKind.COMPANY, TenantKind.PLATFORM)
            else None
        ),
        # #924: de sociale links komen uit de ORGANISATIE en niet meer uit de
        # tenant-instellingen. Een Facebook-pagina van een vereniging bestaat
        # los van haar site — de beslisregel uit het issue. Enkel tonen als
        # gezet; er is geen zinvolle default.
        # #945: en ze zijn een lijst geworden. Drie contextsleutels werden er
        # één, want drie sleutels zijn drie sjabloonregels en dus precies de
        # kolom-per-netwerk die dit issue opruimt.
        "sociale_links": _sociale_links(db, bron),
        # The organisation's details (#924). The footer shows them in its legal
        # line (`legal_parts`, #1588); a CMS page may show them as a contact
        # block. The free `site-footer` block is no longer rendered.
        "organisatie": footer_organisation,
        # The newsletter's call, in the footer's row since #1588 (it was a link
        # at the bottom of the home page, #984). Not on the platform: it has no
        # members and sends no newsletter.
        # CR-19 C6 test 11: the member, not the string. `org_type` is a CodeEnum,
        # which never equals "PLATFORM", so the platform showed the link too.
        # CR-19 (#1477): and only with the newsletter module on.
        "nieuwsbrief_inschrijven": (
            organisatie is not None
            and organisatie.org_type is not OrganizationType.PLATFORM
            and module_enabled(ModuleCode.NEWSLETTER)
        ),
        # CR-19 (#1477): what the line above the sponsor logos says. A company
        # has partners; an association keeps the words it has always had.
        "sponsors_kop": (
            _("Partners")
            if organisatie is not None and organisatie.kind is TenantKind.COMPANY
            else _("Met steun van")
        ),
        # SEO (#454): canonieke origin + huidige canonical-URL voor OG/canonical.
        "base_url": base_url,
        # Webstatistieken (#176/#808). Beide of geen van beide — zie
        # `umami_tracking`. Alleen de PUBLIEKE schil draagt het script:
        # beheerverkeer is geen bezoek en zou de cijfers vervuilen.
        "umami_src": umami_src,
        "umami_website_id": umami_website_id,
        # #693: élke publieke pagina draagt het CSRF-token. Dit was de
        # eigenlijke oorzaak van de 403's onder #649/#662, en het lag niet aan
        # een verlopen sessie: het token staat in `hx-headers` op de <body> van
        # de schil, en bij een hx-boost-navigatie vervangt htmx de INHOUD van de
        # body, niet haar ATTRIBUTEN. Landde je via een publieke pagina zonder
        # token (`{{ csrf_token|default("") }}` → lege string) en boostte je
        # daarna naar /leden/gezin, dan bleef die lege waarde staan en stuurde
        # elke mutatie een leeg token mee.
        #
        # Herladen hielp, want dat is een harde navigatie — vandaar dat het
        # advies in de melding klopte terwijl de verklaring erin niet klopte.
        #
        # De reparatie hoort hier en niet in de JS: is het token overal correct,
        # dan maakt het niet meer uit welke pagina de body-attributen leverde.
        "csrf_token": csrf_from_request(request) if request is not None else "",
        "canonical_url": (base_url + request.url.path) if (base_url and request) else None,
    }
