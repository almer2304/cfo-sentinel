"""
api/main.py
CFO Sentinel — FastAPI Application Entry Point
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from core.database import init_database
from api.routes import auth, analysis, history, chat


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Jalankan init saat startup."""
    init_database()
    print("[OK] CFO Sentinel API siap")
    yield
    print("[BYE] CFO Sentinel API berhenti")


app = FastAPI(
    title="CFO Sentinel API",
    description="AI-Powered Financial Advisor untuk UMKM Indonesia",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — izinkan React frontend akses API
# Ganti origins sesuai domain kamu saat production
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

# Register semua routes
app.include_router(auth.router,     prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")
app.include_router(history.router,  prefix="/api/v1")
app.include_router(chat.router,     prefix="/api/v1")


@app.get("/")
async def root():
    return {
        "service": "CFO Sentinel API",
        "version": "1.0.0",
        "status":  "running",
        "docs":    "/docs",
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
