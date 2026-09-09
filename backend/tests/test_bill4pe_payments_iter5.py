"""Bill4Pe payments/webhook reconciliation regression (iter 5).

Validates the exact-once bill-generation invariant using SYNTHETIC orders +
real Razorpay HMAC signatures. NEVER calls the live Razorpay API — synthetic
payment_orders docs are inserted directly into MongoDB and captured via signed
webhook / verify payloads.
"""
import asyncio
import concurrent.futures
import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import datetime, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE_URL:
    for line in open("/app/frontend/.env").read().splitlines():
        if line.startswith("REACT_APP_BACKEND_URL="):
            BASE_URL = line.split("=", 1)[1].strip().rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bill4pe_database")

RZP_KEY_SECRET = "IipAU9vseV7vh5THLkJJJ10L"
RZP_WEBHOOK_SECRET = "36dcdf9d7e978507054f7dce7318040a0f4d9db6b3b9b3a3"

SUPER_EMAIL = "ujjwal@bill4pe.com"
SUPER_PW = "Bill4Pe@2026"


# ---------------- Helpers ----------------
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sign_checkout(order_id: str, payment_id: str) -> str:
    return hmac.new(RZP_KEY_SECRET.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256).hexdigest()


def sign_webhook(raw: bytes) -> str:
    return hmac.new(RZP_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()


def make_webhook_body(order_id: str, payment_id: str, amount_paise: int, event="payment.captured"):
    body = {
        "event": event,
        "payload": {
            "payment": {"entity": {
                "id": payment_id, "order_id": order_id,
                "amount": amount_paise, "status": "captured",
            }}
        },
    }
    raw = json.dumps(body, separators=(",", ":")).encode()
    return raw, sign_webhook(raw)


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    return c[DB_NAME]


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def user_ctx(client):
    email = f"test_pay_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(f"{API}/auth/register", json={
        "email": email, "password": "Test@1234", "name": "Pay Tester",
    })
    assert r.status_code == 200, r.text
    j = r.json()
    return {"email": email, "token": j["token"], "user_id": j["user"]["id"]}


@pytest.fixture(scope="module")
def user_client(user_ctx):
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json",
                      "Authorization": f"Bearer {user_ctx['token']}"})
    return s


@pytest.fixture(scope="module")
def other_user_client(client):
    email = f"other_{uuid.uuid4().hex[:8]}@example.com"
    r = client.post(f"{API}/auth/register", json={
        "email": email, "password": "Test@1234", "name": "Other",
    })
    assert r.status_code == 200
    tok = r.json()["token"]
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def super_client(client):
    r = client.post(f"{API}/auth/login", json={"email": SUPER_EMAIL, "password": SUPER_PW})
    assert r.status_code == 200, r.text
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json",
                      "Authorization": f"Bearer {r.json()['token']}"})
    return s


def make_merchant_order(mongo, user_id, amount=1500.0):
    tid = str(uuid.uuid4())
    order_id = f"order_{uuid.uuid4().hex[:14]}"
    doc = {
        "id": tid,
        "order_id": order_id,
        "user_id": user_id,
        "purpose": "merchant_payment",
        "amount": amount,
        "amount_paise": int(round(amount * 100)),
        "payment_status": "created",
        "status": "created",
        "bill_status": "pending",
        "settlement_status": "not_required",
        "credited": False,
        "expense_id": None,
        "expense_draft": {
            "category": "food",
            "sub_category": "dinner",
            "items": [
                {"name": "Meal", "quantity": 1, "unit_price": amount - 50.0},
                {"name": "Tea", "quantity": 5, "unit_price": 10.0},
            ],
            "payment": {
                "merchant_name": "Synthetic Cafe",
                "merchant_upi": "synthcafe@upi",
                "amount": amount,
                "payment_method": "Razorpay",
            },
        },
        "razorpay_payment_id": None,
        "created_at": now_iso(),
    }
    mongo.payment_orders.insert_one(doc)
    return tid, order_id


def make_wallet_order(mongo, user_id, amount=200.0):
    tid = str(uuid.uuid4())
    order_id = f"order_{uuid.uuid4().hex[:14]}"
    mongo.payment_orders.insert_one({
        "id": tid, "order_id": order_id, "user_id": user_id,
        "purpose": "wallet_recharge", "amount": amount,
        "amount_paise": int(round(amount * 100)),
        "payment_status": "created", "status": "created",
        "bill_status": "pending", "settlement_status": "not_required",
        "credited": False, "expense_id": None, "expense_draft": None,
        "razorpay_payment_id": None, "created_at": now_iso(),
    })
    return tid, order_id


