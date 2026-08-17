"""
app/main.py
-----------
FastAPI application entry point.

Registers all routers and sets up CORS, lifespan events, and health check.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import upload, status, results
from app.core.config import settings

app = FastAPI(
    title="Recalce",
    description="Automated bank reconciliation engine",
    version="0.1.0",
)

# ── CORS ─────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(upload.router,  prefix="/api/v1")
app.include_router(status.router,  prefix="/api/v1")
app.include_router(results.router, prefix="/api/v1")


# ── Health ────────────────────────────────────────────────────────────────────
@app.get("/api/v1/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok"}
