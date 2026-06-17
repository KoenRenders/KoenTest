import logging
import time

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import engine
from app.logging_config import configure_logging
from app import soft_delete  # noqa: F401 - registreert de globale soft-delete-filter
from app.models import *  # noqa: F401, F403 - ensures all models are registered
from app.routers import auth, members, activities, ideas, cms, admin, media, chat, chatbot_info
from app.routers.member_household import router as member_household_router
from app.routers.member_import import router as member_import_router
from app.routers.users import router as users_router
from app.domains.payment_gateway.router import router as payment_gateway_router
from app.domains.payment_status.router import router as payment_status_router

configure_logging()

logger = logging.getLogger(__name__)

logger.info(
    "Starting Raak Millegem %s (%s) [omgeving=%s]",
    settings.app_version,
    settings.git_sha,
    settings.app_env,
)

app = FastAPI(
    title="Raak Millegem API",
    description="API for the Raak Millegem community association",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(members.router, prefix="/api/v1")
app.include_router(activities.router, prefix="/api/v1")
app.include_router(ideas.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")
app.include_router(cms.router, prefix="/api/v1")
app.include_router(media.router, prefix="/api/v1")
app.include_router(chatbot_info.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1/admin")
app.include_router(users_router, prefix="/api/v1")
app.include_router(member_household_router, prefix="/api/v1")
app.include_router(member_import_router, prefix="/api/v1")
app.include_router(payment_gateway_router, prefix="/api/v1")
app.include_router(payment_status_router, prefix="/api/v1")


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


@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "Raak Millegem API",
        "version": settings.app_version,
        "commit": settings.git_sha,
    }
