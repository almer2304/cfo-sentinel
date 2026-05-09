# CFO Sentinel — Architecture Decisions Log

## Deskripsi Project
AI-Powered Financial Survival & Strategic Decision System for SMEs.
Dibuat untuk AI Agent Competition 2026.

## [7 Mei 2026] Stack yang dipilih
- Orchestration: LangGraph (bukan n8n) 
  Alasan: LangGraph support conditional routing, reflection loop, 
  dan parallel execution. n8n terlalu terbatas untuk arsitektur ini.
- Database: SQLite (bukan ChromaDB)
  Alasan: Zero setup, portable, cukup untuk scope kompetisi.
- Dashboard: Streamlit (bukan React)
  Alasan: Efisien untuk timeline 3 minggu, bisa keren dengan Python saja.
- LLM: GPT-4o-mini (structured tasks) + Claude Haiku (narrative tasks)
  Alasan: Hemat token, model disesuaikan per kebutuhan agent.

## [7 Mei 2026] Keputusan Arsitektur
- MAX_REFLECTION = 2 untuk mencegah infinite loop di Critic Pattern
- Temperature 0.1 untuk agent struktural (Parser, Categorizer, Analyst)
- Temperature 0.3 untuk agent naratif (Scenario, Advisor)
- Semua angka keuangan HARUS dari SQLite, bukan dari LLM (anti-hallucination)
- Setiap agent punya fallback rule-based jika LLM call gagal

## [7 Mei 2026] Yang sengaja TIDAK dipakai
- n8n: terlalu terbatas untuk orchestration kompleks
- ChromaDB: overkill untuk scope ini
- LangSmith: nice to have, tapi bukan prioritas menang
- OCR: tidak diimplementasi agar tidak overscope