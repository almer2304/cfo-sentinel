"""
agents/anomaly_agent.py — AGENT 3 (NEW VERSION)
Deteksi anomali dengan membandingkan current vs baseline historis.
Dipanggil otomatis dari background pipeline.
"""

import time
from datetime import datetime, timedelta, timezone
from core.llm_client import call_llm_json
from core.database import get_connection, log_agent_step
from core.database_new import get_spending_by_category_efficient

WIB = timezone(timedelta(hours=7))

ANOMALY_SYSTEM = """\
Kamu adalah Risk Analyst senior dengan keahlian mendalam di akuntansi UMKM \
Indonesia (SAK-EMKM). Pengalamanmu 15 tahun menganalisis pola keuangan \
usaha kecil: warung, toko kelontong, UMKM F&B, jasa, dan perdagangan.

═══════════════════════════════════════════
TUGASMU
═══════════════════════════════════════════
Bandingkan pengeluaran bulan ini PER KATEGORI dengan rata-rata baseline \
3 bulan sebelumnya. Identifikasi anomali yang signifikan secara bisnis.

═══════════════════════════════════════════
ATURAN ANALISIS
═══════════════════════════════════════════
1. Analisis SETIAP kategori secara terpisah.
   - Hitung deviasi = ((current - baseline) / baseline) × 100%.
   - Jika baseline = 0 dan current > 0, ini kategori baru → LOW severity \
     kecuali nominalnya besar (>Rp 5 juta → MEDIUM).

2. Jenis anomali:
   - LONJAKAN (current >> baseline): kemungkinan pemborosan, fraud, \
     atau kebutuhan musiman yang sah.
   - PENURUNAN TAJAM (current << baseline): kemungkinan bisnis melambat, \
     supplier hilang, atau efisiensi berhasil.

3. Threshold severity berdasarkan DEVIASI ABSOLUT:
   - HIGH:   |deviasi| > 100%  (naik/turun lebih dari 2× lipat)
   - MEDIUM: |deviasi| 50–100%
   - LOW:    |deviasi| 25–50%
   - Di bawah 25%: BUKAN anomali, jangan masukkan.

4. Konteks musiman Indonesia (pertimbangkan sebelum menandai anomali):
   - Ramadan & Lebaran (bervariasi): lonjakan bahan baku F&B, THR, \
     parcel → wajar naik 50–150%.
   - Juli–Agustus: libur sekolah, pariwisata naik.
   - November–Desember: tutup buku, belanja akhir tahun, stok Natal.
   - Januari: penjualan turun pasca liburan, biaya izin/pajak tahunan.
   Jika lonjakan sesuai pola musiman, turunkan severity satu tingkat \
   dan jelaskan di root_cause_hypothesis.

5. Jika data baseline kosong atau ini bulan pertama → JANGAN buat anomali, \
   kembalikan list kosong.

═══════════════════════════════════════════
FORMAT OUTPUT — JSON SAJA, TANPA TEKS LAIN
═══════════════════════════════════════════
{
  "anomalies": [
    {
      "category": "nama kategori PERSIS dari data input",
      "severity": "HIGH|MEDIUM|LOW",
      "current_amount": 2000000,
      "baseline_amount": 500000,
      "deviation_pct": 300.0,
      "description": "penjelasan singkat dan jelas dalam Bahasa Indonesia",
      "root_cause_hypothesis": "kemungkinan penyebab berdasarkan konteks UMKM",
      "suggested_action": "saran konkret 1–2 kalimat yang bisa langsung dilakukan"
    }
  ],
  "overall_risk": "LOW|MEDIUM|HIGH|CRITICAL"
}

Aturan overall_risk:
- CRITICAL: ada ≥1 anomali HIGH dengan nominal > Rp 10 juta
- HIGH:     ada ≥1 anomali HIGH
- MEDIUM:   ada anomali MEDIUM tapi tidak ada HIGH
- LOW:      hanya anomali LOW atau tidak ada anomali
"""


