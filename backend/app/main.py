from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database import engine
from app.models import *  # noqa: F401, F403 - ensures all models are registered
from app.routers import auth, members, activities, ideas, cms, admin

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Raak Millegem API",
    description="API for the Raak Millegem community association",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url, "http://localhost:3000", "http://localhost"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(members.router, prefix="/api/v1")
app.include_router(activities.router, prefix="/api/v1")
app.include_router(ideas.router, prefix="/api/v1")
app.include_router(cms.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1/admin")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Raak Millegem API"}
