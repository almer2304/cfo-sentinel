# CFO Sentinel — AI Context File
# Baca file ini dulu sebelum menyentuh apapun di project ini.
# File ini adalah sumber kebenaran tunggal untuk semua keputusan.

---

## IDENTITAS PROJECT

Nama: CFO Sentinel
Tagline: AI-Powered Financial Survival & Strategic Decision System for SMEs
Kompetisi: AI Agent Competition 2026 (ai-event.qhomemart.com)
Deadline submission: 25–30 Mei 2026
Presentasi final: 6 Juni 2026
Hadiah Juara 1: Rp 5.000.000

---

## MASALAH YANG DISELESAIKAN

65 juta UMKM Indonesia tidak punya sistem keuangan yang proper.
60% UMKM tutup dalam 5 tahun — penyebab utama: cash flow crisis
yang tidak terdeteksi lebih awal.

CFO Sentinel hadir sebagai CFO virtual yang:
- Mencegah UMKM bangkrut dengan early warning system
- Mendeteksi anomali pengeluaran sebelum menjadi krisis
- Memberikan rekomendasi bisnis yang konkret dan actionable
- Membantu UMKM memahami kondisi keuangan mereka sendiri

---

## ARSITEKTUR SISTEM — 6 AGENT

Pipeline: Input → Parser → Categorizer → Analyst → [Anomaly + Scenario paralel] → Advisor → Dashboard

### Agent 1: Parser Agent
File: agents/parser_agent.py
Tugas: Parse teks bebas Bahasa Indonesia → JSON terstruktur
Model: GPT-4o-mini (temperature 0.1)
Input: String teks dari user (bisa berantakan, singkatan, typo)
Output: ParserOutput (Pydantic schema)
Fitur khusus: Business/Personal disambiguation — jika ambigu, tanya user

### Agent 2: Categorizer Agent
File: agents/categorizer_agent.py
Tugas: Klasifikasi transaksi ke kategori bisnis
Model: GPT-4o-mini (temperature 0.1)
Input: Output dari Parser Agent
Output: CategorizerOutput (Pydantic schema)
Kategori valid: Bahan Baku, Operasional, Marketing, SDM,
                Penjualan, Piutang, Utang, Investasi, Lain-lain

### Agent 3: Financial Analyst Agent
File: agents/analyst_agent.py
Tugas: Hitung semua metrik keuangan + forecast 30 hari
Model: Claude Haiku (temperature 0.1)
Input: Output Categorizer + data SQLite
Output: AnalystOutput (Pydantic schema)
PENTING: Semua angka dari SQLite. LLM hanya untuk narasi.
Metrik: cash balance, burn rate, runway (dengan confidence range),
        gross margin, health score (0-100 dengan 3 benchmark),
        forecast 30 hari

### Agent 4: Anomaly Detection Agent
File: agents/anomaly_agent.py
Tugas: Deteksi anomali + validasi output Analyst (Critic Pattern)
Model: GPT-4o-mini (temperature 0.2)
Input: Output Analyst + baseline dari SQLite
Output: AnomalyOutput (Pydantic schema)
Fitur khusus: Critic Pattern — bisa trigger reflection loop
              MAX_REFLECTION = 2 (hard limit, tidak bisa diubah)
Deteksi: Statistical (z-score + deviation %) bukan LLM

### Agent 5: Scenario Simulation Agent
File: agents/scenario_agent.py
Tugas: Simulasi "what if" dengan deep reasoning
Model: Claude Haiku (temperature 0.3)
Input: Data keuangan current + pertanyaan skenario
Output: ScenarioOutput (Pydantic schema)
PENTING: Bukan kalkulator. Harus reason tentang fixed vs variable
         cost, chain of consequences, titik kritis, mitigasi konkret.

### Agent 6: Strategic Advisor Agent
File: agents/advisor_agent.py
Tugas: Rekomendasi bisnis + early warning + conversational interface
Model: Claude Haiku (temperature 0.3)
Input: Semua output dari agent 1-5 + historical context
Output: AdvisorOutput (Pydantic schema)
Fitur khusus:
- Conflict resolution: jika Anomaly vs Scenario bertentangan,
  prioritaskan survival (konservatif)
- Conversational: user bisa tanya langsung dalam BI
- Uncertainty awareness: semua output punya confidence range

---

## ORCHESTRATION — LangGraph

File: core/orchestrator.py
Framework: LangGraph (bukan n8n — keputusan final, tidak berubah)
Pattern: Sequential pipeline + conditional routing + reflection loop

Flow:
1. Parser → Categorizer (sequential)
2. Categorizer → Analyst (sequential)
3. Analyst → Anomaly CHECK (Critic Pattern)
   - Jika Anomaly raise flag → Analyst re-run (max 2x)
   - Jika clear → lanjut
4. Analyst + Anomaly → Scenario (paralel dalam 1 LLM call)
5. Anomaly + Scenario → Advisor
6. Advisor → Dashboard

Termination conditions:
- MAX_REFLECTION = 2 (hard limit untuk reflection loop)
- Timeout 30 detik per agent call
- Fallback rule-based jika LLM gagal

---

## DATABASE — SQLite

File: core/database.py
Alasan SQLite (bukan PostgreSQL):
- Zero setup untuk juri (reproducibility)
- Satu file .db yang portable
- Scale lebih dari cukup untuk UMKM single-user

