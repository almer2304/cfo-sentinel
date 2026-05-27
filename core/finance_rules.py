"""
Deterministic finance rules for CFO Sentinel.

LLM boleh membantu narasi, tetapi angka keuangan, jurnal dasar, dan risk flag
harus bisa dihitung tanpa LLM. Modul ini menjadi guardrail akuntansi untuk
arsitektur kasir digital v2.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta
import re
from typing import Any


@dataclass
class MoneyMention:
    value: float
    text: str
    start: int
    end: int
    context: str


@dataclass
class ClassifiedEntry:
    amount: float
    description: str
    accounting_type: str
    debit_account: str
    credit_account: str
    type: str
    category: str
    sub_category: str = ""
    is_recurring: bool = False
    is_business: bool = True
    is_pnl: bool = True
    confidence: float = 0.78
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


MONEY_RE = re.compile(
    r"(?P<prefix>rp\.?\s*)?"
    r"(?P<number>\d{1,3}(?:[.\s]\d{3})+(?:,\d+)?|\d+(?:[.,]\d+)?)"
    r"\s*(?P<suffix>rb|ribu|k|jt|juta|m|miliar|milyar)?",
    re.IGNORECASE,
)

CLAUSE_SPLIT_RE = re.compile(
    r"\s*(?:[,;\n]|(?:\blalu\b)|(?:\bterus\b)|(?:\bkemudian\b)|(?:\bhabis itu\b))\s*",
    re.IGNORECASE,
)

QUANTITY_WORDS = {
    "porsi", "pcs", "pc", "buah", "kg", "gram", "gr", "liter", "ltr",
    "botol", "pack", "pak", "dus", "box", "orang", "kali", "unit",
    "meter", "m2", "hari", "bulan", "tahun",
}


def _norm(text: str) -> str:
    return (text or "").lower().strip()


def _has_any(text: str, keywords: list[str] | set[str] | tuple[str, ...]) -> bool:
    for keyword in keywords:
        k = str(keyword).lower().strip()
        if not k:
            continue
        if " " in k:
            if k in text:
                return True
            continue
        if re.search(rf"\b{re.escape(k)}\b", text):
            return True
    return False


def _normalize_number(raw_number: str, suffix: str | None) -> float:
    raw = (raw_number or "").strip().replace(" ", "")
    suffix = (suffix or "").lower()

    if suffix:
        number = raw.replace(",", ".")
        if number.count(".") > 1:
            parts = number.split(".")
            number = "".join(parts[:-1]) + "." + parts[-1]
        base = float(number)
    else:
        if "." in raw and "," in raw:
            base = float(raw.replace(".", "").replace(",", "."))
        elif "." in raw:
            chunks = raw.split(".")
            base = float(raw.replace(".", "")) if all(len(c) == 3 for c in chunks[1:]) else float(raw)
        elif "," in raw:
            base = float(raw.replace(",", "."))
        else:
            base = float(raw)

    if suffix in {"rb", "ribu", "k"}:
        return base * 1_000
    if suffix in {"jt", "juta"}:
        return base * 1_000_000
    if suffix in {"m", "miliar", "milyar"}:
        return base * 1_000_000_000
    return base


def _looks_like_non_money(text: str, match: re.Match, value: float) -> bool:
    """Hindari salah membaca tanggal, tahun, atau kuantitas sebagai nominal."""
    prefix = match.group("prefix")
    suffix = match.group("suffix")
    number = match.group("number") or ""
    if prefix or suffix or "." in number or "," in number:
        return False

    start, end = match.span()
    before = text[start - 1] if start > 0 else ""
    after = text[end] if end < len(text) else ""

    # ISO/slash date fragments: 2026-05-26, 26/05/2026.
    if before in "-/" or after in "-/":
        return True

    # Standalone year.
    if len(number) == 4 and 1900 <= value <= 2100:
        return True

    next_word = re.match(r"\s*([a-zA-Z0-9]+)", text[end:].lower())
    if next_word and next_word.group(1) in QUANTITY_WORDS:
        return True

    return False


def extract_money_mentions(raw_input: str) -> list[MoneyMention]:
    """Extract Indonesian money mentions such as 750rb, Rp 1.500.000, 2 juta."""
    text = raw_input or ""
    mentions: list[MoneyMention] = []

    for match in MONEY_RE.finditer(text):
        prefix = match.group("prefix")
        suffix = match.group("suffix")
        number = match.group("number")
        token = match.group(0).strip()

        has_currency_signal = bool(prefix or suffix or "." in number or "," in number)
        try:
            value = _normalize_number(number, suffix)
        except ValueError:
            continue

        if _looks_like_non_money(text, match, value):
            continue

        # Avoid parsing quantities like "10 porsi" as rupiah.
        if not has_currency_signal and value < 1_000:
            continue

        start, end = match.span()
        mentions.append(MoneyMention(
            value=round(value, 2),
            text=token,
            start=start,
            end=end,
            context=text[max(0, start - 28): min(len(text), end + 28)],
        ))

    return mentions


PERSONAL_WORDS = {
    "pribadi", "rumah", "keluarga", "anak", "istri", "suami", "jajan",
    "rokok", "liburan", "main", "netflix", "spotify", "bioskop",
}
BUSINESS_WORDS = {
    "toko", "warung", "usaha", "bisnis", "pelanggan", "supplier", "stok",
    "bahan", "jual", "jualan", "sewa", "gaji", "karyawan", "qris",
    "invoice", "vendor", "modal", "owner", "pemilik",
}
INCOME_WORDS = {
    "jual", "jualan", "penjualan", "laku", "omset", "omzet", "pendapatan",
    "terima bayaran", "bayaran", "dibayar pelanggan", "pelanggan bayar",
    "transfer masuk", "masuk dari", "invoice dibayar", "qris masuk",
    "cash masuk", "tunai masuk",
}
OWNER_CAPITAL_WORDS = {
    "setor modal", "tambahan modal", "modal dari pemilik", "modal owner",
    "modal usaha", "pemilik setor", "investasi pemilik",
}
OWNER_DRAW_WORDS = {
    "prive", "ambil uang usaha", "ambil kas", "tarik uang usaha",
    "uang usaha dipakai pribadi",
}
LOAN_RECEIPT_WORDS = {
    "pinjam uang", "dapat pinjaman", "terima pinjaman", "pinjaman bank",
    "utang bank cair", "kredit bank cair",
}
RECEIVABLE_COLLECTION_WORDS = {
    "terima piutang", "terima pembayaran piutang", "pembayaran piutang",
    "bayar piutang", "pelunasan piutang", "piutang dibayar",
}
DEBT_PAYMENT_WORDS = {
    "bayar utang", "bayar hutang", "cicil utang", "cicilan utang",
    "angsuran", "pelunasan utang", "lunasi utang",
}
DEBT_SPLIT_WORDS = {
    "sisa utang", "sisa hutang", "ngutang", "hutang dulu", "utang dulu",
    "tempo", "belum dibayar", "bayar sebagian", "separuh",
}
RECURRING_WORDS = {
    "bulanan", "langganan", "sewa", "gaji", "listrik", "internet",
    "air", "cicilan", "angsuran",
}


def _detect_business(text: str) -> bool:
    if _has_any(text, PERSONAL_WORDS) and not _has_any(text, BUSINESS_WORDS):
        return False
    return True


def _detect_income(text: str) -> bool:
    if _has_any(text, INCOME_WORDS):
        return True
    if "terima" in text and not _has_any(text, {"bayar", "beli", "tagihan"}):
        return True
    return False


def _classify_expense_account(text: str) -> tuple[str, str, str, bool, str]:
    """
    Returns: accounting_type, debit_account, category, is_pnl, sub_category.
    """
    # Deteksi pengeluaran pribadi/non-bisnis lebih awal
    if _has_any(text, PERSONAL_WORDS):
        return "other", "Prive", "Pengeluaran Pribadi", False, "Non-Bisnis"

    if _has_any(text, {"stok", "persediaan", "restock", "barang dagangan"}):
        return "asset_purchase", "Persediaan", "Pembelian Persediaan", False, "Persediaan"

    if _has_any(text, {"alat", "mesin", "kulkas", "kompor", "laptop", "komputer", "etalase", "kendaraan", "renovasi"}):
        return "asset_purchase", "Aset Tetap", "Pembelian Aset Tetap", False, "Aset tetap"

    if _has_any(text, {"bahan", "baku", "ayam", "daging", "sayur", "beras", "tepung", "minyak", "kopi", "susu", "gula", "bumbu", "kemasan"}):
        return "cogs", "HPP (Bahan Baku)", "Harga Pokok Penjualan (HPP)", True, "Bahan produksi"

    if _has_any(text, {"gaji", "upah", "karyawan", "pegawai", "freelancer", "thr"}):
        return "operational_expense", "Beban Gaji", "Beban SDM", True, "SDM"

    if _has_any(text, {"iklan", "ads", "promosi", "konten", "endorse", "marketing"}):
        return "operational_expense", "Beban Pemasaran", "Beban Pemasaran", True, "Pemasaran"

    if _has_any(text, {"sewa", "kontrakan", "ruko"}):
        return "operational_expense", "Beban Sewa", "Beban Operasional", True, "Sewa"

    if _has_any(text, {"listrik", "air", "internet", "wifi", "gas", "bensin", "transport", "ongkir", "parkir", "pulsa"}):
        return "operational_expense", "Beban Operasional", "Beban Operasional", True, "Operasional"

    return "operational_expense", "Beban Lain", "Beban Lain", True, "Lain-lain"


def _base_entry(
    amount: float,
    description: str,
    text: str,
    is_business: bool,
    confidence: float = 0.78,
) -> ClassifiedEntry:
    recurring = _has_any(text, RECURRING_WORDS)

    if _has_any(text, OWNER_CAPITAL_WORDS):
        return ClassifiedEntry(
            amount=amount,
            description=description,
            accounting_type="other",
            debit_account="Kas",
            credit_account="Modal Pemilik",
            type="income",
            category="Modal Pemilik",
            sub_category="Setoran modal",
            is_recurring=False,
            is_business=is_business,
            is_pnl=False,
            confidence=confidence,
            reasoning="Kas masuk dari setoran modal pemilik, bukan pendapatan usaha.",
        )

    if _has_any(text, LOAN_RECEIPT_WORDS):
        return ClassifiedEntry(
            amount=amount,
            description=description,
            accounting_type="other",
            debit_account="Kas",
            credit_account="Utang Bank",
            type="income",
            category="Pinjaman Diterima",
            sub_category="Kas dari pinjaman",
            is_recurring=False,
            is_business=is_business,
            is_pnl=False,
            confidence=confidence,
            reasoning="Kas masuk dari pinjaman, bukan pendapatan usaha.",
        )

    if _has_any(text, OWNER_DRAW_WORDS):
        return ClassifiedEntry(
            amount=amount,
            description=description,
            accounting_type="other",
            debit_account="Prive",
            credit_account="Kas",
            type="expense",
            category="Prive",
            sub_category="Pengambilan pemilik",
            is_recurring=False,
            is_business=is_business,
            is_pnl=False,
            confidence=confidence,
            reasoning="Kas keluar untuk prive/pengambilan pemilik, bukan beban usaha.",
        )

    if _has_any(text, RECEIVABLE_COLLECTION_WORDS):
        return ClassifiedEntry(
            amount=amount,
            description=description,
            accounting_type="receivable",
            debit_account="Kas",
            credit_account="Piutang",
            type="income",
            category="Penerimaan Piutang",
            sub_category="Pelunasan piutang",
            is_recurring=False,
            is_business=is_business,
            is_pnl=False,
            confidence=confidence,
            reasoning="Kas masuk dari pelunasan piutang, bukan pendapatan baru.",
        )

    if _has_any(text, DEBT_PAYMENT_WORDS):
        return ClassifiedEntry(
            amount=amount,
            description=description,
            accounting_type="debt_payment",
            debit_account="Utang Usaha",
            credit_account="Kas",
            type="expense",
            category="Pembayaran Utang",
            sub_category="Pelunasan utang",
            is_recurring=recurring,
            is_business=is_business,
            is_pnl=False,
            confidence=confidence,
            reasoning="Kas keluar untuk mengurangi utang, bukan beban baru.",
        )

    if _detect_income(text):
        if _has_any(text, {"piutang", "belum dibayar", "tempo"}):
            return ClassifiedEntry(
                amount=amount,
                description=description,
                accounting_type="revenue",
                debit_account="Piutang",
                credit_account="Pendapatan Usaha",
                type="income",
                category="Piutang",
                sub_category="Penjualan kredit",
                is_recurring=recurring,
                is_business=is_business,
                is_pnl=True,
                confidence=confidence,
                reasoning="Penjualan diakui sebagai pendapatan, kas belum masuk karena piutang.",
            )
        return ClassifiedEntry(
            amount=amount,
            description=description,
            accounting_type="revenue",
            debit_account="Kas",
            credit_account="Pendapatan Usaha",
            type="income",
            category="Pendapatan Usaha",
            sub_category="Penjualan",
            is_recurring=recurring,
            is_business=is_business,
            is_pnl=True,
            confidence=confidence,
            reasoning="Transaksi terdeteksi sebagai penjualan/pemasukan usaha.",
        )

    accounting_type, debit, category, is_pnl, sub_category = _classify_expense_account(text)
    return ClassifiedEntry(
        amount=amount,
        description=description,
        accounting_type=accounting_type,
        debit_account=debit,
        credit_account="Kas",
        type="expense",
        category=category,
        sub_category=sub_category,
        is_recurring=recurring,
        is_business=is_business,
        is_pnl=is_pnl,
        confidence=confidence,
        reasoning=f"Transaksi diklasifikasi sebagai {category}.",
    )


def classify_raw_transaction(raw_input: str, business_type: str = "general") -> dict[str, Any]:
    """
    Convert one raw Indonesian transaction sentence into one or more journal rows.
    """
    text = _norm(raw_input)
    mentions = extract_money_mentions(raw_input)
    is_business = _detect_business(text)

    if not mentions:
        return {
            "transactions": [],
            "reasoning": "Tidak ada nominal rupiah yang bisa diekstrak.",
            "confidence": 0.0,
            "money_mentions": [],
        }

    amounts = [m.value for m in mentions]
    primary_amount = max(amounts)
    description = raw_input.strip()

    base = _base_entry(
        amount=primary_amount,
        description=description,
        text=text,
        is_business=is_business,
        confidence=0.86 if len(mentions) == 1 else 0.78,
    )

    entries: list[ClassifiedEntry] = []

    # Split purchase: "beli alat 2jt, bayar 500rb, sisa utang".
    if (
        base.type == "expense"
        and base.accounting_type in {"operational_expense", "cogs", "asset_purchase"}
        and _has_any(text, DEBT_SPLIT_WORDS)
    ):
        paid_amount = None
        if len(amounts) >= 2:
            smaller = [a for a in amounts if a < primary_amount]
            paid_amount = max(smaller) if smaller else None
        elif "separuh" in text:
            paid_amount = primary_amount * 0.5

        if paid_amount and 0 < paid_amount < primary_amount:
            debt_amount = primary_amount - paid_amount
            cash_entry = ClassifiedEntry(**{
                **base.to_dict(),
                "amount": round(paid_amount, 2),
                "description": f"{description} (bagian tunai)",
                "credit_account": "Kas",
                "reasoning": f"Pembayaran tunai Rp {paid_amount:,.0f}; sisanya dicatat sebagai utang.",
                "confidence": 0.84,
            })
            debt_entry = ClassifiedEntry(**{
                **base.to_dict(),
                "amount": round(debt_amount, 2),
                "description": f"{description} (bagian utang)",
                "credit_account": "Utang Usaha",
                "reasoning": f"Sisa kewajiban Rp {debt_amount:,.0f} dicatat sebagai utang usaha.",
                "confidence": 0.84,
            })
            entries = [cash_entry, debt_entry]

    if not entries:
        entries = [base]

    return {
        "transactions": [e.to_dict() for e in entries],
        "reasoning": " | ".join(e.reasoning for e in entries if e.reasoning),
        "confidence": min(e.confidence for e in entries),
        "money_mentions": [asdict(m) for m in mentions],
        "business_type": business_type,
    }


def infer_transaction_date(raw_input: str, base_date: date | None = None) -> str:
    """Infer tanggal sederhana dari bahasa Indonesia; fallback ke hari ini."""
    text = _norm(raw_input)
    base = base_date or date.today()

    iso = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", text)
    if iso:
        year, month, day = (int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
        try:
            return date(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            pass

    slash = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](20\d{2}))?\b", text)
    if slash:
        day = int(slash.group(1))
        month = int(slash.group(2))
        year = int(slash.group(3)) if slash.group(3) else base.year
        try:
            return date(year, month, day).strftime("%Y-%m-%d")
        except ValueError:
            pass

    if "kemarin" in text:
        return (base - timedelta(days=1)).strftime("%Y-%m-%d")
    if "lusa" in text:
        # Transaksi aktual seharusnya tidak diproyeksikan ke masa depan.
        return base.strftime("%Y-%m-%d")
    return base.strftime("%Y-%m-%d")


def split_transaction_clauses(raw_input: str) -> list[str]:
    """Pecah input panjang menjadi klausa transaksi tanpa memecah frasa utang parsial."""
    text = (raw_input or "").strip()
    if not text:
        return []

    clauses = [part.strip() for part in CLAUSE_SPLIT_RE.split(text) if part.strip()]
    if len(clauses) <= 1:
        return [text]

    # Gabungkan klausa lanjutan yang menjelaskan pembayaran sebagian.
    merged: list[str] = []
    for clause in clauses:
        lower = _norm(clause)
        if merged and _has_any(lower, DEBT_SPLIT_WORDS | {"sisa"}):
            merged[-1] = f"{merged[-1]}, {clause}"
        else:
            merged.append(clause)
    return merged


def classify_raw_transactions(raw_input: str, business_type: str = "general") -> dict[str, Any]:
    """
    Classify a free-form input that may contain multiple transactions.
    Deterministic fallback for Parser Agent when LLM is unavailable.
    """
    clauses = split_transaction_clauses(raw_input)
    all_entries: list[dict[str, Any]] = []
    reasoning: list[str] = []
    mentions: list[dict[str, Any]] = []
    tx_date_default = infer_transaction_date(raw_input)

    for clause in clauses:
        if not extract_money_mentions(clause):
            continue
        result = classify_raw_transaction(clause, business_type=business_type)
        clause_date = infer_transaction_date(clause)
        for entry in result.get("transactions", []):
            entry = dict(entry)
            entry["date"] = clause_date or tx_date_default
            all_entries.append(entry)
        if result.get("reasoning"):
            reasoning.append(result["reasoning"])
        mentions.extend(result.get("money_mentions", []))

    if not all_entries and raw_input:
        result = classify_raw_transaction(raw_input, business_type=business_type)
        for entry in result.get("transactions", []):
            entry = dict(entry)
            entry["date"] = tx_date_default
            all_entries.append(entry)
        if result.get("reasoning"):
            reasoning.append(result["reasoning"])
        mentions.extend(result.get("money_mentions", []))

    return {
        "transactions": all_entries,
        "reasoning": " | ".join(reasoning) if reasoning else "Tidak ada transaksi valid yang bisa diklasifikasi.",
        "confidence": min((e.get("confidence", 0.0) for e in all_entries), default=0.0),
        "money_mentions": mentions,
        "business_type": business_type,
    }


def safe_finance_narrative(summary: dict[str, Any], cash_balance: float, health_score: float, runway_days: float) -> str:
    income = summary.get("total_income", 0) or 0
    expense = summary.get("total_expense", 0) or 0
    net = income - expense
    revenue = summary.get("journal_revenue", 0) or 0
    pnl_expense = summary.get("journal_expense", 0) or summary.get("operational_expense", 0) or 0
    margin = ((revenue - pnl_expense) / revenue * 100) if revenue > 0 else 0

    if summary.get("total_tx", 0) == 0:
        return "Belum ada transaksi bulan ini. Mulai catat pemasukan dan pengeluaran agar CFO Sentinel bisa membaca pola kas."

    if cash_balance <= 0:
        return (
            f"Kas bisnis sedang negatif atau kosong (Rp {cash_balance:,.0f}); prioritas hari ini adalah menunda pengeluaran non-esensial "
            f"dan mengejar kas masuk. Margin operasional terbaca {margin:.1f}% dari data yang sudah diklasifikasi."
        )

    if runway_days < 14:
        return (
            f"Kas masih ada Rp {cash_balance:,.0f}, tetapi runway hanya sekitar {runway_days:.0f} hari. "
            f"Arus kas bulan ini Rp {net:+,.0f}; segera tekan pengeluaran yang tidak langsung menghasilkan penjualan."
        )

    if net < 0:
        return (
            f"Bisnis masih punya kas Rp {cash_balance:,.0f}, namun arus kas bulan ini negatif Rp {abs(net):,.0f}. "
            f"Periksa kategori pengeluaran terbesar sebelum defisit menjadi kebiasaan."
        )

    return (
        f"Kondisi kas relatif terkendali: saldo Rp {cash_balance:,.0f}, arus kas bulan ini Rp {net:+,.0f}, "
        f"dan runway sekitar {runway_days:.0f} hari. Tetap pantau biaya rutin agar margin tidak terkikis."
    )


def estimate_health_score(summary: dict[str, Any], cash_balance: float) -> float:
    """Fast deterministic health score for API fallback and agent validation."""
    cash_in = summary.get("total_income", 0) or 0
    cash_out = summary.get("total_expense", 0) or 0
    revenue = summary.get("journal_revenue", 0) or 0
    pnl_expense = summary.get("journal_expense", 0) or 0
    tx_count = summary.get("total_tx", 0) or 0
    classified = summary.get("classified_tx", 0) or 0
    active_days = max(summary.get("active_days", 1) or 1, 1)

    if tx_count == 0:
        return 0.0

    monthly_burn = cash_out
    if monthly_burn > 0 and cash_balance > 0:
        runway = (cash_balance / monthly_burn) * 30
    else:
        runway = 0 if cash_balance <= 0 else 90
    runway_score = min(35, (min(runway, 60) / 60) * 35)

    if revenue > 0:
        margin = ((revenue - pnl_expense) / revenue) * 100
        margin_score = max(0, min(25, (margin / 25) * 25))
    else:
        margin_score = 0

    net = cash_in - cash_out
    if cash_out <= 0 and cash_in > 0:
        cashflow_score = 20
    elif net >= 0:
        cashflow_score = 20
    else:
        cashflow_score = max(0, 20 + (net / max(cash_out, 1)) * 20)

    classification_rate = classified / tx_count if tx_count else 0
    data_quality_score = min(10, ((min(tx_count, 3) / 3) * 6) + (classification_rate * 4))

    daily_burn = cash_out / active_days
    buffer_days = cash_balance / daily_burn if daily_burn > 0 and cash_balance > 0 else 0
    buffer_score = min(10, (min(buffer_days, 30) / 30) * 10)

    return round(min(100, max(0, runway_score + margin_score + cashflow_score + data_quality_score + buffer_score)), 1)


def build_dashboard_brief(
    summary: dict[str, Any],
    cash_balance: float,
    health_score: float,
    runway_days: float,
    anomalies: list[dict[str, Any]] | None = None,
    spending: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    anomalies = anomalies or []
    spending = spending or []
    income = summary.get("total_income", 0) or 0
    expense = summary.get("total_expense", 0) or 0
    net = income - expense
    tx_count = summary.get("total_tx", 0) or 0
    classified = summary.get("classified_tx", 0) or 0
    classification_rate = (classified / tx_count * 100) if tx_count else 0

    insights: list[str] = []
    actions: list[dict[str, str]] = []

    if runway_days and runway_days < 14:
        insights.append(f"Runway kas kritis: sekitar {runway_days:.0f} hari.")
        actions.append({
            "urgency": "IMMEDIATE",
            "title": "Bekukan pengeluaran non-esensial 7 hari",
            "description": "Tunda pembelian aset, promosi eksperimen, dan belanja yang tidak langsung menaikkan penjualan.",
            "expected_impact": "Menambah napas kas jangka pendek.",
        })
    elif runway_days and runway_days < 30:
        insights.append(f"Runway kas pendek: sekitar {runway_days:.0f} hari.")
        actions.append({
            "urgency": "THIS_WEEK",
            "title": "Susun daftar biaya yang bisa dipotong",
            "description": "Mulai dari biaya langganan, promosi kecil yang tidak terukur, dan stok lambat bergerak.",
            "expected_impact": "Mengurangi burn rate harian.",
        })

    if net < 0:
        insights.append(f"Arus kas bulan ini negatif Rp {abs(net):,.0f}.")
        actions.append({
            "urgency": "THIS_WEEK",
            "title": "Kejar kas masuk paling cepat",
            "description": "Tagih piutang, dorong paket fast-moving, atau buat promo margin sehat untuk stok yang cepat laku.",
            "expected_impact": "Menutup defisit kas bulan berjalan.",
        })

    if anomalies:
        top = anomalies[0]
        insights.append(f"Anomali terbesar: {top.get('category', 'kategori')} ({top.get('severity', 'LOW')}).")
        actions.append({
            "urgency": "THIS_WEEK",
            "title": f"Audit biaya {top.get('category', 'terbesar')}",
            "description": top.get("suggested_action") or "Cek bukti transaksi dan bandingkan dengan kebutuhan operasional.",
            "expected_impact": "Mengurangi risiko pemborosan atau salah klasifikasi.",
        })

    if spending:
        top_spend = spending[0]
        insights.append(f"Kategori kas keluar terbesar: {top_spend.get('category')} Rp {top_spend.get('total', 0):,.0f}.")

    if tx_count and classification_rate < 80:
        insights.append(f"Kualitas data belum matang: {classification_rate:.0f}% transaksi sudah diklasifikasi.")
        actions.append({
            "urgency": "THIS_WEEK",
            "title": "Rapikan transaksi pending",
            "description": "Edit transaksi yang masih bernilai Rp 0 atau kategori Pending agar analisis tidak bias.",
            "expected_impact": "Meningkatkan akurasi skor dan saran CFO.",
        })

    if not insights:
        insights.append("Belum ada sinyal risiko besar dari data yang tercatat.")
        actions.append({
            "urgency": "THIS_MONTH",
            "title": "Pertahankan disiplin pencatatan harian",
            "description": "Catat transaksi pada hari yang sama agar pola kas dan anomali terbaca lebih cepat.",
            "expected_impact": "Membuat proyeksi kas semakin stabil.",
        })

    return {
        "insights": insights[:5],
        "next_actions": actions[:4],
        "data_quality": {
            "transaction_count": tx_count,
            "classified_count": classified,
            "classification_rate": round(classification_rate, 1),
            "pending_count": max(0, tx_count - classified),
        },
        "risk_posture": (
            "CRITICAL" if cash_balance <= 0 or (runway_days and runway_days < 7)
            else "WATCH" if net < 0 or anomalies or (runway_days and runway_days < 30)
            else "STABLE"
        ),
    }
