from core.finance_rules import classify_raw_transaction, extract_money_mentions


def test_extracts_indonesian_money_without_quantity_noise():
    mentions = extract_money_mentions("Laku jualan nasi 10 porsi 150rb")
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
