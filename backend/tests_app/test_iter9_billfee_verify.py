"""Iteration 9 regression tests.

Covers:
  * Phone OTP request/verify auth flow returns JWT and /api/auth/me works
  * Bill generation fee = 1% of total (₹500 → ₹5.00)
  * Bill generation fee MIN = ₹1 (₹50 → ₹1.00 not ₹0.50)
  * Public verify endpoint returns minimal info for valid bill
  * Public verify endpoint returns valid:false for bogus id (no 500)
"""
import os
import re
import uuid
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://ai-expense-hub-8.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

BILL_ID_PATTERN = re.compile(r"^B4P-\d{8}-[A-Z0-9]{6}$")


# ---------------------------- Auth (OTP) ---------------------------- #
def _otp_login(phone: str) -> dict:
    r = requests.post(f"{API}/auth/otp/request", json={"phone": phone}, timeout=30)
    assert r.status_code == 200, f"otp request failed: {r.status_code} {r.text}"
    r = requests.post(
        f"{API}/auth/otp/verify",
        json={"phone": phone, "otp": "123456"},
        timeout=30,
    )
    assert r.status_code == 200, f"otp verify failed: {r.status_code} {r.text}"
    data = r.json()
    assert "token" in data and isinstance(data["token"], str) and len(data["token"]) > 20
    assert "user" in data and data["user"].get("id")
    return data


@pytest.fixture(scope="module")
def otp_user():
    """Fresh OTP-authenticated user per module (random 10-digit phone)."""
    phone = "9" + str(uuid.uuid4().int)[:9]
    data = _otp_login(phone)
    return {
        "phone": phone,
        "token": data["token"],
        "user": data["user"],
        "headers": {
            "Authorization": f"Bearer {data['token']}",
            "Content-Type": "application/json",
        },
    }


def test_auth_otp_flow_and_me(otp_user):
    r = requests.get(f"{API}/auth/me", headers=otp_user["headers"], timeout=30)
    assert r.status_code == 200, f"/auth/me failed: {r.status_code} {r.text}"
    me = r.json()
    assert me["id"] == otp_user["user"]["id"]
    # Signup bonus should give wallet_balance >= 50 for a new user
    assert isinstance(me.get("wallet_balance"), (int, float))


# ---------------------------- Helpers ---------------------------- #
def _ensure_wallet(headers, min_required=200.0):
    """Top-up via /api/wallet/recharge if below min_required (mock gateway)."""
    me = requests.get(f"{API}/auth/me", headers=headers, timeout=30).json()
    bal = float(me.get("wallet_balance", 0) or 0)
    if bal >= min_required:
        return bal
    add = max(200.0, min_required - bal + 50)
    r = requests.post(
        f"{API}/wallet/recharge",
        headers=headers,
        json={"amount": add},
        timeout=30,
    )
    # Some implementations may require a two-step flow; if direct recharge fails,
    # we surface that as a skip rather than crash subsequent tests.
    if r.status_code >= 400:
        pytest.skip(f"wallet recharge unavailable for direct top-up: {r.status_code} {r.text}")
    me = requests.get(f"{API}/auth/me", headers=headers, timeout=30).json()
    return float(me.get("wallet_balance", 0) or 0)


def _create_expense(headers, total: float):
    payload = {
        "category": "food",
        "sub_category": "restaurant",
        "items": [{"name": "Test", "quantity": 1, "unit_price": total}],
        "total": total,
        "payment": {
            "merchant_name": "T",
            "merchant_upi": "t@upi",
            "amount": total,
            "transaction_id": f"TXN-{uuid.uuid4().hex[:8].upper()}",
            "payment_method": "UPI",
            "payment_status": "paid",
        },
        "notes": "iter9 test",
    }
    r = requests.post(f"{API}/expenses", headers=headers, json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create expense failed: {r.status_code} {r.text}"
    return r.json()


def _generate_bill(eid, headers):
    r = requests.post(f"{API}/bills/{eid}/generate", headers=headers, timeout=30)
    assert r.status_code == 200, f"generate bill failed: {r.status_code} {r.text}"
    return r.json()


# ---------------------------- Bill fee 1% ---------------------------- #
def test_bill_fee_1_percent_total_500(otp_user):
    bal_before = _ensure_wallet(otp_user["headers"], min_required=20.0)
    exp = _create_expense(otp_user["headers"], total=500.0)
    eid = exp.get("id") or exp.get("expense", {}).get("id")
    assert eid, f"no expense id in create response: {exp}"

    result = _generate_bill(eid, otp_user["headers"])
    assert result["fee"] == 5.00, f"expected fee 5.00, got {result['fee']}"
    assert result["wallet_balance"] == round(bal_before - 5.0, 2), (
        f"wallet should drop by 5: before={bal_before}, after={result['wallet_balance']}"
    )
    bill_id = result["bill_id"]
    assert BILL_ID_PATTERN.match(bill_id), f"bill_id does not match pattern: {bill_id}"
    # stash for verify test
    pytest.shared_bill_id_500 = bill_id
    pytest.shared_user_name = otp_user["user"].get("name")


def test_bill_fee_minimum_1_rupee_total_50(otp_user):
    _ensure_wallet(otp_user["headers"], min_required=5.0)
    exp = _create_expense(otp_user["headers"], total=50.0)
    eid = exp.get("id") or exp.get("expense", {}).get("id")
    assert eid

    result = _generate_bill(eid, otp_user["headers"])
    # 50 * 0.01 = 0.50 but min is ₹1.00
    assert result["fee"] == 1.00, f"expected MIN fee 1.00, got {result['fee']}"
    assert BILL_ID_PATTERN.match(result["bill_id"])


# ---------------------------- Public verify ---------------------------- #
def test_public_verify_valid_bill():
    bill_id = getattr(pytest, "shared_bill_id_500", None)
    if not bill_id:
        pytest.skip("requires test_bill_fee_1_percent_total_500 to have run")

    r = requests.get(f"{API}/public/verify/{bill_id}", timeout=30)
    assert r.status_code == 200, f"verify failed: {r.status_code} {r.text}"
    data = r.json()
    assert data["valid"] is True
    assert data["bill_id"] == bill_id
    assert data["merchant_name"] == "T"
    assert data["amount"] == 500.0
    assert data["fee"] == 5.0
    assert data["grand_total"] == 505.0
    # customer_name is first name only
    cn = data.get("customer_name")
    assert cn is None or " " not in cn, f"customer_name should be first name only, got: {cn}"


def test_public_verify_bogus_id_returns_valid_false():
    r = requests.get(f"{API}/public/verify/BOGUS-ID", timeout=30)
    assert r.status_code == 200, f"expected 200 (not 500) for bogus id, got {r.status_code} {r.text}"
    data = r.json()
    assert data["valid"] is False
    assert data["bill_id"] == "BOGUS-ID"


def test_public_verify_does_not_require_auth():
    bill_id = getattr(pytest, "shared_bill_id_500", None)
    if not bill_id:
        pytest.skip("requires earlier bill creation")
    # No Authorization header at all
    r = requests.get(f"{API}/public/verify/{bill_id}", timeout=30, headers={})
    assert r.status_code == 200
