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

# ── Expose port Streamlit ─────────────────────────────────────────
EXPOSE 8501

# ── Health check ──────────────────────────────────────────────────
# Docker akan cek apakah Streamlit masih jalan setiap 30 detik
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# ── Entrypoint ────────────────────────────────────────────────────
# --server.address=0.0.0.0  → bisa diakses dari luar container
# --server.port=8501         → port yang di-expose
# --server.headless=true     → tidak buka browser otomatis
# --server.fileWatcherType=none → matikan file watcher (lebih stabil di prod)
CMD ["streamlit", "run", "dashboard/app.py", \
     "--server.address=0.0.0.0", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--server.fileWatcherType=none", \
     "--browser.gatherUsageStats=false"]