Tabel:
- transactions        (semua transaksi)
- analytics           (hasil kalkulasi per sesi)
- anomalies           (anomali yang terdeteksi)
- recommendations     (rekomendasi advisor)
- monthly_snapshots   (ringkasan bulanan — persistent memory)
- spending_baselines  (baseline per kategori — untuk anomaly detection)
- agent_logs          (reasoning log setiap agent — visible di UI)
- scenarios           (hasil simulasi skenario)

---

## ANTI-HALLUCINATION STRATEGY

1. Temperature rendah: 0.1 untuk agent struktural
2. Pydantic validation: setiap output divalidasi sebelum diteruskan
3. Data grounding: semua angka di-inject dari SQLite ke prompt
4. Self-check di setiap prompt: agent wajib verifikasi angkanya sendiri
5. Schema contract: format output sudah didefinisikan ketat di prompts

---

## PERSISTENT MEMORY LAYER

File: core/memory.py
Solusi cold start: Synthetic baseline dari INDUSTRY_BASELINES
Industri yang didukung: kuliner, fashion, jasa, retail, general

Cara kerja:
- User baru → load industry baseline (synthetic)
- Setelah 1 bulan data → update baseline dari data real
- Weighted average: 60% old + 40% new (smooth update)

Health Score benchmark (3 referensi wajib):
1. Skor bulan lalu milik user (perbandingan historis)
2. Rata-rata industri sejenis (dari INDUSTRY_BASELINES)
3. Danger threshold <50/100

---

## TECH STACK LENGKAP

Development:
- IDE: Antigravity (Google) — gratis selama public preview
- AI coding: Gemini 3 Pro via Antigravity
- Language: Python 3.11
- Orchestration: LangGraph 0.2.28
- Validation: Pydantic 2.9.2
- Dashboard: Streamlit 1.40.0
- Charts: Plotly 5.24.1
- Testing: pytest
- DB: SQLite (built-in Python)

LLM untuk sistem (via Sumopod portal):
MODEL_PARSER=gemini-2.0-flash
MODEL_CATEGORIZER=gemini-2.0-flash
MODEL_ANALYST=gemini-2.0-flash
MODEL_ANOMALY=gemini-2.0-flash
MODEL_SCENARIO=gemini-2.0-flash
MODEL_ADVISOR=gemini-2.0-flash

Deployment:
- VPS: Sumopod
- Container: Docker + docker-compose
- Web server: Nginx
- Budget LLM: Voucher Sumopod Rp 150.000

---

## FLAW YANG SUDAH DIIDENTIFIKASI DAN SOLUSINYA

1. Cold Start → Synthetic Baseline Generator (core/seed_data.py)
2. Health Score tanpa benchmark → 3 referensi wajib
3. Scenario Agent terlalu sederhana → Deep reasoning prompt (chain of consequences)
4. Campur keuangan pribadi/bisnis → Business/Personal disambiguation di Parser
5. Token economics → Batch Anomaly+Scenario dalam 1 call, Demo Mode
6. Demo non-deterministic → Demo Mode dengan pre-cached output
7. Parallel agents konflik → Conflict Resolution Protocol di Advisor
8. Reflection loop infinite → MAX_REFLECTION = 2 hard limit
9. Schema contract → Pydantic validation antar semua agent
10. Graceful degradation → Fallback rule-based di setiap agent

---

## YANG SENGAJA TIDAK DIPAKAI (DAN ALASANNYA)

- n8n: terlalu terbatas untuk conditional routing kompleks
- PostgreSQL: overkill, reproducibility jadi susah
- ChromaDB: tidak butuh vector search untuk scope ini
- LangSmith: nice to have, bukan prioritas menang
- OCR: tidak diimplementasi agar tidak overscope
- Executive Report Agent terpisah: duplikasi Advisor, digabung jadi output mode

---

## STATUS PENGERJAAN

Core layer:
[x] core/database.py     — SELESAI, sudah ditest
[x] core/schemas.py      — SELESAI, sudah ditest
[x] core/llm_client.py   — SELESAI
[x] core/prompts.py      — SELESAI
[x] core/memory.py       — SELESAI, sudah ditest
[x] core/seed_data.py    — SELESAI, sudah ditest

Agents: (update checklist ini setiap file selesai)
[x] agents/parser_agent.py      — SELESAI
[x] agents/categorizer_agent.py — SELESAI
[x] agents/analyst_agent.py     — SELESAI
[x] agents/anomaly_agent.py     — SELESAI
[x] agents/scenario_agent.py    — SELESAI
[x] agents/advisor_agent.py     — SELESAI

Orchestration:
[x] core/orchestrator.py        — SELESAI

Dashboard:
[x] dashboard/app.py            — SELESAI, berjalan di port 8501
[x] dashboard/demo_mode.py      — SELESAI, demo Warung Sate Padang

Deployment:
[ ] Dockerfile
[ ] docker-compose.yml
[ ] README.md

---

## CARA PAKAI FILE INI (UNTUK AI ASSISTANT)

Jika kamu adalah AI assistant yang baru masuk ke project ini:

1. Baca file ini dari awal sampai akhir dulu.
2. Cek STATUS PENGERJAAN di atas — lihat mana yang sudah selesai.
3. Baca file yang sudah selesai sebelum mengerjakan file berikutnya.
4. JANGAN ubah keputusan arsitektur tanpa alasan yang sangat kuat.
5. Semua keputusan yang ada di sini sudah dipertimbangkan matang.
6. Jika ada yang tidak jelas, tanya dulu sebelum mengimplementasikan.

Urutan pengerjaan yang benar:
core/ → agents/ → orchestrator → dashboard → docker → README