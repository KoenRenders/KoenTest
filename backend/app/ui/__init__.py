"""UI-fundament (#396/#398, §21): Jinja-templates + htmx/Alpine, server-rendered.

Elke component levert zijn schermen als ``ui.py`` (routes: view-model bouwen,
template kiezen) + ``templates/`` (dom: alleen tonen). Dit pakket levert de
gedeelde machinerie: de template-omgeving (met de component-template-mappen),
de UI-kit-macro's en de shells (base-layouts).
"""
import hashlib
import logging
from functools import lru_cache
from pathlib import Path

from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader, StrictUndefined, Undefined
from jinja2 import make_logging_undefined

from app.config import settings

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
    StrictUndefined if settings.app_env in _STRICT_ENVS
    else make_logging_undefined(logger=logging.getLogger("app.ui.undefined"),
                                base=Undefined)
)

# LET OP — `autoescape=True` is hier XSS-kritisch. Starlette zet autoescape zelf
# wanneer je `directory=` meegeeft, maar NIET wanneer je een eigen `env=`
# meegeeft: dan is het jouw environment en jouw verantwoordelijkheid. Zonder deze
# regel gaat élke `{{ }}` ongeëscapet naar de browser. De lint-gate bewaakt dat
# de regel hier letterlijk blijft staan.
_env = Environment(loader=FileSystemLoader(template_dirs), undefined=_undefined,
                   autoescape=True)

templates = Jinja2Templates(env=_env)

# Taalbeleid (#407-T): {{ _("...") }} beschikbaar in alle templates, volgend
# op de actieve tenant-taal.
from app.i18n import install_jinja_i18n  # noqa: E402

install_jinja_i18n(templates.env)


def _langedatum(d) -> str:
    """Lange Nederlandse datum, bv. 'zaterdag 29 augustus 2026' (#451)."""
    if d is None:
        return ""
    from babel.dates import format_date
    from app.i18n import current_locale

    return format_date(d, format="full", locale=current_locale.get())


templates.env.filters["langedatum"] = _langedatum


# Geldbedragen in nl-BE-notatie (#735): `{{ bedrag|geld }}` → "35,00". Het euroteken
# staat in de sjablonen, zodat de opmaak eromheen (kleur, uitlijning) daar blijft.
from app.kernel.geld import bedrag as _bedrag  # noqa: E402

templates.env.filters["geld"] = _bedrag


# Een meetwaarde per opmaaksoort (#875): `{{ waarde|meetwaarde(c.format) }}`. Eén
# plek voor alle vijf de soorten die de universe declareert — het paneel kende er
# één en drukte de rest rauw af, met `0E-20` als resultaat.
from app.kernel.meetwaarden import meetwaarde as _meetwaarde  # noqa: E402

templates.env.filters["meetwaarde"] = _meetwaarde


# Relatietype leesbaar tonen (#476): ruwe code → label i.p.v. "HOOFDLID".
_RELATIE_LABELS = {"HOOFDLID": "Hoofdlid", "PARTNER": "Partner",
                   "KIND": "(meerderjarig) kind"}


def _relatielabel(code) -> str:
    return _RELATIE_LABELS.get(code or "", code or "—")


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
    return (f"data-confirm='{escape(type_label)} \"{escape(name)}\" "
            f"{escape(_('definitief verwijderen?'))}'")


templates.env.globals["confirm_attrs"] = _confirm_attrs


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

# Omgevings-indicator (#464): [HDEV]/[UAT] in titel + gekleurde band. Als globale
# beschikbaar in álle templates (publiek + admin); PROD blijft schoon.
from app.config import settings as _settings  # noqa: E402

templates.env.globals["omgeving"] = _settings.app_env


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


templates.env.globals["statisch"] = statisch

# Canonieke admin-navigatie (React-exit 405-d, #405): één bron voor alle
# server-rendered beheer-schermen i.p.v. een kopie per module.
_ADMIN_NAV: list[tuple[str, str]] = [
    ("/admin/werkbank", "Werkbank"),
    ("/admin/activiteiten", "Activiteiten"),
    ("/admin/leden", "Leden"),
    ("/admin/betalingen", "Betalingen"),
    ("/admin/rapporten", "Rapporten"),
    ("/admin/formulieren", "Formulieren"),
    ("/admin/paginas", "Pagina's"),
    ("/admin/media", "Media"),
    ("/admin/gebruikers", "Gebruikers"),
    ("/admin/ledenwijzigingen", "Wijzigingen"),
    ("/admin/ai-context", "Raakje"),
    ("/admin/e-maillog", "E-maillog"),
    ("/admin/tenants", "Tenants"),
    ("/admin/design-system", "Design system"),
    ("/admin/info", "Info"),
]


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


