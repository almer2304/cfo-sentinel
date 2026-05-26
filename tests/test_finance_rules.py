from core.finance_rules import (
    classify_raw_transaction,
    classify_raw_transactions,
    extract_money_mentions,
)


def test_extracts_indonesian_money_without_quantity_noise():
    mentions = extract_money_mentions("Laku jualan nasi 10 porsi 150rb")
    assert [m.value for m in mentions] == [150000]


def test_does_not_parse_dates_or_quantities_as_money():
    mentions = extract_money_mentions("Tanggal 2026-05-26 laku 10 porsi 150rb")
    assert [m.value for m in mentions] == [150000]


def test_classifies_cash_sale_as_revenue():
    result = classify_raw_transaction("Laku jualan nasi goreng 150rb")
    tx = result["transactions"][0]

    assert tx["type"] == "income"
    assert tx["accounting_type"] == "revenue"
    assert tx["debit_account"] == "Kas"
    assert tx["credit_account"] == "Pendapatan Usaha"
    assert tx["amount"] == 150000


def test_classifies_inventory_purchase_as_asset_not_expense():
    result = classify_raw_transaction("Beli stok barang 1.5jt")
    tx = result["transactions"][0]

    assert tx["type"] == "expense"
    assert tx["accounting_type"] == "asset_purchase"
    assert tx["debit_account"] == "Persediaan"
    assert tx["credit_account"] == "Kas"
    assert tx["is_pnl"] is False


def test_listrik_is_business_operational_not_personal_istri_match():
    result = classify_raw_transaction("Bayar listrik 450rb")
    tx = result["transactions"][0]

    assert tx["is_business"] is True
    assert tx["category"] == "Beban Operasional"


def test_splits_partial_debt_purchase():
    result = classify_raw_transaction("Beli alat 2jt bayar 500rb sisa utang")
    entries = result["transactions"]

    assert len(entries) == 2
    assert sum(e["amount"] for e in entries) == 2_000_000
    assert entries[0]["credit_account"] == "Kas"
    assert entries[0]["amount"] == 500_000
    assert entries[1]["credit_account"] == "Utang Usaha"
    assert entries[1]["amount"] == 1_500_000


def test_receivable_collection_is_cash_not_new_revenue():
    result = classify_raw_transaction("Terima pembayaran piutang pelanggan 750rb")
    tx = result["transactions"][0]

    assert tx["type"] == "income"
    assert tx["accounting_type"] == "receivable"
    assert tx["debit_account"] == "Kas"
    assert tx["credit_account"] == "Piutang"
    assert tx["is_pnl"] is False


def test_credit_sale_is_revenue_but_not_cash_in():
    result = classify_raw_transaction("Jual tempo ke pelanggan 2jt belum dibayar")
    tx = result["transactions"][0]

    assert tx["accounting_type"] == "revenue"
    assert tx["debit_account"] == "Piutang"
    assert tx["credit_account"] == "Pendapatan Usaha"
    assert tx["is_pnl"] is True


def test_owner_capital_is_not_revenue():
    result = classify_raw_transaction("Setor modal usaha 5jt")
    tx = result["transactions"][0]

    assert tx["debit_account"] == "Kas"
    assert tx["credit_account"] == "Modal Pemilik"
    assert tx["is_pnl"] is False


def test_fallback_parser_handles_multiple_transactions():
    result = classify_raw_transactions(
        "beli bahan baku 1.5jt, bayar listrik 450rb, terima bayaran pelanggan 3.2jt"
    )
    transactions = result["transactions"]

    assert len(transactions) == 3
    assert [t["amount"] for t in transactions] == [1_500_000, 450_000, 3_200_000]


def test_fallback_parser_does_not_merge_normal_paid_invoice():
    result = classify_raw_transactions("bayar listrik 450rb, invoice dibayar pelanggan 1jt")
    transactions = result["transactions"]

    assert len(transactions) == 2
    assert transactions[0]["credit_account"] == "Kas"
    assert transactions[1]["debit_account"] == "Kas"
