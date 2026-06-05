# CFO Sentinel - Backend (Multi-AI Agent Ecosystem)

CFO Sentinel adalah asisten Direktur Keuangan (CFO) cerdas yang dirancang untuk menjaga kesehatan finansial UMKM melalui kolaborasi 6 agen AI terspesialisasi.

## 🤖 Pemetaan AI Agent

| Agent Name | Berkas Kode | Tugas & Logika |
| :--- | :--- | :--- |
| **Agent 1: Bookkeeper** | `agents/bookkeeper_agent.py` | Mengubah teks mentah menjadi jurnal akuntansi (Debit/Kredit). Menggunakan SAK EMKM sebagai *guardrail*. |
| **Agent 2: Health** | `agents/health_agent.py` | Menghitung skor kesehatan (0-100) dan *Cash Runway* (hari) berdasarkan saldo kas riil. |
| **Agent 3: Anomaly** | `agents/anomaly_agent_new.py` | Mendeteksi kebocoran kas, pengeluaran tidak wajar, atau penggunaan dana bisnis untuk Netflix/Mixue (prive). |
| **Agent 4: Scenario** | `agents/scenario_agent.py` | Mensimulasikan dampak finansial jika terjadi perubahan parameter (misal: "Jika omzet turun 20%"). |
| **Agent 5: Advisor** | `agents/advisor_agent.py` | Merumuskan rekomendasi aksi konkret (Action Items) dengan prioritas tinggi/rendah. |
| **Agent 6: Reporter** | `agents/report_agent.py` | Merangkum seluruh temuan agen di atas menjadi narasi laporan harian yang mudah dipahami. |

## 🛠️ Tech Stack
- **Framework:** FastAPI (Python)
- **Orchestration:** Sequential Background Pipeline
- **Database:** SQLite (PRAGMA WAL)
- **AI Engine:** Gemini API / GPT-4o (via LangChain)

## 🚀 Instalasi (Docker)
```bash
docker compose up -d --build
```
API akan berjalan di `port 8000`. Dokumentasi Swagger tersedia di `/docs`.
