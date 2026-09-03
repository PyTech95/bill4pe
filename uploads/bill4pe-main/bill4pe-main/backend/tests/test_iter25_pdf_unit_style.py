"""Iteration 25 — unit-level guard on pdf.py table styling when fee_amt == 0.

pdf.py applies fee-row TableStyle commands under `if show_fee:` (not
`if show_fee and fee_amt > 0`), so a corporate bill (show_fee=True, fee=0)
styles rows -3/-2 which are actual item/header rows. Verify it does not crash
for small item counts.
"""
import sys

sys.path.insert(0, "/app/backend")

from services.pdf import build_pdf_bytes  # noqa: E402

USER = {"name": "TEST Corp Admin", "email": "test_corp@example.com",
        "user_type": "corporate", "corporate_name": "TEST Corp Pvt Ltd"}


def _exp(items, fee):
    return {
        "id": "unit-1", "bill_id": "BILL-TEST-0001", "category": "food",
        "sub_category": "restaurant", "items": items,
        "total": sum(i["quantity"] * i["unit_price"] for i in items),
        "bill_generated": True, "bill_fee": fee,
        "payment": {"transaction_id": "B4P-TEST", "payment_method": "UPI",
                    "payment_status": "paid", "payee_name": "TEST Stall",
                    "payee_upi": "test@ybl"},
    }


def test_zero_fee_single_item_pdf_renders():
    pdf = build_pdf_bytes(_exp([{"name": "TEST_a", "quantity": 1, "unit_price": 490.0}], 0.0), USER)
    assert pdf[:4] == b"%PDF" and len(pdf) > 1000


def test_zero_fee_no_items_pdf_renders():
    pdf = build_pdf_bytes(_exp([], 0.0), USER)
    assert pdf[:4] == b"%PDF" and len(pdf) > 1000


def test_none_fee_falls_back_to_calc():
    # bill_fee missing (legacy doc) -> fee computed, fee rows rendered
    e = _exp([{"name": "TEST_a", "quantity": 1, "unit_price": 1000.0}], None)
    e.pop("bill_fee")
    pdf = build_pdf_bytes(e, {"name": "TEST Indiv", "email": "i@example.com",
                              "user_type": "individual"})
    assert pdf[:4] == b"%PDF"
