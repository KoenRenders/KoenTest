import logging
import time

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import engine
from app.logging_config import configure_logging
from app import soft_delete  # noqa: F401 - registreert de globale soft-delete-filter
from app.models import *  # noqa: F401, F403 - ensures all models are registered
from app.routers import members, admin, media
from app.routers.member_household import router as member_household_router
from app.routers.member_import import router as member_import_router
from app.domains.activities.router import router as activities_router
from app.domains.activities.ui import router as activities_ui_router
from app.domains.activities.admin_ui import router as activities_admin_ui_router
from app.domains.auth.router import router as auth_router
from app.domains.auth.ui import router as auth_ui_router
from app.domains.chatbot.router import router as chat_router
from app.domains.chatbot.info_router import router as chatbot_info_router
from app.domains.chatbot.ui import router as chatbot_ui_router
from app.domains.stt.router import router as stt_router
from app.domains.cms.router import router as cms_router
from app.domains.mdm.router import router as mdm_router
from app.domains.forms.router import router as forms_router
from app.domains.forms.ui import router as forms_ui_router
from app.domains.workflow.ui import router as workflow_ui_router
from app.domains.workflow import handlers as workflow_handlers  # noqa: F401 - event-abonnementen (#398)
from app.domains.mail.router import router as email_log_router
from app.domains.mail.ui import router as email_log_ui_router
from app.domains.mdm.ui import router as mdm_ui_router
from app.domains.mail.handlers import retry_mail  # noqa: F401 - registreert de mail.retry-job (#399)
from app.domains.payment.handlers import reconcile_orphans  # noqa: F401 - registreert payment.reconcile (#401)
from app.domains.payment.router import router as payment_router
from app.domains.payment.ui import router as payment_ui_router

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


app = FastAPI(
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

app.include_router(auth_router, prefix="/api/v1")
app.include_router(members.router, prefix="/api/v1")
app.include_router(activities_router, prefix="/api/v1")
app.include_router(chat_router, prefix="/api/v1")
app.include_router(stt_router, prefix="/api/v1")
app.include_router(cms_router, prefix="/api/v1")
app.include_router(mdm_router, prefix="/api/v1")
app.include_router(media.router, prefix="/api/v1")
app.include_router(chatbot_info_router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1/admin")
app.include_router(member_household_router, prefix="/api/v1")
app.include_router(member_import_router, prefix="/api/v1")
app.include_router(forms_router, prefix="/api/v1")
app.include_router(forms_ui_router)
app.include_router(activities_ui_router)
app.include_router(activities_admin_ui_router)
app.include_router(chatbot_ui_router)
app.include_router(auth_ui_router)
app.include_router(email_log_ui_router)
app.include_router(mdm_ui_router)
app.include_router(payment_ui_router)
app.include_router(workflow_ui_router)
app.include_router(email_log_router, prefix="/api/v1/admin")
app.include_router(payment_router, prefix="/api/v1")


# Server-rendered UI (#396, §21): statics (CSS + gevendorde htmx/Alpine) komen
# rechtstreeks uit de backend; Caddy routeert /static/* hierheen.
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")


@app.middleware("http")
async def _access_log(request: Request, call_next):
    # Toegangslog op INFO: methode, pad, status en duur. Health-checks
    # overslaan om ruis te beperken. Geen query-strings of bodies — die
    # kunnen persoonsgegevens bevatten.
    start = time.perf_counter()
    response = await call_next(request)
    if request.url.path != "/api/health":
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s -> %s (%.1f ms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
    return response


@app.exception_handler(RequestValidationError)
async def _validation_error_handler(request: Request, exc: RequestValidationError):
    # Log alleen welke velden faalden en waarom (type + locatie) — NOOIT de
    # ingevoerde waarden of de request-body, want die kunnen persoonsgegevens
    # bevatten. Genoeg om 422's te diagnosticeren zonder PII te lekken.
    velden = [
        {"loc": e.get("loc"), "type": e.get("type"), "msg": e.get("msg")}
        for e in exc.errors()
    ]
    logger.warning(
        "422 validatiefout op %s %s — velden: %s",
        request.method, request.url.path, velden,
    )
    # jsonable_encoder maakt eventuele ValueError-objecten in ctx (afkomstig
    # van custom validators) serialiseerbaar — net zoals FastAPI's eigen
    # handler. Zonder dit faalt json.dumps met een 500 i.p.v. een nette 422.
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(exc.errors())})


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Onverwerkte uitzondering: %s %s", request.method, request.url.path
    )
    return JSONResponse(status_code=500, content={"detail": "Interne serverfout"})


@app.on_event("startup")
def _start_kernel_jobs() -> None:
    """Start de kernel-jobs scheduler (#396) — het achtergrondwerk-primitief
    (§5.8). In tests uitgeschakeld via JOBS_ENABLED=false."""
    if settings.jobs_enabled:
        from app.kernel.jobs import KernelJob, enqueue, start_scheduler

        start_scheduler()
        # Wees-record-reconciliatie (#401): zorg dat er altijd precies één
        # geplande payment.reconcile-job leeft (her-enqueuet zichzelf daarna).
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            pending = (db.query(KernelJob)
                       .filter(KernelJob.name == "payment.reconcile",
                               KernelJob.status.in_(["pending", "running"]))
                       .count())
            if not pending:
                enqueue(db, "payment.reconcile", {})
                db.commit()
            sweep_pending = (db.query(KernelJob)
                             .filter(KernelJob.name == "workflow.sweep",
                                     KernelJob.status.in_(["pending", "running"]))
                             .count())
            if not sweep_pending:
                enqueue(db, "workflow.sweep", {})
                db.commit()
        finally:
            db.close()


@app.on_event("startup")
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
