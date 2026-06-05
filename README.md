# CFO Sentinel - Backend (Expert Multi-Agent Ecosystem)

CFO Sentinel adalah asisten Direktur Keuangan (CFO) cerdas yang dirancang untuk menjaga kesehatan finansial UMKM melalui kolaborasi 6 agen AI terspesialisasi yang bekerja dengan logika **Reasoning & Reflection**.

## 🤖 Pemetaan AI Agent (The CFO Team)

| Agent Name | Berkas Kode | Tugas & Logika |
| :--- | :--- | :--- |
| **Agent 1: Parser** | `agents/parser_agent.py` | Mengubah teks/suara mentah menjadi data transaksi atomik yang akurat. |
| **Agent 2: Bookkeeper** | `agents/bookkeeper_agent.py` | Melakukan penjurnalan akuntansi otomatis (Debit/Kredit) sesuai standar SAK EMKM. |
| **Agent 3: Analyst** | `agents/analyst_agent.py` | Menghitung skor kesehatan (0-100) dan *Cash Runway* berdasarkan data riil dari SQLite. |
| **Agent 4: Anomaly** | `agents/anomaly_agent_new.py` | Mendeteksi kebocoran kas dan pengeluaran tidak wajar (Red Flag Detector). |
| **Agent 5: Scenario** | `agents/scenario_agent.py` | Mensimulasikan dampak finansial "What-If" dengan penalaran mendalam. |
| **Agent 6: Advisor** | `agents/advisor_agent.py` | Merumuskan rekomendasi aksi strategis (Action Items) berbasis ROI & Likuiditas. |

## 🛠️ Tech Stack & Komponen
*   **Framework:** FastAPI (Python) - Performa tinggi & asinkron.
*   **Database:** SQLite - Portabel & Reproducible (Zero setup untuk juri).
*   **Orchestration:** LangGraph - Manajemen alur multi-agent yang kompleks.
*   **AI Engine:** Qwen 3.6 (Plus/Flash) & Claude Haiku - Perpaduan kecepatan dan kecerdasan tinggi.
*   **Deployment:** Docker & Docker Compose - Siap dideploy ke lingkungan server mana pun.

## 🚀 Cara Instalasi & Penggunaan

### Menggunakan Docker (Rekomendasi)
1. Clone repository ini.
2. Pastikan file `.env` sudah terisi dengan API Key yang valid.
3. Jalankan perintah:
   ```bash
   docker compose up -d --build
   ```
4. API akan berjalan di port `8000`. Akses dokumentasi Swagger di `http://localhost:8000/docs`.

### Tanpa Docker
1. Buat virtual environment: `python -m venv venv`
2. Aktivasi venv dan install dependencies: `pip install -r requirements.txt`
3. Jalankan server: `python api/main.py`

## 📊 Keunggulan Kompetisi
1. **Multi-Agent Collaboration**: 6 Agent bekerja sama dengan sistem *Conflict Resolution*.
2. **Deep Reasoning**: Menggunakan pola *Reflection* (Anomaly mengoreksi Analyst).
3. **CFO Expert Knowledge**: Prompting yang didesain khusus berdasarkan standar manajemen keuangan profesional.
4. **Desktop Responsive UI**: Tampilan dashboard yang elegan di semua perangkat.

---
**Repo Frontend CFO Sentinel:**
[https://github.com/almer2304/cfo-sentinel-frontend](https://github.com/almer2304/cfo-sentinel-frontend)
