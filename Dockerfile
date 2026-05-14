# ══════════════════════════════════════════════════════════════════
# CFO Sentinel — Dockerfile
# Base: Python 3.11 slim (lebih kecil dari full image)
# ══════════════════════════════════════════════════════════════════

FROM python:3.11-slim

# Metadata
LABEL maintainer="CFO Sentinel Team"
LABEL description="AI-Powered Financial Survival System for SMEs"
LABEL version="1.0.0"

# ── Environment ───────────────────────────────────────────────────
ENV PYTHONDONTWRITEBYTECODE=1   
# Tidak buat file .pyc — container lebih bersih

ENV PYTHONUNBUFFERED=1          
# Output langsung ke stdout — penting untuk docker logs

ENV PYTHONPATH=/app

# ── Working directory ─────────────────────────────────────────────
WORKDIR /app

# ── Install system dependencies ───────────────────────────────────
# Minimal — hanya yang benar-benar dibutuhkan
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ── Install Python dependencies ───────────────────────────────────
# Copy requirements dulu (layer caching — rebuild lebih cepat)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ── Copy source code ──────────────────────────────────────────────
COPY . .

# ── Buat direktori data (untuk SQLite) ───────────────────────────
RUN mkdir -p /app/data

# ── Expose ports ──────────────────────────────────────────────────
# 8000 = FastAPI backend (primary)
# 8501 = Streamlit dashboard (admin/backup)
EXPOSE 8000 8501

# ── Health check ──────────────────────────────────────────────────
# Default: cek FastAPI. docker-compose bisa override per service.
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# ── Entrypoint ────────────────────────────────────────────────────
# Default: jalankan FastAPI backend.
# docker-compose override CMD per service:
#   cfo-api       → uvicorn api.main:app (default ini)
#   cfo-dashboard → streamlit run dashboard/app.py
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]