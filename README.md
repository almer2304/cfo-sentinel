# CFO Sentinel - Backend (Multi-AI Agent)

CFO Sentinel adalah sistem manajemen keuangan cerdas yang dirancang khusus untuk UMKM Indonesia. Menggunakan arsitektur Multi-AI Agent, sistem ini mengubah input bahasa alami menjadi jurnal akuntansi yang presisi dan memberikan saran strategis setingkat CFO (Chief Financial Officer).

## 🚀 Fitur Utama

1.  **AI Bookkeeper (Agent 1):** Klasifikasi transaksi otomatis menggunakan LLM dengan fallback aturan akuntansi deterministik. Mendukung *split transaction* (tunai/utang).
2.  **Financial Health Scorer (Agent 2):** Menghitung skor kesehatan bisnis berdasarkan likuiditas, margin, dan arus kas.
3.  **Anomaly Detector (Agent 3):** Mendeteksi penyimpangan pengeluaran secara otomatis terhadap baseline historis.
4.  **Scenario Simulator (Agent 4):** Simulasi "What-If" (misal: "Bagaimana jika omzet turun 20%?") untuk memitigasi risiko.
5.  **Strategic Advisor (Agent 5):** Memberikan rekomendasi aksi konkret berdasarkan kondisi kas dan runway.
6.  **Narrative Reporter (Agent 6):** Menghasilkan laporan narasi harian yang mudah dipahami pemilik bisnis.

## 🛠️ Tech Stack

*   **Framework:** FastAPI (Python)
*   **Database:** SQLite dengan logika Double-Entry Accounting
*   **AI Engine:** LangGraph / Gemini API / LangChain
*   **Validation:** Pydantic Models

## 📦 Instalasi

1. Clone repository
2. Buat virtual environment: `python -m venv venv`
3. Install dependencies: `pip install -r requirements.txt`
4. Setup `.env` (isi API Key Gemini/OpenAI)
5. Jalankan server: `python api/main.py`

## 📊 Struktur Data
Sistem menggunakan tabel `daily_summaries` untuk menyimpan state harian yang diproses oleh background pipeline setiap kali transaksi baru masuk.