# ---------------- T0: Config / health / providers ----------------
def test_payments_config_live(client):
    r = client.get(f"{API}/payments/config")
    assert r.status_code == 200
    j = r.json()
    assert j["enabled"] is True
    assert j["mode"] == "live"


def test_health_providers_shows_configured(client):
    r = client.get(f"{API}/health/providers")
    assert r.status_code == 200
    j = r.json()
    assert j["payments"]["razorpay_configured"] is True
    assert j["payments"]["webhook_secret_set"] is True


# ---------------- T1: Normal verify -> bill ----------------
def test_t1_verify_generates_exactly_one_bill(mongo, user_ctx, user_client):
    tid, order_id = make_merchant_order(mongo, user_ctx["user_id"], amount=1500.0)
    payment_id = f"pay_{uuid.uuid4().hex[:14]}"
    sig = sign_checkout(order_id, payment_id)

    r = user_client.post(f"{API}/payments/verify", json={
        "transaction_id": tid, "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id, "razorpay_signature": sig,
    })
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["success"] is True
    assert j["bill_id"], f"no bill_id in {j}"
    assert re.match(r"^BILL-\d{4}-\d{6}$", j["bill_id"]), j["bill_id"]

    # exactly one expense
    n = mongo.expenses.count_documents({"transaction_id": tid})
    assert n == 1, f"expected exactly one expense, got {n}"

    # status endpoint
    st = user_client.get(f"{API}/payments/{tid}/status").json()
    assert st["payment_status"] == "captured"
    assert st["bill_status"] == "generated"

    # bill snapshot frozen
    exp = mongo.expenses.find_one({"transaction_id": tid})
    assert exp["bill_snapshot"], "bill_snapshot missing"
    assert exp["bill_id"] == j["bill_id"]


# ---------------- T2: App-close recovery via webhook only ----------------
def test_t2_webhook_only_generates_bill(mongo, user_ctx, user_client):
    tid, order_id = make_merchant_order(mongo, user_ctx["user_id"], amount=800.0)
    payment_id = f"pay_{uuid.uuid4().hex[:14]}"
    raw, sig = make_webhook_body(order_id, payment_id, 80000)

    r = requests.post(
        f"{API}/webhooks/razorpay", data=raw,
        headers={"Content-Type": "application/json",
                 "X-Razorpay-Signature": sig,
                 "X-Razorpay-Event-Id": f"evt_{uuid.uuid4().hex[:10]}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"

    n = mongo.expenses.count_documents({"transaction_id": tid})
    assert n == 1
    st = user_client.get(f"{API}/payments/{tid}/status").json()
    assert st["payment_status"] == "captured"
    assert st["bill_status"] == "generated"
    assert st["bill_id"]


# ---------------- T3: Webhook idempotency (3x) ----------------
def test_t3_webhook_idempotent(mongo, user_ctx, user_client):
    tid, order_id = make_merchant_order(mongo, user_ctx["user_id"], amount=600.0)
    payment_id = f"pay_{uuid.uuid4().hex[:14]}"
    raw, sig = make_webhook_body(order_id, payment_id, 60000)
    event_id = f"evt_{uuid.uuid4().hex[:10]}"

    statuses = []
    for _ in range(3):
        r = requests.post(f"{API}/webhooks/razorpay", data=raw, headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": sig,
            "X-Razorpay-Event-Id": event_id,
        })
        assert r.status_code == 200
        statuses.append(r.json().get("status"))
    assert statuses[0] == "ok"
    assert statuses[1] == "ignored_duplicate"
    assert statuses[2] == "ignored_duplicate"

    assert mongo.expenses.count_documents({"transaction_id": tid}) == 1
    assert mongo.webhook_events.count_documents({"dedupe_key": event_id}) == 1


# ---------------- T4: Concurrent verify + webhook ----------------
def test_t4_concurrent_verify_and_webhook(mongo, user_ctx, user_client):
    tid, order_id = make_merchant_order(mongo, user_ctx["user_id"], amount=999.0)
    payment_id = f"pay_{uuid.uuid4().hex[:14]}"
    sig_chk = sign_checkout(order_id, payment_id)
    raw, sig_wh = make_webhook_body(order_id, payment_id, 99900)

    def do_verify():
        return user_client.post(f"{API}/payments/verify", json={
            "transaction_id": tid, "razorpay_order_id": order_id,
            "razorpay_payment_id": payment_id, "razorpay_signature": sig_chk,
        })

    def do_webhook():
        return requests.post(f"{API}/webhooks/razorpay", data=raw, headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": sig_wh,
            "X-Razorpay-Event-Id": f"evt_{uuid.uuid4().hex[:10]}",
        })

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        f1 = pool.submit(do_verify)
        f2 = pool.submit(do_webhook)
        r1, r2 = f1.result(), f2.result()
    assert r1.status_code == 200 and r2.status_code == 200, (r1.text, r2.text)

    # exactly one expense
    exps = list(mongo.expenses.find({"transaction_id": tid}))
    assert len(exps) == 1, f"expected 1 expense, got {len(exps)}"
    txn = mongo.payment_orders.find_one({"id": tid})
    assert txn["bill_status"] == "generated"
    assert txn["bill_id"] == exps[0]["bill_id"]


