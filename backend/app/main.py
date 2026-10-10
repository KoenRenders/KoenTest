import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs

from fastapi import Depends, FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import soft_delete  # noqa: F401 - registreert de globale soft-delete-filter
from app.config import settings
from app.domains.activities.account_ui import router as activities_account_ui_router
from app.domains.activities.admin_ui import router as activities_admin_ui_router
from app.domains.activities.ui import router as activities_ui_router
from app.domains.auth.admin_ui import router as auth_admin_ui_router
from app.domains.auth.handlers import (  # noqa: F401 - event subscriptions (#1711)
    send_address_code,
)
from app.domains.auth.ui import router as auth_ui_router
from app.domains.chatbot.admin_ui import router as chatbot_admin_ui_router
from app.domains.chatbot.handlers import (  # noqa: F401 - event subscriptions (#1251)
    keep_text_of_document,
)
from app.domains.chatbot.stt.router import router as stt_router
from app.domains.chatbot.ui import router as chatbot_ui_router
from app.domains.cms.admin_ui import router as cms_admin_ui_router
from app.domains.cms.handlers import (  # noqa: F401 - event subscriptions (#1478)
    seed_blocks_of_new_tenant,
)
from app.domains.cms.ui import router as cms_public_ui_router
from app.domains.designstudio.admin_ui import router as designstudio_admin_ui_router
from app.domains.designstudio.handlers import (
    copy_designs_of_copied_activity,  # noqa: F401 - event subscription (#1397)
    generate_image,  # noqa: F401 - registers the designstudio.generate job (#1007)
)
from app.domains.forms.admin_ui import router as forms_admin_ui_router
from app.domains.forms.handlers import (  # noqa: F401 - event subscriptions (#1509)
    seed_contact_form_of_new_tenant,
)
from app.domains.forms.ui import router as forms_ui_router
from app.domains.mail.handlers import (
    retry_mail,  # noqa: F401 - registreert de mail.retry-job (#399)
)
from app.domains.mail.ui import router as email_log_ui_router
from app.domains.mdm.account_ui import router as mdm_account_ui_router
from app.domains.mdm.api import EmailAddressInUse, EmailAddressInvalid
from app.domains.mdm.handlers import (  # noqa: F401 - event subscriptions (#1346)
    set_circle_start_when_chosen,
)
from app.domains.mdm.persons_ui import router as mdm_persons_ui_router
from app.domains.mdm.ui import router as mdm_ui_router
from app.domains.media.admin_ui import router as media_admin_ui_router
from app.domains.media.handlers import (  # noqa: F401 - its three ports and the extraction job (#1251)
    store_file,
)
from app.domains.media.router import router as media_router
from app.domains.media.ui import router as media_ui_router
from app.domains.meetings.admin_ui import router as meetings_admin_ui_router
from app.domains.membership.handlers import (  # noqa: F401 - event-abonnementen (CR-13 phase 2)
    activate_membership_on_payment,
)
from app.domains.membership.ui import router as membership_ui_router
from app.domains.newsletter.admin_ui import router as newsletter_admin_ui_router
from app.domains.newsletter.handlers import (
    send_newsletter,  # noqa: F401 - registreert de newsletter.send-job (#984)
)
from app.domains.newsletter.ui import router as newsletter_ui_router
from app.domains.payment.handlers import (  # noqa: F401 - event-abonnementen (CR-13 phase 1)
    reconcile_registration_on_order_change,
)
from app.domains.payment.router import router as payment_router
from app.domains.payment.stub_router import include_stub_routes
from app.domains.payment.ui import router as payment_ui_router
from app.domains.pricing.admin_ui import router as pricing_admin_ui_router
from app.domains.pricing.handlers import (  # noqa: F401 - event subscription (CR-21)
    drop_prices_of_deleted_product,
)
from app.domains.product.admin_ui import router as product_admin_ui_router
from app.domains.reporting.admin_ui import router as reporting_admin_ui_router
from app.domains.stock.admin_ui import router as stock_admin_ui_router
from app.domains.stock.handlers import (  # noqa: F401 - event subscription (CR-21)
    refuse_delete_with_movements,
)
from app.domains.workflow import (
    handlers as workflow_handlers,  # noqa: F401 - event-abonnementen (#398)
)
from app.domains.workflow.ui import router as workflow_ui_router
from app.kernel.modules import ModuleCode, require_module
from app.logging_config import configure_logging
from app.models import *  # noqa: F401, F403 - ensures all models are registered
from app.ui.account_ui import router as account_ui_router
from app.ui.changes_ui import router as changes_ui_router
from app.ui.design_system_ui import router as design_system_ui_router
from app.ui.organisaties_ui import router as organisaties_ui_router
from app.ui.system_ui import router as system_ui_router
from app.ui.tenants_ui import router as tenants_ui_router

