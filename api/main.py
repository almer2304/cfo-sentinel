"""
api/main.py
CFO Sentinel — FastAPI Application Entry Point (Arsitektur Baru)
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from core.database import init_database
from core.database_new import init_new_tables
from api.routes import auth, analysis, history, chat
from api.routes import transactions, dashboard


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Jalankan init saat startup."""
    init_database()
    init_new_tables()
    print("[OK] CFO Sentinel API siap — Arsitektur Kasir Digital v2")
    yield
    print("[BYE] CFO Sentinel API berhenti")


app = FastAPI(
    title="CFO Sentinel API",
    description="AI-Powered Financial Advisor untuk UMKM Indonesia — v2 Kasir Digital",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS — izinkan React frontend akses API
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",        # React dev server
        "http://localhost:5173",        # Vite dev server
        "https://cfosentinel.my.id",    # Production domain
        "http://cfosentinel.my.id",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routes v1 (lama — tetap ada untuk kompatibilitas) ────────────────────────
app.include_router(auth.router,         prefix="/api/v1")
app.include_router(analysis.router,     prefix="/api/v1")
app.include_router(history.router,      prefix="/api/v1")
app.include_router(chat.router,         prefix="/api/v1")

# ── Routes v2 (baru — arsitektur kasir digital) ──────────────────────────────
app.include_router(transactions.router, prefix="/api/v2")
app.include_router(dashboard.router,    prefix="/api/v2")


@app.get("/")
async def root():
    return {
        "service": "CFO Sentinel API",
        "version": "2.0.0",
        "status":  "running",
        "docs":    "/docs",
        "arch":    "Kasir Digital + Background Pipeline",
    }


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