# ---------------- T5: Invalid checkout signature ----------------
def test_t5_invalid_checkout_signature(mongo, user_ctx, user_client):
    tid, order_id = make_merchant_order(mongo, user_ctx["user_id"], amount=500.0)
    payment_id = f"pay_{uuid.uuid4().hex[:14]}"
    bad_sig = "0" * 64

    r = user_client.post(f"{API}/payments/verify", json={
        "transaction_id": tid, "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id, "razorpay_signature": bad_sig,
    })
    # According to router: verified=False -> returns 200 with success:false
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["success"] is False
    assert j.get("payment_status") == "verification_failed"

    assert mongo.expenses.count_documents({"transaction_id": tid}) == 0
    txn = mongo.payment_orders.find_one({"id": tid})
    assert txn["payment_status"] != "captured"


# ---------------- T6: Invalid webhook signature ----------------
def test_t6_invalid_webhook_signature(mongo, user_ctx):
    tid, order_id = make_merchant_order(mongo, user_ctx["user_id"], amount=500.0)
    payment_id = f"pay_{uuid.uuid4().hex[:14]}"
    raw, _sig = make_webhook_body(order_id, payment_id, 50000)

    r = requests.post(f"{API}/webhooks/razorpay", data=raw, headers={
        "Content-Type": "application/json",
        "X-Razorpay-Signature": "deadbeef" * 8,
        "X-Razorpay-Event-Id": f"evt_{uuid.uuid4().hex[:10]}",
    })
    assert r.status_code == 400

    txn = mongo.payment_orders.find_one({"id": tid})
    assert txn["payment_status"] == "created"
    assert mongo.expenses.count_documents({"transaction_id": tid}) == 0


# ---------------- T7: Amount mismatch -> manual_review ----------------
def test_t7_amount_mismatch_manual_review(mongo, user_ctx):
    tid, order_id = make_merchant_order(mongo, user_ctx["user_id"], amount=1000.0)
    payment_id = f"pay_{uuid.uuid4().hex[:14]}"
    # send half amount
    raw, sig = make_webhook_body(order_id, payment_id, 50000)

    r = requests.post(f"{API}/webhooks/razorpay", data=raw, headers={
        "Content-Type": "application/json",
        "X-Razorpay-Signature": sig,
        "X-Razorpay-Event-Id": f"evt_{uuid.uuid4().hex[:10]}",
    })
    assert r.status_code == 200

    txn = mongo.payment_orders.find_one({"id": tid})
    assert txn["payment_status"] == "manual_review", txn
    assert mongo.expenses.count_documents({"transaction_id": tid}) == 0


# ---------------- T8: Settlement not_required after reimbursement bill ----------------
def test_t8_settlement_not_required(mongo, user_ctx, user_client):
    tid, order_id = make_merchant_order(mongo, user_ctx["user_id"], amount=444.0)
    payment_id = f"pay_{uuid.uuid4().hex[:14]}"
    sig = sign_checkout(order_id, payment_id)
    r = user_client.post(f"{API}/payments/verify", json={
        "transaction_id": tid, "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id, "razorpay_signature": sig,
    })
    assert r.status_code == 200 and r.json()["success"] is True

    txn = mongo.payment_orders.find_one({"id": tid})
    assert txn["settlement_status"] == "not_required"
    assert txn["bill_id"]
    exp = mongo.expenses.find_one({"transaction_id": tid})
    assert exp and exp.get("bill_id") == txn["bill_id"]