configure_logging()

logger = logging.getLogger(__name__)

logger.info(
    "Starting Raak Millegem %s (%s) [omgeving=%s]",
    settings.app_version,
    settings.git_sha,
    settings.app_env,
)


def _docs_kwargs(app_env: str) -> dict:
    """Verberg de interactieve docs + het OpenAPI-schema in prod-achtige
    omgevingen (#269). Ze lekken geen data, maar publiceren wél de volledige
    API-kaart (alle admin-/finance-/member-endpoints + schema's) — onnodige
    verkenning voor een aanvaller. In dev/hdev/build blijven ze handig aanstaan."""
    if app_env in ("uat", "prod"):
        return {"docs_url": None, "redoc_url": None, "openapi_url": None}
    return {}


def cors_origins(app_env: str, frontend_url: str) -> list[str]:
    """Toegelaten CORS-origins (#271). De dev-uitzondering localhost:3000 hoort
    niet in prod-achtige omgevingen; daar enkel de echte frontend-URL."""
    origins = [frontend_url]
    if app_env not in ("uat", "prod"):
        origins.append("http://localhost:3000")
    return origins


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup-werk via de moderne lifespan-API (#407-O): kernel-jobs starten
    en de e-maillog opschonen. De oude on_event("startup")-hooks zijn weg."""
    _start_kernel_jobs()
    _purge_old_email_logs()
    yield


# What a payment is for is told by the domain that owns the payable (CR-21 Q48,
# #1748): each registers its describer here, beside the event subscribers above. A
# payable type without one is refused by `payment/tests/test_payable_describers.py`.
from app.domains.activities.api import registration_describer  # noqa: E402
from app.domains.membership.api import membership_describer  # noqa: E402
from app.domains.payment.api import PayableType, register_describer  # noqa: E402

register_describer(PayableType.REGISTRATION, registration_describer())
register_describer(PayableType.MEMBERSHIP, membership_describer())

app = FastAPI(
    lifespan=_lifespan,
    title="Raak Millegem API",
    description="API for the Raak Millegem community association",
    version="1.0.0",
    **_docs_kwargs(settings.app_env),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(settings.app_env, settings.frontend_url),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# CR-19 (#1475): each module's routers carry `require_module`, here at the
# include and not in the domain files (§C4.3) — one place says which router
# belongs to which module. A module that is off answers 404 for that tenant.
# The shell's own routers carry none and are listed once, below; the gate
# (`tests/test_module_gate.py`) holds that every include is one or the other.
M = ModuleCode


def _module(code: ModuleCode) -> list:
    return [Depends(require_module(code))]


#: Routers of the shell: login, account, system, tenants, users, changes, the
#: e-mail log; the public site core (home, sitemap, robots, CMS pages), which
#: every tenant has; the dictation used by screens of several modules.
SHELL_ROUTERS = (
    stt_router,
    auth_ui_router,
    auth_admin_ui_router,
    changes_ui_router,
    account_ui_router,
    mdm_account_ui_router,
    mdm_persons_ui_router,
    design_system_ui_router,
    system_ui_router,
    organisaties_ui_router,
    tenants_ui_router,
    email_log_ui_router,
    cms_public_ui_router,
    workflow_ui_router,
)

app.include_router(stt_router, prefix="/api/v1")
app.include_router(media_router, prefix="/api/v1", dependencies=_module(M.MEDIA))
app.include_router(forms_ui_router, dependencies=_module(M.FORMS))
app.include_router(forms_admin_ui_router, dependencies=_module(M.FORMS))
app.include_router(activities_ui_router, dependencies=_module(M.ACTIVITIES))
app.include_router(activities_account_ui_router, dependencies=_module(M.ACTIVITIES))
app.include_router(activities_admin_ui_router, dependencies=_module(M.ACTIVITIES))
app.include_router(chatbot_ui_router, dependencies=_module(M.CHATBOT))
app.include_router(chatbot_admin_ui_router, dependencies=_module(M.CHATBOT))
app.include_router(membership_ui_router, dependencies=_module(M.MEMBERSHIP))
app.include_router(auth_ui_router)
app.include_router(auth_admin_ui_router)
app.include_router(cms_admin_ui_router, dependencies=_module(M.CMS))
app.include_router(media_admin_ui_router, dependencies=_module(M.MEDIA))
# The public albums are the albums of activities (#1477): Media serves them, and
# without Activiteiten they are not found, as the menu item already was (#1476).
app.include_router(
    media_ui_router, dependencies=[Depends(require_module(M.MEDIA, also=(M.ACTIVITIES,)))]
)
app.include_router(changes_ui_router)
app.include_router(account_ui_router)
app.include_router(mdm_account_ui_router)
app.include_router(mdm_persons_ui_router)
app.include_router(design_system_ui_router)
app.include_router(system_ui_router)
app.include_router(organisaties_ui_router)
app.include_router(tenants_ui_router)
app.include_router(email_log_ui_router)
app.include_router(mdm_ui_router, dependencies=_module(M.MEMBERSHIP))
app.include_router(payment_ui_router, dependencies=_module(M.PAYMENT))
app.include_router(product_admin_ui_router, dependencies=_module(M.SHOP))
app.include_router(pricing_admin_ui_router, dependencies=_module(M.SHOP))
app.include_router(stock_admin_ui_router, dependencies=_module(M.SHOP))
app.include_router(reporting_admin_ui_router, dependencies=_module(M.REPORTING))
app.include_router(meetings_admin_ui_router, dependencies=_module(M.MEETINGS))
app.include_router(designstudio_admin_ui_router, dependencies=_module(M.DESIGNSTUDIO))
app.include_router(newsletter_admin_ui_router, dependencies=_module(M.NEWSLETTER))
app.include_router(newsletter_ui_router, dependencies=_module(M.NEWSLETTER))
app.include_router(workflow_ui_router)
app.include_router(payment_router, prefix="/api/v1", dependencies=_module(M.PAYMENT))


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> FileResponse:
    """Defined before the `/{slug}` catch-all below, which would answer 404.

    The browser asks for `/favicon.ico` by itself, with or without a link in the
    page (#1245) — every page load logged a 404 there. The shells link the
    versioned `/static/favicon.ico`; this answers the unasked request with the same
    file. Short cache on purpose: an icon fetched once sticks, so a changed one must
    be able to arrive.

    The icon is candidate B of #1245, chosen by Koen: the RaaK wordmark cropped
    square from the house-style logo and scaled, on the logo's own blue — nothing
    redrawn (CLAUDE.md, *Brand*)."""
    return FileResponse(
        Path(__file__).parent / "static" / "favicon.ico",
        media_type="image/x-icon",
        headers={"Cache-Control": "public, max-age=86400"},
    )


# #1274: the stub payment provider's pretend checkout page and webhook — only in
# development and the tests. Elsewhere these routes are never registered.
include_stub_routes(app, allowed=settings.payment_stub_allowed)
# LAATSTE: publieke site-kern — bevat de /{slug}-catch-all (#405)
app.include_router(cms_public_ui_router)


# Server-rendered UI (#396, §21): statics (CSS + gevendorde htmx/Alpine) komen
# rechtstreeks uit de backend; Caddy routeert /static/* hierheen.
class _StatischeBestanden(StaticFiles):
    """StaticFiles met een expliciete `Cache-Control` (#773).

    Zonder die header stuurt Starlette enkel een `ETag` en een `Last-Modified`, en dan
    beslist de browser zélf hoe lang hij het bestand vers vindt. Dat is precies hoe de
    fix uit #751 een uur lang niet bij de browser aankwam.

    De duur hangt af van de vraag of er een versie in de URL staat. `app.ui.statisch()`
    hangt er een inhoudshash aan, en zo'n adres wijzigt bij elke wijziging van het
    bestand — dat mag dus een jaar blijven staan. Een adres **zonder** versie is niet
    te onderscheiden van een oudere inhoud, en krijgt daarom vijf minuten: lang genoeg
    om een pagina met haar eigen plaatjes te laden, kort genoeg om een deploy niet
    urenlang te overleven.
    """

    def file_response(self, *args, **kwargs):
        response = super().file_response(*args, **kwargs)
        scope = args[2] if len(args) > 2 else kwargs.get("scope", {})
        query = parse_qs((scope.get("query_string") or b"").decode("latin-1"))
        response.headers["Cache-Control"] = (
            "public, max-age=31536000, immutable" if "v" in query else "public, max-age=300"
        )
        return response


app.mount(
    "/static", _StatischeBestanden(directory=str(Path(__file__).parent / "static")), name="static"
)


@app.middleware("http")
async def _tenant_context(request: Request, call_next):
    """Tenant-resolutie per request (§7, fase 5 #406): pad-prefix → hostname →
    tenant-cookie (platform-hosts) → default (Millegem). De contextvar stuurt
    zowel de globale ORM-filter als de default-tenant van nieuwe rijen. Een
    pad-prefix wordt gestript en verankerd in een cookie, zodat absolute
    vervolgnavigatie op dezelfde tenant blijft; noindex-tenants (demo) krijgen
    een X-Robots-Tag-header."""
    from app.domains.mdm.api import enabled_modules, platform_tenant_id, tenant_codes
    from app.kernel.modules import current_modules
    from app.kernel.tenancy import (
        DEFAULT_TENANT_ID,
        current_origin,
        current_platform_host,
        current_tenant_code,
        current_tenant_id,
        parse_hostname_map,
        resolve_request,
    )

    # Dynamische code→id-map uit de DB (#546): een nieuw aangemaakte tenant resolvet
    # zonder codewijziging. Gecachet, dus geen query-per-request na de eerste.
    codes = tenant_codes()
    platform_hosts = {h.strip().lower() for h in settings.platform_hosts.split(",") if h.strip()}
    tenant, nieuw_pad = resolve_request(
        request.headers.get("host"),
        request.url.path,
        request.cookies.get("raak_tenant"),
        parse_hostname_map(settings.tenant_hostnames),
        platform_hosts,
        codes,
        # #854: het platform is zelf een tenant, dus een platform-host heeft iets om
        # naar te resolven — op élk pad, niet alleen op "/". Even gecachet als de
        # codes; None zolang migratie 097 nog niet gelopen is.
        platform_tenant_id(),
    )
    if nieuw_pad is not None:
        request.scope["path"] = nieuw_pad
    from app.i18n import DEFAULT_LOCALE, current_locale

    taal = DEFAULT_LOCALE
    if tenant != DEFAULT_TENANT_ID:
        from app.database import SessionLocal
        from app.kernel.tenant_config import tenant_language

        _db = SessionLocal()
        try:
            taal = tenant_language(_db, tenant_id=tenant)
        finally:
            _db.close()
    # #860: absolute URL's horen terug te wijzen naar de host waarop je binnenkwam.
    # Het schema komt uit FRONTEND_URL en niet uit het verzoek — er staat geen
    # proxy-header-verwerking aan, dus achter Caddy leest elk verzoek als http. De
    # omgeving weet of ze https draait, het verzoek weet welke host.
    binnenkomende_host = (request.headers.get("host") or "").strip()
    schema = settings.frontend_url.split("://", 1)[0] if "://" in settings.frontend_url else "https"
    origin_token = current_origin.set(
        f"{schema}://{binnenkomende_host}" if binnenkomende_host else None
    )
    platform_token = current_platform_host.set(
        binnenkomende_host.split(":")[0].lower().removeprefix("www.") in platform_hosts
    )
    # De code van de actieve tenant, als ze er een heeft. De platform-tenant staat
    # niet in de code→id-map en heeft geen pad-prefix; dan blijft dit None.
    code_token = current_tenant_code.set(next((c for c, t in codes.items() if t == tenant), None))
    token = current_tenant_id.set(tenant)
    taal_token = current_locale.set(taal)
    # CR-19 (#1475): the tenant's module set, for `require_module` on the module
    # routers. Cached like the code map — no session and no query per request.
    modules_token = current_modules.set(enabled_modules(tenant))
    try:
        response = await call_next(request)
    finally:
        current_modules.reset(modules_token)
        current_locale.reset(taal_token)
        current_tenant_id.reset(token)
        current_tenant_code.reset(code_token)
        current_platform_host.reset(platform_token)
        current_origin.reset(origin_token)
    if nieuw_pad is not None:
        code = next(c for c, t in codes.items() if t == tenant)
        response.set_cookie("raak_tenant", code, httponly=True, samesite="lax")
    if tenant != DEFAULT_TENANT_ID:
        from app.database import SessionLocal
        from app.kernel.tenant_config import get_setting

        db = SessionLocal()
        try:
            if get_setting(db, "noindex", tenant_id=tenant) == "1":
                response.headers["X-Robots-Tag"] = "noindex, nofollow"
        finally:
            db.close()
    return response


@app.middleware("http")
async def _filter_push_url(request: Request, call_next):
    """Zet de filterstand in de browser-URL (#671).

    Een filterbalk vraagt haar lijst bij een fragment-route; vier van de elf balken
    doen dat op een eigen `…/lijst`-pad. `hx-push-url="true"` op de balk zou juist
    díé URL in de adresbalk duwen, en een F5 daarop geeft het kale fragment zonder
    schil. De balk merkt zich daarom met `X-Raak-Filter`, en hier zetten we het
    PAGINApad met dezelfde query — de server is de enige die beide kent.

    Drie dingen komen daarmee goed, en de derde is de reden dat #671 bestond:
    de filterstand overleeft een F5, een gefilterde lijst is deelbaar als link, en
    htmx stuurt de URL bij élk volgend verzoek mee als `HX-Current-URL` — ook bij
    een mutatie, die vroeger de ongefilterde lijst terugkreeg.

    Eén middleware in plaats van elf routes: een vergeten route is anders weer een
    scherm dat zijn filter kwijtraakt. `app.ui.filterparams()` leest hem uit.
    """
    response = await call_next(request)
    if request.headers.get("X-Raak-Filter") == "1" and response.status_code < 400:
        pad = request.url.path
        # De vier balken met een eigen fragment-route hangen onder hun pagina.
        if pad.endswith("/lijst"):
            pad = pad[: -len("/lijst")]
        query = request.url.query
        # A route that knows a better address has set it already (the embedded
        # Betalingen tab of a record, #1560).
        if "HX-Push-Url" not in response.headers:
            response.headers["HX-Push-Url"] = f"{pad}?{query}" if query else pad
    return response


@app.middleware("http")
async def _boosted_swap_headers(request: Request, call_next):
    """Vertel htmx hoe het een gebooste navigatie moet inswappen (#634).

    De schillen dragen `hx-boost="true"` op de <body>, zodat een klik op een link
    de pagina ophaalt i.p.v. de browser te laten herladen. Wat er dan geswapt moet
    worden — alleen `#main`, als outerHTML, met de scroll naar boven — staat
    BEWUST niet als `hx-target`/`hx-select`/`hx-swap` op diezelfde <body>.

    Die drie attributen zijn in htmx *inheritable*: htmx zoekt ze op met een
    closest()-lookup. Op de <body> zou dus élke htmx-actie in de app ze erven —
    ook de honderd `hx-post`-knoppen die een fragment terugkrijgen. Die zouden dan
    `#main` proberen te selecteren uit een antwoord dat alleen een lijstfragment
    bevat: niets om te swappen, dus een dode knop. Precies het soort stille breuk
    dat #613/#616 opleverde.

    De responsheaders HX-Retarget/HX-Reselect/HX-Reswap doen hetzelfde, maar
    uitsluitend voor het antwoord op een gebooste navigatie (htmx stuurt daar
    `HX-Boosted: true` bij). Geen overerving, geen invloed op de rest.
    """
    response = await call_next(request)
    if (
        request.headers.get("HX-Boosted") == "true"
        and response.status_code < 400
        and response.headers.get("content-type", "").startswith("text/html")
    ):
        response.headers["HX-Retarget"] = "#main"
        response.headers["HX-Reselect"] = "#main"
        response.headers["HX-Reswap"] = "outerHTML show:window:top"
    return response


@app.middleware("http")
async def _access_log(request: Request, call_next):
    """Toegangslog: methode, pad, status en duur. Health-checks overslaan om ruis
    te beperken. Geen query-strings of bodies — die kunnen persoonsgegevens
    bevatten.

    De duur staat sinds #645 als **veld** in de regel (`duration_ms`), niet enkel
    in de tekst: met de JSON-formatter kan je dan op trage requests filteren
    i.p.v. de tekst te moeten parsen. `route` draagt het routepatroon
    (`/admin/leden/gezin/{family_id}`), zodat duizend detailpagina's als één regel
    samengevat kunnen worden i.p.v. duizend losse paden.

    Boven `settings.slow_request_ms` gaat dezelfde regel op WARNING met
    `slow=true`. Met htmx is de snelheid van de UI de snelheid van de server; een
    trage route hoort op te vallen zonder dat iemand ernaar zoekt.
    """
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    # X-Process-Time maakt server- en netwerkduur scheidbaar voor het meetscript
    # (scripts/latency-probe.py) — goedkoop en zonder persoonsgegevens.
    response.headers["X-Process-Time"] = f"{duration_ms:.1f}"
    if request.url.path != "/api/health":
        route = request.scope.get("route")
        traag = duration_ms > settings.slow_request_ms
        logger.log(
            logging.WARNING if traag else logging.INFO,
            "%s %s -> %s (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            extra={
                "duration_ms": round(duration_ms, 1),
                "method": request.method,
                "path": request.url.path,
                "route": getattr(route, "path_format", None) or getattr(route, "path", None),
                "status": response.status_code,
                "slow": True if traag else None,
            },
        )
    return response


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError):
    # Log alleen welke velden faalden en waarom (type + locatie) — NOOIT de
    # ingevoerde waarden of de request-body, want die kunnen persoonsgegevens
    # bevatten. Genoeg om 422's te diagnosticeren zonder PII te lekken.
    velden = [
        {"loc": e.get("loc"), "type": e.get("type"), "msg": e.get("msg")} for e in exc.errors()
    ]
    logger.warning(
        "422 validatiefout op %s %s — velden: %s",
        request.method,
        request.url.path,
        velden,
    )
    # jsonable_encoder maakt eventuele ValueError-objecten in ctx (afkomstig
    # van custom validators) serialiseerbaar — net zoals FastAPI's eigen
    # handler. Zonder dit faalt json.dumps met een 500 i.p.v. een nette 422.
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    """#1583: a signed-in user refused on an admin screen gets a calm page, not a
    bare JSON body. Everything else — the API, a fragment, a write, any other
    status — keeps FastAPI's own answer."""
    if exc.status_code == 403:
        from app.ui.no_access import no_access_page

        page = no_access_page(request)
        if page is not None:
            return page
    return await http_exception_handler(request, exc)


@app.exception_handler(EmailAddressInvalid)
@app.exception_handler(EmailAddressInUse)
async def _email_address_in_use_handler(request: Request, exc: Exception):
    """CR-22 (#1704): an e-mail address another person already uses is a refusal
    with its reason, at whichever door it was typed — the answer a form shows
    under its field or in its message, never the 500 of an unhandled error.

    One handler and not a `try` in every route: the rule has one home (master
    data's `new_contact_detail`) and ten writers reach it through a dozen
    doors; a door that forgot its `try` would answer "Interne serverfout" to
    someone who only typed an address that was taken.

    #1853: the same for a text that is no address — the contact detail refuses
    it at the flush, whatever door wrote it.
    """
    return await http_exception_handler(
        request, StarletteHTTPException(status_code=422, detail=str(exc))
    )


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Onverwerkte uitzondering: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Interne serverfout"})


def _start_kernel_jobs() -> None:
    """Start de kernel-jobs scheduler (#396) — het achtergrondwerk-primitief
    (§5.8). In tests uitgeschakeld via JOBS_ENABLED=false."""
    if settings.jobs_enabled:
        from app.kernel.jobs import JobStatus, KernelJob, enqueue, start_scheduler

        start_scheduler()
        # #824: the orphan-record reconciliation (#401) used to be scheduled here too.
        # It disappeared together with the whole mechanism — an orphan payment is not
        # an event in the business but a symptom of a bug, and since #667 the
        # application can no longer create one.
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            sweep_pending = (
                db.query(KernelJob)
                .filter(
                    KernelJob.name == "workflow.sweep",
                    KernelJob.status.in_([JobStatus.PENDING, JobStatus.RUNNING]),
                )
                .count()
            )
            if not sweep_pending:
                enqueue(db, "workflow.sweep", {})
                db.commit()
        finally:
            db.close()


def _purge_old_email_logs() -> None:
    """Ruim bij opstart e-mailloggen op die ouder zijn dan de bewaartermijn
    (#328). Mag het opstarten nooit breken — fouten worden enkel gelogd."""
    try:
        from app.database import SessionLocal
        from app.domains.mail.api import purge_old_email_logs

        db = SessionLocal()
        try:
            deleted = purge_old_email_logs(db)
            if deleted:
                logger.info("E-maillog opgeschoond: %s oude rijen verwijderd.", deleted)
        finally:
            db.close()
    except Exception as exc:
        logger.warning("E-maillog opschonen bij opstart mislukt: %s", exc)


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "Raak Millegem API",
        "version": settings.app_version,
        "commit": settings.git_sha,
    }
