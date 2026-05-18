"""
test_llm_pipeline.py
Test pipeline LLM calls — classifier, health narasi, anomaly JSON.
Jalankan: python test_llm_pipeline.py
"""
import sys
sys.stdout.reconfigure(encoding="utf-8")

# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
load_dotenv()

from core.llm_client import call_llm_json, call_llm, AGENT_CONFIG

print("=" * 60)
print("TEST: max_tokens config")
print("=" * 60)
for agent, cfg in AGENT_CONFIG.items():
    print(f"  {agent:12} max_tokens={cfg['max_tokens']}, model={cfg['model']}")

print()
print("=" * 60)
print("TEST: call_llm_json — classifier agent")
print("=" * 60)

system_prompt = (
    "Kamu adalah Akuntan Profesional Indonesia.\n"
    "Klasifikasikan transaksi ke accounting_type yang tepat.\n"
    "Balas HANYA dengan JSON: {\"accounting_type\": \"...\", \"category\": \"...\", \"is_recurring\": false}"
)
user_message = "Transaksi: expense - Bayar listrik - Rp 500000 - Kategori: Operasional"

result, meta = call_llm_json(
    agent_name="classifier",
    system_prompt=system_prompt,
    user_message=user_message,
)
print(f"Result JSON : {result}")
print(f"Tokens used: {meta['tokens_used']}")
print(f"Duration   : {meta['duration_ms']}ms")
print(f"Status     : {'[OK] SUKSES' if result else '[FAIL] GAGAL - JSON kosong'}")

print()
print("=" * 60)
print("TEST: call_llm — health narasi (text response)")
print("=" * 60)

health_system = (
    "Kamu adalah Financial Analyst UMKM Indonesia.\n"
    "Buat narasi singkat kondisi keuangan dalam 1-2 kalimat.\n"
    "Balas HANYA dengan teks narasi biasa, tanpa JSON."
)
health_data = (
    "Health Score: 72/100 | "
    "Pemasukan bulan ini: Rp 15.000.000 | "
    "Pengeluaran bulan ini: Rp 9.500.000 | "
    "Saldo kas: Rp 5.500.000 | "
    "Uang habis per hari: Rp 316.000 | "
    "Perkiraan bertahan: 17 hari"
)
narrative, meta2 = call_llm(
    agent_name="health",
    system_prompt=health_system,
    user_message=f"Buat narasi kondisi keuangan:\n{health_data}",
    response_format="text",
)
print(f"Narasi    : {narrative[:200]}")
print(f"Tokens    : {meta2['tokens_used']}")
print(f"Duration  : {meta2['duration_ms']}ms")
print(f"Status    : {'[OK] SUKSES' if narrative else '[FAIL] GAGAL - narasi kosong'}")

print()
print("=" * 60)
print("TEST: call_llm_json — anomaly agent")
print("=" * 60)

anomaly_system = (
    "Kamu adalah Risk Analyst UMKM.\n"
    "Deteksi anomali pengeluaran dan balas HANYA dengan JSON:\n"
    "{\"anomalies\": [], \"overall_risk\": \"LOW|MEDIUM|HIGH|CRITICAL\"}"
)
anomaly_prompt = (
    "Pengeluaran bulan ini:\n"
    "Bahan Baku: Rp 8.000.000 | Operasional: Rp 3.000.000\n\n"
    "Baseline rata-rata 3 bulan lalu:\n"
    "Bahan Baku: Rp 4.000.000/bulan | Operasional: Rp 2.500.000/bulan\n\n"
    "Deteksi anomali berdasarkan perbandingan di atas."
)
result3, meta3 = call_llm_json(
    agent_name="anomaly",
    system_prompt=anomaly_system,
    user_message=anomaly_prompt,
)
print(f"Result JSON: {result3}")
print(f"Tokens     : {meta3['tokens_used']}")
print(f"Duration   : {meta3['duration_ms']}ms")
print(f"Status     : {'[OK] SUKSES' if result3 else '[FAIL] GAGAL - JSON kosong'}")

print()
print("=" * 60)
print("RINGKASAN TEST")
print("=" * 60)
tests = [
    ("Classifier JSON", bool(result)),
    ("Health Narasi", bool(narrative)),
    ("Anomaly JSON", bool(result3)),
]
for name, ok in tests:
    print(f"  {'[OK]' if ok else '[!!]'} {name}")

all_ok = all(ok for _, ok in tests)
print(f"\n  STATUS: {'SEMUA OK!' if all_ok else 'ADA YANG GAGAL'}")
