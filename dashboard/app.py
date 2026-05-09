"""
dashboard/app.py
CFO Sentinel — Streamlit Dashboard
"""

import os
import sys
# pyrefly: ignore [missing-import]
import streamlit as st
# pyrefly: ignore [missing-import]
import plotly.graph_objects as go
# pyrefly: ignore [missing-import]
import plotly.express as px
import pandas as pd
from datetime import datetime

# Tambahkan root project ke path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# pyrefly: ignore [missing-import]
from dotenv import load_dotenv
load_dotenv()

from core.database import init_database, get_agent_logs, get_transactions
from core.schemas import PipelineState

# ── Page config ────────────────────────────────────────────────────
st.set_page_config(
    page_title="CFO Sentinel — AI Financial Advisor",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ────────────────────────────────────────────────────────────
st.markdown("""
<style>
[data-testid="stMetric"] { background:#1e293b; border-radius:8px; padding:12px; }
.metric-danger { color:#ef4444 !important; }
.metric-warning { color:#f59e0b !important; }
.metric-safe { color:#22c55e !important; }
.stAlert { border-radius:8px; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════

def _init_session():
    if "pipeline_result" not in st.session_state:
        st.session_state.pipeline_result = None
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "is_demo" not in st.session_state:
        st.session_state.is_demo = os.getenv("DEMO_MODE", "false").lower() == "true"


# ══════════════════════════════════════════════════════════════════
# SIDEBAR
# ══════════════════════════════════════════════════════════════════

def render_sidebar() -> dict:
    """Render sidebar dan return konfigurasi input."""
    with st.sidebar:
        st.image("https://img.icons8.com/fluency/96/shield.png", width=64)
        st.title("CFO Sentinel")
        st.caption("AI-Powered Financial Advisor untuk UMKM")
        st.divider()

        demo_mode = st.toggle(
            "🎬 Demo Mode",
            value=st.session_state.is_demo,
            help="Gunakan data demo (hemat token, hasil deterministic)"
        )
        st.session_state.is_demo = demo_mode

        st.subheader("⚙️ Konfigurasi Bisnis")
        business_type = st.selectbox(
            "Jenis Bisnis",
            ["kuliner", "fashion", "jasa", "retail", "general"],
            index=0,
        )

        cash_balance = st.number_input(
            "Saldo Kas Saat Ini (Rp)",
            min_value=0,
            value=5_000_000,
            step=100_000,
            format="%d",
        )

        st.divider()
        st.caption("**Model:** Llama 3.3 70B (Groq)")
        st.caption("**Framework:** LangGraph 0.2.28")
        st.caption(f"**Session:** {datetime.now().strftime('%d/%m/%Y %H:%M')}")

    return {
        "business_type": business_type,
        "cash_balance": cash_balance,
        "demo_mode": demo_mode,
    }


# ══════════════════════════════════════════════════════════════════
# INPUT SECTION
# ══════════════════════════════════════════════════════════════════

def render_input_section(config: dict):
    """Render area input transaksi."""
    st.header("📝 Input Transaksi")

    placeholder = (
        "Contoh:\n"
        "Senin beli bahan baku 500rb, bayar listrik 200rb\n"
        "Selasa dapet orderan 2jt dari pelanggan\n"
        "Rabu gaji karyawan 1.5jt, beli kemasan 150rb"
    )

    col1, col2 = st.columns([3, 1])
    with col1:
        raw_input = st.text_area(
            "Ceritakan transaksi bisnis Anda (bebas format, Bahasa Indonesia):",
            height=150,
            placeholder=placeholder,
            key="raw_input",
        )
    with col2:
        st.markdown("<br>", unsafe_allow_html=True)
        if config["demo_mode"]:
            st.info("🎬 Mode demo aktif")
            if st.button("▶️ Jalankan Demo", use_container_width=True, type="primary"):
                _run_demo_pipeline()
        else:
            if st.button("🚀 Analisis", use_container_width=True, type="primary",
                         disabled=not raw_input.strip()):
                _run_live_pipeline(raw_input, config)

        if st.button("🔄 Reset", use_container_width=True):
            st.session_state.pipeline_result = None
            st.session_state.chat_history = []
            st.rerun()


def _run_demo_pipeline():
    """Load pre-cached demo state."""
    with st.spinner("🎬 Memuat demo..."):
        from dashboard.demo_mode import get_demo_state
        st.session_state.pipeline_result = get_demo_state()
    st.success("Demo loaded!")
    st.rerun()


def _run_live_pipeline(raw_input: str, config: dict):
    """Jalankan pipeline live."""
    with st.spinner("🤖 CFO Sentinel sedang menganalisis..."):
        progress = st.progress(0, text="Parser Agent...")
        try:
            from core.orchestrator import run_pipeline
            progress.progress(20, "Parser Agent...")
            result = run_pipeline(
                raw_input=raw_input,
                business_type=config["business_type"],
                current_cash_balance=float(config["cash_balance"]),
            )
            progress.progress(100, "Selesai!")
            st.session_state.pipeline_result = result
            st.success("✅ Analisis selesai!")
            st.rerun()
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            st.exception(e)


# ══════════════════════════════════════════════════════════════════
# RESULTS DASHBOARD
# ══════════════════════════════════════════════════════════════════

def render_results(state: PipelineState):
    """Render seluruh hasil analisis."""
    tabs = st.tabs([
        "📊 Overview",
        "⚠️ Anomali",
        "🎯 Skenario",
        "💡 Rekomendasi",
        "📈 Forecast",
        "🤖 Reasoning Log",
        "💬 Tanya CFO",
    ])

    with tabs[0]: render_overview(state)
    with tabs[1]: render_anomalies(state)
    with tabs[2]: render_scenario(state)
    with tabs[3]: render_recommendations(state)
    with tabs[4]: render_forecast(state)
    with tabs[5]: render_agent_logs(state)
    with tabs[6]: render_chat(state)


def render_overview(state: PipelineState):
    """Tab 1: Overview metrik keuangan."""
    analyst = state.analyst_output
    if not analyst:
        st.warning("Tidak ada data analisis.")
        return

    hs = analyst.health_score

    # Early warning banner
    if state.advisor_output and state.advisor_output.has_early_warning:
        ew = state.advisor_output.early_warning
        st.error(
            f"🚨 **PERINGATAN DINI:** {ew.message}",
            icon="🚨"
        )

    # Executive summary
    if state.advisor_output:
        st.info(f"**Ringkasan:** {state.advisor_output.executive_summary}")

    st.divider()

    # Metrik utama — baris 1
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        delta_hs = hs.current - hs.previous_month
        st.metric(
            "Health Score",
            f"{hs.current:.0f}/100",
            f"{delta_hs:+.0f} vs bulan lalu",
            delta_color="normal" if delta_hs >= 0 else "inverse",
        )
    with col2:
        st.metric("Saldo Kas", f"Rp {analyst.cash_balance:,.0f}")
    with col3:
        st.metric("Runway", f"{analyst.runway_days.expected:.0f} hari",
                  f"min {analyst.runway_days.minimum:.0f}d")
    with col4:
        st.metric("Gross Margin", f"{analyst.gross_margin:.1f}%")

    # Metrik baris 2
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Pemasukan", f"Rp {analyst.total_income:,.0f}")
    with col2:
        st.metric("Total Pengeluaran", f"Rp {analyst.total_expense:,.0f}")
    with col3:
        st.metric("Net Cash Flow", f"Rp {analyst.net_cashflow:,.0f}",
                  delta_color="normal" if analyst.net_cashflow >= 0 else "inverse")
    with col4:
        st.metric("Burn Rate/Hari", f"Rp {analyst.burn_rate_daily:,.0f}")

    st.divider()

    # Health Score gauge + kategori
    col1, col2 = st.columns([1, 2])
    with col1:
        fig = go.Figure(go.Indicator(
            mode="gauge+number+delta",
            value=hs.current,
            delta={"reference": hs.previous_month},
            gauge={
                "axis": {"range": [0, 100]},
                "bar": {"color": "#22c55e" if hs.current >= 65 else "#f59e0b" if hs.current >= 50 else "#ef4444"},
                "steps": [
                    {"range": [0, 50],  "color": "#1f2937"},
                    {"range": [50, 65], "color": "#1f2937"},
                    {"range": [65, 100],"color": "#1f2937"},
                ],
                "threshold": {
                    "line": {"color": "#ef4444", "width": 4},
                    "thickness": 0.75,
                    "value": 50,
                },
            },
            title={"text": f"Health Score<br><sub>{hs.status}</sub>"},
        ))
        fig.update_layout(height=280, margin=dict(t=40, b=20))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        if state.categorizer_output:
            # Pie chart pengeluaran per kategori
            cats = state.categorizer_output.categories_found
            txs  = state.categorizer_output.transactions
            expenses = {}
            for c in cats:
                total = sum(
                    t.amount if hasattr(t, "amount") else t.get("amount", 0)
                    for t in txs
                    if (t.category if hasattr(t, "category") else t.get("category")) == c
                    and (t.type if hasattr(t, "type") else t.get("type")) == "expense"
                )
                if total > 0:
                    expenses[c] = total

            if expenses:
                fig2 = px.pie(
                    names=list(expenses.keys()),
                    values=list(expenses.values()),
                    title="Pengeluaran per Kategori",
                    hole=0.4,
                    color_discrete_sequence=px.colors.qualitative.Set3,
                )
                fig2.update_layout(height=280, margin=dict(t=40, b=20))
                st.plotly_chart(fig2, use_container_width=True)

    # Narasi analyst
    st.subheader("📋 Analisis")
    st.write(analyst.narrative)


def render_anomalies(state: PipelineState):
    """Tab 2: Anomali yang ditemukan."""
    anomaly = state.anomaly_output
    if not anomaly:
        st.warning("Tidak ada data anomali.")
        return

    risk_colors = {"LOW": "🟢", "MEDIUM": "🟡", "HIGH": "🔴", "CRITICAL": "🚨"}
    sev_colors  = {"LOW": "blue", "MEDIUM": "orange", "HIGH": "red"}

    st.subheader(f"Risk Level: {risk_colors.get(anomaly.overall_risk_level, '?')} {anomaly.overall_risk_level}")

    if not anomaly.anomalies:
        st.success("✅ Tidak ada anomali terdeteksi. Pengeluaran dalam batas normal.")
        return

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Anomali", anomaly.total_anomalies)
    col2.metric("Severity HIGH", anomaly.high_severity_count)
    col3.metric("Analyst Valid", "✅ Ya" if anomaly.analyst_output_valid else "❌ Perlu koreksi")

    st.divider()
    for a in anomaly.anomalies:
        sev = a.severity if hasattr(a, "severity") else a.get("severity", "LOW")
        cat = a.category if hasattr(a, "category") else a.get("category", "?")
        dev = a.deviation_pct if hasattr(a, "deviation_pct") else a.get("deviation_pct", 0)
        desc = a.description if hasattr(a, "description") else a.get("description", "")
        action = a.suggested_action if hasattr(a, "suggested_action") else a.get("suggested_action", "")
        cur = a.current_amount if hasattr(a, "current_amount") else a.get("current_amount", 0)
        base = a.baseline_amount if hasattr(a, "baseline_amount") else a.get("baseline_amount", 0)

        icon = "🔴" if sev == "HIGH" else "🟡" if sev == "MEDIUM" else "🔵"
        with st.expander(f"{icon} [{sev}] {cat} — Deviasi {dev:+.0f}%", expanded=sev=="HIGH"):
            col1, col2 = st.columns(2)
            col1.metric("Bulan Ini", f"Rp {cur:,.0f}")
            col2.metric("Baseline", f"Rp {base:,.0f}", f"{dev:+.0f}%")
            st.write(desc)
            if action:
                st.info(f"💡 **Saran:** {action}")


def render_scenario(state: PipelineState):
    """Tab 3: Simulasi skenario."""
    scenario = state.scenario_output
    if not scenario:
        st.warning("Tidak ada data simulasi skenario.")
        return

    st.subheader(f"🎯 Skenario: Revenue {scenario.parameter_change_pct:+.0f}%")

    col1, col2, col3 = st.columns(3)
    col1.metric("Runway Baru", f"{scenario.new_runway.expected:.0f} hari",
                f"min {scenario.new_runway.minimum:.0f}d")
    col2.metric("Health Score Baru", f"{scenario.new_health_score:.0f}/100")
    if scenario.breakeven_day:
        col3.metric("Titik Kritis", f"Hari ke-{scenario.breakeven_day}")

    st.divider()
    st.markdown("**⛓️ Rantai Konsekuensi:**")
    st.write(scenario.chain_of_consequences)

    st.markdown("**🔧 Langkah Mitigasi:**")
    for line in scenario.mitigation_steps.split("\n"):
        if line.strip():
            st.write(line)

    if scenario.mitigation_impact:
        st.success(f"✅ **Dampak Mitigasi:** {scenario.mitigation_impact}")

    if scenario.cuttable_costs:
        st.divider()
        st.markdown(f"**✂️ Biaya yang Bisa Dipotong (Total: Rp {scenario.total_cuttable_amount:,.0f}):**")
        for c in scenario.cuttable_costs:
            cat = c.category if hasattr(c, "category") else c.get("category", "?")
            amt = c.amount if hasattr(c, "amount") else c.get("amount", 0)
            pct = c.cut_potential_pct if hasattr(c, "cut_potential_pct") else c.get("cut_potential_pct", 0)
            rat = c.rationale if hasattr(c, "rationale") else c.get("rationale", "")
            st.write(f"- **{cat}**: Rp {amt:,.0f} — bisa dipotong {pct:.0f}%. _{rat}_")


def render_recommendations(state: PipelineState):
    """Tab 4: Rekomendasi strategis."""
    advisor = state.advisor_output
    if not advisor:
        st.warning("Tidak ada rekomendasi.")
        return

    urgency_icon = {"IMMEDIATE": "🔴", "THIS_WEEK": "🟡", "THIS_MONTH": "🟢"}

    if advisor.has_early_warning and advisor.early_warning:
        ew = advisor.early_warning
        st.error(
            f"🚨 **{ew.message}**\n\n"
            f"Waktu tersisa: {ew.days_until_crisis or '?'} hari "
            f"(perkiraan {ew.confidence.minimum:.0f}–{ew.confidence.maximum:.0f} hari)\n\n"
            f"Pemicu: _{ew.trigger_condition}_"
        )

    st.subheader("📋 Action Items")
    for item in advisor.action_items:
        icon = urgency_icon.get(item.urgency, "⚪")
        with st.expander(f"{icon} #{item.priority} — {item.title}", expanded=item.priority == 1):
            st.write(item.description)
            col1, col2 = st.columns(2)
            col1.caption(f"**Urgensi:** {item.urgency}")
            if item.estimated_impact:
                col2.caption(f"**Dampak:** {item.estimated_impact}")

    if advisor.conflict_detected:
        st.warning(f"⚠️ **Conflict Resolution:** {advisor.conflict_resolution}")

    st.divider()
    st.subheader("📖 Analisis Detail")
    st.markdown(advisor.detailed_advice)
    st.caption(f"ℹ️ {advisor.uncertainty_statement}")


def render_forecast(state: PipelineState):
    """Tab 5: Forecast 30 hari."""
    analyst = state.analyst_output
    if not analyst or not analyst.forecast_30d:
        st.warning("Tidak ada data forecast.")
        return

    df = pd.DataFrame([
        {
            "Hari": fp.day if hasattr(fp, "day") else fp.get("day"),
            "Tanggal": fp.date if hasattr(fp, "date") else fp.get("date"),
            "Saldo": fp.predicted_balance if hasattr(fp, "predicted_balance") else fp.get("predicted_balance"),
            "Min": fp.confidence_min if hasattr(fp, "confidence_min") else fp.get("confidence_min"),
            "Max": fp.confidence_max if hasattr(fp, "confidence_max") else fp.get("confidence_max"),
        }
        for fp in analyst.forecast_30d
    ])

    fig = go.Figure()

    # Confidence band
    fig.add_trace(go.Scatter(
        x=df["Tanggal"], y=df["Max"],
        fill=None, mode="lines",
        line=dict(color="rgba(34,197,94,0.1)"),
        name="Confidence Max",
        showlegend=False,
    ))
    fig.add_trace(go.Scatter(
        x=df["Tanggal"], y=df["Min"],
        fill="tonexty",
        mode="lines",
        line=dict(color="rgba(34,197,94,0.1)"),
        fillcolor="rgba(34,197,94,0.1)",
        name="Confidence Range",
    ))

    # Main forecast line
    fig.add_trace(go.Scatter(
        x=df["Tanggal"], y=df["Saldo"],
        mode="lines+markers",
        line=dict(color="#22c55e", width=2),
        name="Proyeksi Saldo",
    ))

    # Danger line at 0
    fig.add_hline(y=0, line_dash="dash", line_color="#ef4444",
                  annotation_text="Batas Kritis", annotation_position="right")

    fig.update_layout(
        title="Proyeksi Cash Balance 30 Hari",
        xaxis_title="Tanggal",
        yaxis_title="Saldo (Rp)",
        height=400,
        template="plotly_dark",
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # Runway summary
    col1, col2, col3 = st.columns(3)
    col1.metric("Runway Min", f"{analyst.runway_days.minimum:.0f} hari")
    col2.metric("Runway Ekspektasi", f"{analyst.runway_days.expected:.0f} hari")
    col3.metric("Runway Max", f"{analyst.runway_days.maximum:.0f} hari")
    st.caption(f"_Asumsi: {analyst.runway_days.assumption}_")


def render_agent_logs(state: PipelineState):
    """Tab 6: Reasoning log setiap agent."""
    st.subheader("🤖 Agent Reasoning Log")

    try:
        logs = get_agent_logs(state.session_id)
    except Exception:
        logs = []

    if not logs:
        st.info("Log tersedia setelah menjalankan analisis live (bukan demo mode).")
        return

    for log in logs:
        icon_map = {
            "parser": "🔍", "categorizer": "🏷️", "analyst": "📈",
            "anomaly": "🔎", "scenario": "🎯", "advisor": "🧠",
        }
        icon = icon_map.get(log.get("agent_name", ""), "🤖")
        with st.expander(
            f"{icon} {log.get('agent_name','?').title()} Agent "
            f"— Step {log.get('step','?')} "
            f"({log.get('duration_ms', 0)}ms)",
            expanded=False
        ):
            st.caption(f"**Input:** {log.get('input_summary', '-')}")
            st.write(f"**Reasoning:** {log.get('reasoning', '-')}")
            st.caption(f"**Output:** {log.get('output_summary', '-')}")
            st.caption(f"Status: `{log.get('status', '?')}`")


def render_chat(state: PipelineState):
    """Tab 7: Conversational interface."""
    st.subheader("💬 Tanya CFO Sentinel")
    st.caption("Tanya langsung tentang kondisi keuangan bisnis Anda dalam Bahasa Indonesia.")

    # Demo Q&A quick buttons
    if state.is_demo_mode:
        from dashboard.demo_mode import DEMO_QA_PAIRS
        st.markdown("**💡 Pertanyaan cepat:**")
        for qa in DEMO_QA_PAIRS:
            if st.button(qa["question"], key=f"qa_{qa['question'][:20]}"):
                st.session_state.chat_history.append(
                    {"role": "user", "content": qa["question"]}
                )
                st.session_state.chat_history.append(
                    {"role": "assistant", "content": qa["answer"]}
                )
                st.rerun()
        st.divider()

    # Chat history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])

    # Input box
    user_q = st.chat_input("Tanyakan sesuatu tentang keuangan bisnis Anda...")
    if user_q:
        st.session_state.chat_history.append({"role": "user", "content": user_q})

        if state.analyst_output and state.anomaly_output and state.advisor_output:
            with st.spinner("CFO Sentinel sedang berpikir..."):
                if state.is_demo_mode:
                    answer = (
                        "Mode demo aktif — jawaban ini adalah contoh. "
                        "Untuk jawaban real-time, nonaktifkan Demo Mode dan jalankan analisis live."
                    )
                else:
                    from agents.advisor_agent import answer_question
                    answer = answer_question(
                        question=user_q,
                        analyst_output=state.analyst_output,
                        anomaly_output=state.anomaly_output,
                        advisor_output=state.advisor_output,
                    )
        else:
            answer = "Jalankan analisis terlebih dahulu sebelum mengajukan pertanyaan."

        st.session_state.chat_history.append({"role": "assistant", "content": answer})
        st.rerun()


# ══════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════

def main():
    _init_session()
    init_database()

    config = render_sidebar()

    st.title("🛡️ CFO Sentinel")
    st.markdown("*AI-Powered Financial Survival & Strategic Decision System untuk UMKM*")
    st.divider()

    render_input_section(config)

    result = st.session_state.pipeline_result
    if result:
        st.divider()
        render_results(result)
    else:
        # Welcome screen
        st.markdown("""
        ### 👋 Selamat datang di CFO Sentinel!

        CFO Sentinel adalah sistem AI yang membantu UMKM Indonesia mengelola keuangan bisnis:

        | Fitur | Deskripsi |
        |-------|-----------|
        | 📝 **Input Bebas** | Ceritakan transaksi dalam Bahasa Indonesia sehari-hari |
        | 📊 **Health Score** | Nilai kesehatan keuangan 0–100 dengan 3 benchmark |
        | ⚠️ **Early Warning** | Deteksi ancaman kas sebelum terjadi krisis |
        | 🎯 **Simulasi** | *What-if* jika penjualan turun atau biaya naik |
        | 💡 **Rekomendasi** | Action items konkret dengan estimasi dampak |
        | 💬 **Tanya CFO** | Tanya langsung dalam Bahasa Indonesia |

        **Mulai:** Masukkan transaksi di kotak di atas, atau aktifkan **Demo Mode** untuk melihat contoh analisis.
        """)


if __name__ == "__main__":
    main()
