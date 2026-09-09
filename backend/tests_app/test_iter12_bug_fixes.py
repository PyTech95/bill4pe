"""Iteration 12 — Verifies BUG1 (direct UPI-to-vendor) & BUG2 (bill gen wallet-topup fallback)."""
import os
import uuid
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
API = f"{BASE}/api"


@pytest.fixture(scope="module")
def auth():
    phone = "9999999999"
    requests.post(f"{API}/auth/otp/request", json={"phone": phone}, timeout=30)
    r = requests.post(f"{API}/auth/otp/verify", json={"phone": phone, "otp": "123456"}, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json()["token"]
    return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# ------------- Bug 1: paid expense stores vendor UPI + UTR -------------

class TestBug1DirectUpiExpense:
    def test_payments_config_razorpay_disabled(self):
        r = requests.get(f"{API}/payments/config", timeout=30)
        assert r.status_code == 200
        # As per env, Razorpay is intentionally NOT configured for this iteration.
        assert r.json().get("enabled") is False

    def test_create_paid_expense_with_vendor_upi(self, auth):
        vendor_vpa = "suresh@oksbi"
        utr = f"UTR{uuid.uuid4().hex[:10].upper()}"
        payload = {
            "category": "food",
            "sub_category": "Lunch",
            "items": [{"name": "Thali", "quantity": 1, "unit_price": 120.0}],
            "notes": "TEST_iter12_bug1",
            "payment": {
                "merchant_name": "Suresh Tiffin",
                "merchant_upi": vendor_vpa,
                "transaction_id": utr,
                "amount": 120.0,
                "payment_method": "UPI",
                "payment_status": "paid",
            },
        }
        r = requests.post(f"{API}/expenses", headers=auth, json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        created = r.json()
        eid = created["id"]
        assert created.get("payment", {}).get("merchant_upi") == vendor_vpa
        assert created.get("payment", {}).get("transaction_id") == utr
        assert created.get("payment", {}).get("payment_status") == "paid"

        # Persistence check (GET)
        r = requests.get(f"{API}/expenses/{eid}", headers=auth, timeout=30)
        assert r.status_code == 200
        exp = r.json()
        assert exp["payment"]["merchant_upi"] == vendor_vpa
        assert exp["payment"]["transaction_id"] == utr
        assert exp["payment"]["payment_status"] == "paid"
        # Persist so next test can reuse
        pytest.paid_expense_id = eid


# ------------- Bug 2: bill generation, wallet-funded + wallet-short fallback -------------

class TestBug2BillGeneration:
    def _create_expense(self, auth, total_items):
        payload = {
            "category": "food",
            "sub_category": "Lunch",
            "items": [{"name": "Item", "quantity": 1, "unit_price": total_items}],
            "notes": "TEST_iter12_bug2",
            "payment": {
                "merchant_name": "Vendor X",
                "merchant_upi": "vendorx@okhdfc",
                "transaction_id": f"UTR{uuid.uuid4().hex[:10].upper()}",
                "amount": total_items,
                "payment_method": "UPI",
                "payment_status": "paid",
            },
        }
        r = requests.post(f"{API}/expenses", headers=auth, json=payload, timeout=30)
        assert r.status_code in (200, 201), r.text
        return r.json()["id"]

    def test_bill_generate_with_wallet_funded(self, auth):
        # Fund wallet plenty
        requests.post(f"{API}/wallet/recharge", headers=auth, json={"amount": 500}, timeout=30)
        eid = self._create_expense(auth, 200.0)
        r = requests.post(f"{API}/bills/{eid}/generate", headers=auth, json={}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("bill_id", "").startswith("B4P-")
        assert body.get("fee_paid_via") == "wallet"

        # Verify persistence
        r = requests.get(f"{API}/expenses/{eid}", headers=auth, timeout=30)
        assert r.status_code == 200
        exp = r.json()
        assert exp.get("bill_generated") is True
        assert exp.get("bill_id") == body["bill_id"]

        # PDF downloads OK
        r = requests.get(f"{API}/bills/{eid}/pdf", headers=auth, timeout=60)
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF" or "application/pdf" in r.headers.get("content-type", "").lower()

    def test_bill_generate_wallet_short_then_topup(self, auth):
        # Drain wallet to near-zero by creating an expensive expense & generating a bill?
        # Simpler: check current balance; if not zero, top-up a huge expense that requires more fee.
        w = requests.get(f"{API}/wallet", headers=auth, timeout=30).json()
        bal = float(w.get("balance", 0.0))
        # We want fee > bal. Fee = max(1, 1% of total). Choose total=big so fee > bal.
        # If bal>0, pick total so 1% * total = bal + 50 → total = (bal+50)*100
        total_items = (bal + 50.0) * 100.0
        eid = self._create_expense(auth, total_items)
        # 1st attempt: wallet short → expect 402
        r = requests.post(f"{API}/bills/{eid}/generate", headers=auth, json={}, timeout=30)
        assert r.status_code == 402, f"expected 402 but got {r.status_code}: {r.text}"
        assert "insufficient" in r.text.lower()

        # Simulate frontend fallback: top up wallet by shortfall then retry.
        fee = max(1.0, round(total_items * 0.01, 2))
        shortfall = max(1.0, round(fee - bal + 0.5, 2))
        # Cap to 10000 (max recharge per txn)
        shortfall = min(shortfall, 10000.0)
        r = requests.post(f"{API}/wallet/recharge", headers=auth, json={"amount": shortfall}, timeout=30)
        assert r.status_code == 200, r.text

        # Retry generate (should now succeed if we recharged enough)
        # If fee > 10000 the shortfall cap bites; skip in that case.
        if fee <= 10000 + bal:
            r = requests.post(f"{API}/bills/{eid}/generate", headers=auth, json={}, timeout=30)
            assert r.status_code == 200, r.text
            body = r.json()
            assert body.get("bill_id", "").startswith("B4P-")
            assert body.get("fee_paid_via") == "wallet"

    def test_razorpay_endpoints_blocked_when_disabled(self, auth):
        # /payments/razorpay/order must 503 since Razorpay not configured — proves the
        # frontend cannot silently route the FEE via Razorpay in this env.
        r = requests.post(
            f"{API}/payments/razorpay/order",
            headers=auth,
            json={"amount": 1.0, "purpose": "bill_fee"},
            timeout=30,
        )
        assert r.status_code == 503, f"expected 503 got {r.status_code}: {r.text}"
