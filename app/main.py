"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.database.session import init_db
import os
from pathlib import Path

app = FastAPI(
    title="HealthTrack AI",
    description="Medical Report Intelligence & Longitudinal Health Tracker",
    version="1.0.0",
)

# CORS — allow React dev server and Vercel deployments
allowed_origins = [
    "http://localhost:5173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
]
if os.getenv("FRONTEND_URL"):
    allowed_origins.append(os.getenv("FRONTEND_URL").rstrip("/"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and mount routers
from app.api.auth_routes import router as auth_router
from app.api.reports import router as reports_router
from app.api.patients import router as patients_router
from app.api.settings import router as settings_router
from app.api.dashboard import router as dashboard_router
from app.api.trends import router as trends_router
from app.api.chat import router as chat_router
from app.api.guidance import router as guidance_router

app.include_router(auth_router)
app.include_router(reports_router)
app.include_router(patients_router)
app.include_router(settings_router)
app.include_router(dashboard_router)
app.include_router(trends_router)
app.include_router(chat_router)
app.include_router(guidance_router)

# Serve uploaded files (for PDF viewing in frontend)
settings.ensure_directories()
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


@app.on_event("startup")
def on_startup():
    """Initialize database tables on startup."""
    settings.ensure_directories()
    init_db()


@app.get("/api/health")
def health_check():
    return {"status": "healthy", "app": "HealthTrack AI"}
