# CFO Sentinel - Backend (Multi-AI Agent Ecosystem)

CFO Sentinel adalah sistem manajemen keuangan cerdas yang dirancang khusus untuk UMKM Indonesia. Menggunakan arsitektur Multi-AI Agent, sistem ini bertindak sebagai asisten Direktur Keuangan (CFO) yang secara otomatis memproses transaksi, memantau kesehatan bisnis, dan memberikan rekomendasi strategis.

## 🤖 AI Agent Ecosystem

Sistem ini digerakkan oleh **6 Agen AI terspesialisasi** yang bekerja secara kolaboratif dalam sebuah *background pipeline*:

1.  **Agent 1: Bookkeeper Agent**
    *   **Tugas:** Mengonversi input bahasa alami (misal: "beli bensin 50rb") menjadi jurnal akuntansi debit-kredit berbasis SAK EMKM.
    *   **Keunggulan:** Mendeteksi kategori, tipe akun (Aset/Beban), dan menangani *split transaction* secara otomatis.
2.  **Agent 2: Health Agent**
    *   **Tugas:** Menghitung skor kesehatan bisnis (0-100) dan memproyeksikan **Runway** (sisa hari bertahan) berdasarkan saldo kas saat ini.
3.  **Agent 3: Anomaly Agent**
    *   **Tugas:** Mendeteksi kebocoran kas, pengeluaran tidak wajar, atau penggunaan dana bisnis untuk keperluan pribadi (prive).
4.  **Agent 4: Scenario Agent**
    *   **Tugas:** Melakukan simulasi risiko "What-If" (misal: simulasi dampak jika omzet turun 20%) secara otomatis untuk kesiapan bisnis.
5.  **Agent 5: Advisor Agent**
    *   **Tugas:** Merumuskan **Action Items** (rekomendasi aksi) dengan tingkat urgensi tertentu (Immediate/This Week).
6.  **Agent 6: Reporter Agent**
    *   **Tugas:** Menghasilkan narasi laporan harian yang membumi dan mudah dipahami oleh pemilik bisnis.

## 🛠️ Tech Stack & Komponen
*   **Framework:** FastAPI (Python) - Performa tinggi & asinkron.
*   **Database:** SQLite - Portabel dengan dukungan PRAGMA WAL untuk konkurensi.
*   **AI Engine:** LangGraph / Gemini API - Orkestrasi agent yang kompleks.
*   **Deployment:** Docker & Docker Compose - Siap dideploy ke lingkungan server apa pun.

## 🚀 Cara Instalasi & Penggunaan

### Menggunakan Docker (Rekomendasi)
1. Clone repository ini.
2. Pastikan file `.env` sudah terisi (terutama API Key LLM).
3. Jalankan perintah:
   ```bash
   docker compose up -d --build
   ```
4. API akan berjalan di port `8000`. Akses dokumentasi di `http://localhost:8000/docs`.

### Tanpa Docker
1. Buat virtual environment: `python -m venv venv`
2. Install dependencies: `pip install -r requirements.txt`
3. Jalankan server: `python api/main.py`

## 📊 Dokumentasi Teknis
Seluruh logika agent tersimpan di folder `agents/`, sementara aturan akuntansi deterministik (guardrails) tersimpan di `core/finance_rules.py` untuk memastikan AI tidak melakukan kesalahan perhitungan angka keuangan.

## Repo Frontend dari CFO Sentinel
   `https://github.com/almer2304/cfo-sentinel-frontend`
