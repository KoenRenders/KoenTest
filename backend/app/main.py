from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import engine
from app.models import *  # noqa: F401, F403 - ensures all models are registered
from app.routers import auth, members, activities, ideas, cms, admin, media
from app.domains.payment_gateway.router import router as payment_gateway_router
from app.domains.payment_status.router import router as payment_status_router

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
app.include_router(cms.router, prefix="/api/v1")
app.include_router(media.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1/admin")
app.include_router(payment_gateway_router, prefix="/api/v1")
app.include_router(payment_status_router, prefix="/api/v1")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Raak Millegem API"}