# ---------------- T9: Bill number format ^BILL-YYYY-NNNNNN$ ----------------
def test_t9_bill_number_format_and_snapshot(mongo, user_ctx, user_client):
    tid, order_id = make_merchant_order(mongo, user_ctx["user_id"], amount=321.0)
    payment_id = f"pay_{uuid.uuid4().hex[:14]}"
    sig = sign_checkout(order_id, payment_id)
    r = user_client.post(f"{API}/payments/verify", json={
        "transaction_id": tid, "razorpay_order_id": order_id,
        "razorpay_payment_id": payment_id, "razorpay_signature": sig,
    })
    j = r.json()
    assert re.match(r"^BILL-\d{4}-\d{6}$", j["bill_id"])
    exp = mongo.expenses.find_one({"transaction_id": tid})
    snap = exp["bill_snapshot"]
    assert snap["merchant_name"] == "Synthetic Cafe"
    assert snap["subtotal"] == exp["total"]
    assert snap["frozen_at"]


# ---------------- T10: Wallet recharge idempotency ----------------
def test_t10_wallet_recharge_idempotent(mongo, user_ctx, user_client):
    # snapshot wallet
    pre = user_client.get(f"{API}/wallet").json()["balance"]
    tid, order_id = make_wallet_order(mongo, user_ctx["user_id"], amount=250.0)
    payment_id = f"pay_{uuid.uuid4().hex[:14]}"
    raw, sig = make_webhook_body(order_id, payment_id, 25000)
    event_id = f"evt_{uuid.uuid4().hex[:10]}"
    for _ in range(3):
        r = requests.post(f"{API}/webhooks/razorpay", data=raw, headers={
            "Content-Type": "application/json",
            "X-Razorpay-Signature": sig,
            "X-Razorpay-Event-Id": event_id,
        })
        assert r.status_code == 200

    post = user_client.get(f"{API}/wallet").json()["balance"]
    assert round(post - pre, 2) == 250.0, f"pre={pre} post={post}"
    txn = mongo.payment_orders.find_one({"id": tid})
    assert txn["credited"] is True


# ---------------- Admin endpoints ----------------
def test_admin_payments_list_and_alerts(super_client):
    r = super_client.get(f"{API}/admin/payments?limit=50")
    assert r.status_code == 200, r.text
    j = r.json()
    assert "payments" in j and "alerts" in j
    for k in ("bill_missing", "settlement_pending", "settlement_failed"):
        assert k in j["alerts"]


def test_admin_payments_flag_bill_missing(super_client):
    r = super_client.get(f"{API}/admin/payments?flag=bill_missing")
    assert r.status_code == 200
    for row in r.json()["payments"]:
        assert row.get("payment_status") == "captured"
        assert row.get("bill_status") != "generated"


def test_admin_reconcile_endpoint(mongo, user_ctx, super_client):
    # captured with bill already exists — reconcile is a no-op returning captured
    tid, order_id = make_merchant_order(mongo, user_ctx["user_id"], amount=150.0)
    payment_id = f"pay_{uuid.uuid4().hex[:14]}"
    raw, sig = make_webhook_body(order_id, payment_id, 15000)
    requests.post(f"{API}/webhooks/razorpay", data=raw, headers={
        "Content-Type": "application/json",
        "X-Razorpay-Signature": sig,
        "X-Razorpay-Event-Id": f"evt_{uuid.uuid4().hex[:10]}",
    })
    r = super_client.post(f"{API}/admin/payments/{tid}/reconcile")
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("found") is True
    # Idempotence: reconciling an already-captured txn must NOT clobber the bill.
    # (Note: admin path may re-hit Razorpay; because these are synthetic orders the
    # live fetch returns no payments and captured=False, but state must be intact.)
    txn = mongo.payment_orders.find_one({"id": tid})
    assert txn["payment_status"] == "captured"
    assert txn["bill_status"] == "generated"
    assert txn["bill_id"]
    assert mongo.expenses.count_documents({"transaction_id": tid}) == 1


def test_admin_settlement_retry_no_record(super_client, mongo, user_ctx):
    tid, _ = make_merchant_order(mongo, user_ctx["user_id"], amount=100.0)
    r = super_client.post(f"{API}/admin/settlements/{tid}/retry")
    assert r.status_code == 200
    assert r.json().get("reason") == "no_settlement_record"


# ---------------- Security ----------------
def test_admin_requires_super_admin(user_client):
    r = user_client.get(f"{API}/admin/payments")
    assert r.status_code in (401, 403)


def test_admin_unauth(client):
    r = client.get(f"{API}/admin/payments")
    assert r.status_code in (401, 403)


def test_status_enforces_ownership(mongo, user_ctx, other_user_client):
    tid, _ = make_merchant_order(mongo, user_ctx["user_id"], amount=100.0)
    r = other_user_client.get(f"{API}/payments/{tid}/status")
    assert r.status_code == 404