def admin_nav(active: str, roles=None) -> list[dict]:
    """Navigatie-items voor de AdminShell; `active` is de href van het scherm.

    Role-aware (#530): een FINANCE-only gebruiker (geen ADMIN/OPERATOR) mag enkel de
    betalingen-schermen openen — toon dan enkel Betalingen, zodat de nav niet vol
    links staat die 403'en. ADMIN/OPERATOR (of geen `roles` meegegeven) zien alles."""
    from app.i18n import _

    items = _ADMIN_NAV
    if roles is not None and not ({"ADMIN", "OPERATOR"} & set(roles)):
        items = [(h, l) for h, l in _ADMIN_NAV if h == "/admin/betalingen"]
    return [{"href": href, "label": _(label), "active": href == active}
            for href, label in items]


def _huidige_gebruiker(db, request) -> dict | None:
    """Ingelogde gebruiker uit de sessie-cookie (#467): naam + is_admin, of None.
    Mag het renderen nooit breken."""
    if request is None:
        return None
    try:
        from app.domains.auth.api import (
            SESSION_COOKIE, get_user_roles, login_person_for_email, read_session_value)

        email = read_session_value(request.cookies.get(SESSION_COOKIE))
        if not email:
            return None
        naam = email
        person = login_person_for_email(db, email)
        if person is not None:
            naam = f"{person.first_name} {person.last_name}".strip() or email
        return {"email": email, "naam": naam,
                "is_admin": "ADMIN" in get_user_roles(db, email),
                "is_member": person is not None}
    except Exception:
        return None


def site_context(db, request=None) -> dict:
    """Gedeelde context van de SiteShell (site_base.html): navigatie-pagina's,
    footer-blok en sponsors. Eén plek, elke publieke route neemt hem mee."""
    from datetime import date

    from app.domains.auth.api import csrf_from_request
    from app.domains.cms.api import CmsPage, render_cms_content
    from app.domains.media.api import MediaAsset

    pages = (db.query(CmsPage)
             .filter(CmsPage.is_published == True,        # noqa: E712
                     CmsPage.show_in_nav == True)         # noqa: E712  (#465)
             .order_by(CmsPage.sort_order.asc(), CmsPage.title.asc()).all())
    # #727: via de domeinfacade en niet met een eigen query — die keek langs
    # `is_published` heen, dus de footer stond op elke publieke pagina terwijl het
    # beheerscherm hem als niet-gepubliceerd toonde.
    from app.domains.cms.api import get_published_page

    footer = get_published_page(db, "site-footer")
    footer_block = None
    if footer is not None:
        footer_block = {"content": render_cms_content(footer.content or "")}
    sponsors = (db.query(MediaAsset)
                .filter(MediaAsset.kind == "sponsor", MediaAsset.is_active == True)  # noqa: E712
                .order_by(MediaAsset.sort_order, MediaAsset.id).all())
    from app.kernel.tenant_config import (get_setting, tenant_display_name,
                                          umami_tracking)
    from app.config import settings

    base_url = (get_setting(db, "base_url") or "").rstrip("/")
    # #808: sinds de React-exit (#405) werd het trackingscript NERGENS meer
    # gerenderd — `Analytics.tsx` verdween zonder Jinja-vervanger. Gemeten in de
    # Umami-databank van PROD: laatste bezoek 9 september 17:41 UTC, 33 bezoeken die
    # dag daarvóór, nul erna. Dat uur is precies de omschakeling van `prod-frontend`
    # naar `prod-backend`.
    umami_src, umami_website_id = umami_tracking(db)

    return {"nav_pages": pages, "footer_block": footer_block,
            "sponsors": sponsors, "current_year": date.today().year,
            "chat_enabled": settings.chat_enabled,
            "stt_mode": settings.stt_mode,   # spraakinvoer in de widget (#567)
            "gebruiker": _huidige_gebruiker(db, request),
            # Branding per tenant (#407/#519): naam/tagline/Facebook uit de
            # tenant-config. GEEN Millegem-specifieke defaults meer — die lekten
            # naar andere tenants (multi-tenancy-fout). Leeg = niet tonen, net als
            # Instagram/TikTok/privacy (#493): elke tenant zet zijn eigen waarden.
            "site_name": tenant_display_name(db),
            "site_tagline": get_setting(db, "tagline") or "",
            "facebook_url": get_setting(db, "facebook_url") or None,
            # Instagram/TikTok hebben geen zinvolle default → enkel tonen als gezet.
            "instagram_url": get_setting(db, "instagram_url") or None,
            "tiktok_url": get_setting(db, "tiktok_url") or None,
            # Privacyverklaring-link per tenant (#493, raakt #453): leeg = niet tonen.
            "privacy_url": get_setting(db, "privacy_url") or None,
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
            "canonical_url": (base_url + request.url.path) if (base_url and request) else None}