def run_anomaly_agent(user_id: int) -> dict:
    """
    Agent 3: Deteksi anomali dengan membanding current vs baseline.
    2 query aggregate + 1 LLM call.
    """
    start = time.time()

    now     = datetime.now(WIB)
    today   = now.strftime('%Y-%m-%d')
    m_start = now.strftime('%Y-%m-01')

    three_months_ago = (now - timedelta(days=90)).strftime('%Y-%m-%d')
    last_month_end   = (now.replace(day=1) - timedelta(days=1)).strftime('%Y-%m-%d')

    current = get_spending_by_category_efficient(user_id, m_start, today)
    baseline_raw = get_spending_by_category_efficient(
        user_id, three_months_ago, last_month_end
    )

    # Bulan pertama atau tidak ada data → skip deteksi anomali
    if not current or not baseline_raw:
        result = {"anomalies": [], "overall_risk": "LOW"}
        duration = int((time.time() - start) * 1000)
        log_agent_step(
            session_id=f"anomaly-{user_id}-{today}",
            agent_name="anomaly",
            step=3,
            input_summary=f"Current: {len(current) if current else 0} kategori, Baseline: {len(baseline_raw) if baseline_raw else 0} kategori",
            reasoning="Skipped: data belum cukup untuk deteksi anomali (bulan pertama atau baseline kosong)",
            output_summary="[]",
            duration_ms=duration,
            status="skipped",
            user_id=user_id,
        )
        return result

    # Bangun baseline map: rata-rata per bulan per kategori
    baseline_map = {
        b["category"]: b["total"] / 3
        for b in baseline_raw
    }

    # Siapkan data perbandingan per kategori untuk LLM
    comparison_lines = []
    for c in current[:15]:
        cat = c["category"]
        cur_amt = c["total"]
        base_amt = baseline_map.get(cat, 0)
        if base_amt > 0:
            dev = ((cur_amt - base_amt) / base_amt) * 100
        else:
            dev = 100.0 if cur_amt > 0 else 0.0
        comparison_lines.append(
            f"• {cat}: bulan ini Rp {cur_amt:,.0f} vs baseline Rp {base_amt:,.0f}/bulan "
            f"(deviasi {dev:+.1f}%)"
        )

    # Cek kategori baseline yang hilang di bulan ini (penurunan 100%)
    current_cats = {c["category"] for c in current}
    for cat, base_amt in list(baseline_map.items())[:10]:
        if cat not in current_cats and base_amt > 50000:
            comparison_lines.append(
                f"• {cat}: bulan ini Rp 0 vs baseline Rp {base_amt:,.0f}/bulan "
                f"(deviasi -100.0%) — KATEGORI HILANG"
            )

    bulan_tahun = now.strftime('%B %Y')
    prompt = (
        f"Periode analisis: {bulan_tahun}\n\n"
        f"Perbandingan pengeluaran per kategori:\n"
        + "\n".join(comparison_lines)
        + "\n\nDeteksi anomali berdasarkan perbandingan di atas. "
        "Hanya laporkan kategori dengan |deviasi| ≥ 25%."
    )

    result, _ = call_llm_json(
        agent_name="anomaly",
        system_prompt=ANOMALY_SYSTEM,
        user_message=prompt,
    )

    anomalies = result.get("anomalies", []) if result else []

    # Simpan anomali ke database
    if anomalies:
        conn = get_connection()
        cursor = conn.cursor()
        for a in anomalies:
            # Gunakan data per-kategori dari respons LLM
            cat = a.get("category", "Lain-lain")

            # Hitung ulang deviation dari data aktual sebagai validasi
            current_match = next(
                (c for c in current if c["category"] == cat), None
            )
            current_amt  = a.get("current_amount", current_match["total"] if current_match else 0)
            baseline_amt = a.get("baseline_amount", baseline_map.get(cat, 0))
            if baseline_amt > 0:
                deviation = ((current_amt - baseline_amt) / baseline_amt) * 100
            else:
                deviation = 100.0 if current_amt > 0 else 0.0

            # BUG 1 FIX: SQL INSERT sekarang lengkap dengan VALUES clause
            cursor.execute("""
                INSERT INTO transaction_anomalies (
                    user_id, category, severity,
                    current_amount, baseline_amount, deviation_pct,
                    description, suggested_action
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                cat,
                a.get("severity", "LOW"),
                round(current_amt, 2),
                round(baseline_amt, 2),
                round(deviation, 1),
                a.get("description", ""),
                a.get("suggested_action", ""),
            ))

        has_critical = any(a.get("severity") == "HIGH" for a in anomalies)
        cursor.execute("""
            UPDATE daily_summaries
            SET anomaly_count        = ?,
                has_critical_anomaly = ?
            WHERE user_id = ? AND date_only = ?
        """, (len(anomalies), 1 if has_critical else 0, user_id, today))

        conn.commit()
        conn.close()

    duration = int((time.time() - start) * 1000)
    overall_risk = result.get("overall_risk", "LOW") if result else "LOW"
    log_agent_step(
        session_id=f"anomaly-{user_id}-{today}",
        agent_name="anomaly",
        step=3,
        input_summary=f"Current: {len(current)} kategori, Baseline: {len(baseline_raw)} kategori",
        reasoning=f"Found {len(anomalies)} anomalies. Risk: {overall_risk}",
        output_summary=str(anomalies[:2]),
        duration_ms=duration,
        status="success" if result else "fallback",
        user_id=user_id,
    )

    return result or {"anomalies": [], "overall_risk": "LOW"}
