from fpdf import FPDF
from datetime import datetime
import io

class CFOSentinelPDF(FPDF):
    def header(self):
        self.set_font('Helvetica', 'B', 16)
        self.set_text_color(220, 38, 38)
        self.cell(0, 10, 'CFO Sentinel', ln=False, align='L')
        self.set_font('Helvetica', '', 10)
        self.set_text_color(107, 114, 128)
        self.cell(0, 10, 
            f'Laporan Keuangan - {datetime.now().strftime("%d %B %Y")}', 
            ln=True, align='R')
        self.set_draw_color(220, 38, 38)
        self.line(10, 25, 200, 25)
        self.ln(5)

    def footer(self):
        self.set_y(-15)
        self.set_font('Helvetica', 'I', 8)
        self.set_text_color(156, 163, 175)
        self.cell(0, 10, 
            f'CFO Sentinel - AI Financial Advisor untuk UMKM | '
            f'Halaman {self.page_no()}', 
            align='C')

def generate_pdf_report(pipeline_state) -> bytes:
    """
    Generate laporan PDF dari hasil analisis pipeline.
    Returns bytes yang bisa di-download via Streamlit.
    """
    pdf = CFOSentinelPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    analyst  = pipeline_state.analyst_output
    anomaly  = pipeline_state.anomaly_output
    advisor  = pipeline_state.advisor_output
    scenario = pipeline_state.scenario_output
    
    if not analyst:
        pdf.set_font('Helvetica', '', 12)
        pdf.cell(0, 10, 'Tidak ada data analisis.', ln=True)
        return bytes(pdf.output())
    
    # ── RINGKASAN EKSEKUTIF ────────────────────────────────────
    pdf.set_font('Helvetica', 'B', 13)
    pdf.set_text_color(31, 41, 55)
    pdf.cell(0, 8, 'RINGKASAN KONDISI KEUANGAN', ln=True)
    pdf.set_draw_color(229, 231, 235)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    
    if advisor:
        pdf.set_font('Helvetica', '', 11)
        pdf.set_text_color(55, 65, 81)
        pdf.multi_cell(0, 6, advisor.executive_summary)
    pdf.ln(5)
    
    # ── METRIK UTAMA ──────────────────────────────────────────
    pdf.set_font('Helvetica', 'B', 13)
    pdf.set_text_color(31, 41, 55)
    pdf.cell(0, 8, 'METRIK KEUANGAN UTAMA', ln=True)
    pdf.line(10, pdf.get_y(), 200, pdf.get_y())
    pdf.ln(3)
    
    hs = analyst.health_score
    status_color = {
        'DANGER':  (220, 38, 38),
        'WARNING': (245, 158, 11),
        'SAFE':    (16, 185, 129),
    }.get(hs.status, (107, 114, 128))
    
    # Health Score box
    pdf.set_fill_color(*status_color)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font('Helvetica', 'B', 12)
    pdf.cell(0, 10, 
        f'Skor Kesehatan Bisnis: {hs.current:.0f}/100 - {hs.status}', 
        ln=True, fill=True)
    pdf.ln(3)
    
    # Metrik tabel
    metrics = [
        ('Total Pemasukan', 
         f"Rp {analyst.total_income:,.0f}"),
        ('Total Pengeluaran', 
         f"Rp {analyst.total_expense:,.0f}"),
        ('Sisa Uang Bersih', 
         f"Rp {analyst.net_cashflow:,.0f}"),
        ('Saldo Kas Saat Ini', 
         f"Rp {analyst.cash_balance:,.0f}"),
        ('Uang Habis per Hari', 
         f"Rp {analyst.burn_rate_daily:,.0f}"),
        ('Perkiraan Bertahan', 
         f"{analyst.runway_days.expected:.0f} hari "
         f"({analyst.runway_days.minimum:.0f}-"
         f"{analyst.runway_days.maximum:.0f} hari)"),
        ('Keuntungan per Penjualan', 
         f"{analyst.gross_margin:.1f}%"),
    ]
    
    pdf.set_font('Helvetica', '', 10)
    for label, value in metrics:
        pdf.set_text_color(75, 85, 99)
        pdf.cell(90, 7, label, border='B')
        pdf.set_text_color(17, 24, 39)
        pdf.set_font('Helvetica', 'B', 10)
        pdf.cell(90, 7, value, border='B', ln=True)
        pdf.set_font('Helvetica', '', 10)
    pdf.ln(5)
    
    # ── PERINGATAN DINI ───────────────────────────────────────
    if advisor and advisor.has_early_warning and advisor.early_warning:
        pdf.set_font('Helvetica', 'B', 13)
        pdf.set_text_color(31, 41, 55)
        pdf.cell(0, 8, 'PERINGATAN DINI', ln=True)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)
        
        pdf.set_fill_color(254, 226, 226)
        pdf.set_text_color(153, 27, 27)
        pdf.set_font('Helvetica', 'B', 11)
        pdf.multi_cell(0, 7, 
            f"!! {advisor.early_warning.message}", 
            fill=True)
        pdf.ln(3)
    
    # ── LANGKAH YANG HARUS DILAKUKAN ─────────────────────────
    if advisor and advisor.action_items:
        pdf.set_font('Helvetica', 'B', 13)
        pdf.set_text_color(31, 41, 55)
        pdf.cell(0, 8, 'LANGKAH YANG HARUS DILAKUKAN', ln=True)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)
        
        for item in advisor.action_items:
            urgency_label = {
                'IMMEDIATE':  'Segera',
                'THIS_WEEK':  'Minggu Ini',
                'THIS_MONTH': 'Bulan Ini',
            }.get(item.urgency, item.urgency)
            
            pdf.set_font('Helvetica', 'B', 11)
            pdf.set_text_color(17, 24, 39)
            pdf.cell(0, 7, 
                f"#{item.priority} - {item.title} ({urgency_label})", 
                ln=True)
            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(75, 85, 99)
            pdf.multi_cell(0, 6, item.description)
            if item.estimated_impact:
                pdf.set_text_color(5, 150, 105)
                pdf.cell(0, 6, 
                    f"Dampak: {item.estimated_impact}", ln=True)
            pdf.ln(2)
    
    # ── PENGELUARAN TIDAK BIASA ───────────────────────────────
    if anomaly and anomaly.anomalies:
        pdf.add_page()
        pdf.set_font('Helvetica', 'B', 13)
        pdf.set_text_color(31, 41, 55)
        pdf.cell(0, 8, 'PENGELUARAN YANG PERLU DIPERHATIKAN', ln=True)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)
        
        for a in anomaly.anomalies:
            sev_label = {
                'HIGH':   'Sangat Perlu Diperhatikan',
                'MEDIUM': 'Perlu Diperhatikan',
                'LOW':    'Perlu Dicermati',
            }.get(a.severity, a.severity)
            sev_color = {
                'HIGH':   (220, 38, 38),
                'MEDIUM': (245, 158, 11),
                'LOW':    (59, 130, 246),
            }.get(a.severity, (107, 114, 128))
            
            pdf.set_font('Helvetica', 'B', 11)
            pdf.set_text_color(*sev_color)
            pdf.cell(0, 7, f"{a.category} - {sev_label}", ln=True)
            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(75, 85, 99)
            pdf.cell(0, 6, 
                f"Bulan ini: Rp {a.current_amount:,.0f} | "
                f"Rata-rata biasanya: Rp {a.baseline_amount:,.0f} | "
                f"Perbedaan: {a.deviation_pct:+.0f}%", 
                ln=True)
            pdf.multi_cell(0, 6, a.description)
            if a.suggested_action:
                pdf.set_text_color(5, 150, 105)
                pdf.cell(0, 6, f"Saran: {a.suggested_action}", ln=True)
            pdf.ln(2)
    
    # ── SIMULASI SKENARIO ─────────────────────────────────────
    if scenario:
        pdf.set_font('Helvetica', 'B', 13)
        pdf.set_text_color(31, 41, 55)
        pdf.cell(0, 8, 
            f'SIMULASI: BAGAIMANA JIKA PENJUALAN TURUN '
            f'{abs(scenario.parameter_change_pct):.0f}%?', 
            ln=True)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(3)
        
        pdf.set_font('Helvetica', '', 10)
        pdf.set_text_color(75, 85, 99)
        pdf.multi_cell(0, 6, scenario.chain_of_consequences)
        pdf.ln(2)
        
        if scenario.mitigation_steps:
            pdf.set_font('Helvetica', 'B', 11)
            pdf.set_text_color(17, 24, 39)
            pdf.cell(0, 7, 'Langkah yang bisa dilakukan:', ln=True)
            pdf.set_font('Helvetica', '', 10)
            pdf.set_text_color(75, 85, 99)
            pdf.multi_cell(0, 6, scenario.mitigation_steps)
    
    # ── DISCLAIMER ────────────────────────────────────────────
    pdf.ln(10)
    pdf.set_font('Helvetica', 'I', 9)
    pdf.set_text_color(156, 163, 175)
    pdf.multi_cell(0, 5, 
        'Laporan ini dibuat otomatis oleh CFO Sentinel berdasarkan '
        'data yang Anda masukkan. Hasil analisis bersifat estimasi '
        'dan dapat berbeda dengan kondisi aktual. Selalu '
        'pertimbangkan kondisi spesifik bisnis Anda sebelum '
        'mengambil keputusan penting.')
    
    return bytes(pdf.output())
