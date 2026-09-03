"""Standalone money-engine verification for the v2 collect-and-payout model.

Runs against the local Mongo with the Razorpay PG + RazorpayX provider layers
MOCKED (no live keys, no real money). Run: `python tests_app/test_v2_engine.py`
from /app/backend.
"""
import asyncio
import sys
import uuid

from core.config import compute_fee_breakdown
from core.db import db
from core.enums import BillStatus, PaymentStatus, PayoutStatus
from services import billing_service, payment_service, payout_service, razorpay_service, razorpayx_service  # noqa

TEST_USER = {"id": f"testuser_{uuid.uuid4().hex[:8]}", "name": "QA User", "email": "qa@bill4pe.test", "wallet_balance": 0.0}

results = []


def check(name, cond, extra=""):
    results.append((name, bool(cond), extra))
    print(f"{'PASS' if cond else 'FAIL'} :: {name} {extra if not cond else ''}")


# ---------------- Provider mocks ----------------
_payout_calls = {}   # idempotency_key -> count
_contact_calls = {"n": 0}
_payout_mode = {"mode": "processed"}  # processed | queued | fail


def install_mocks():
    razorpay_service.enabled = lambda: True
    razorpay_service.key_id = lambda: "rzp_test_mock"
    razorpay_service.verify_checkout_signature = lambda o, p, s: True

    def _create_order(amount, receipt=None, notes=None, transfers=None):
        return {"id": f"order_{uuid.uuid4().hex[:12]}", "amount": amount}
    razorpay_service.create_order = _create_order

    razorpayx_service.enabled = lambda: True

    async def _contact(name, ref, upi):
        _contact_calls["n"] += 1
        return {"id": f"cont_{uuid.uuid4().hex[:8]}"}

    async def _fa(contact_id, upi):
        return {"id": f"fa_{uuid.uuid4().hex[:8]}"}

    async def _payout(*, fund_account_id, amount_paise, reference_id, idempotency_key, narration="x"):
        _payout_calls[idempotency_key] = _payout_calls.get(idempotency_key, 0) + 1
        if _payout_mode["mode"] == "fail":
            raise RuntimeError("razorpayx /payouts 400: temporary error")
        status = "queued" if _payout_mode["mode"] == "queued" else "processed"
        return {"id": f"pout_{uuid.uuid4().hex[:8]}", "status": status, "amount": amount_paise,
                "utr": "UTR12345" if status == "processed" else None, "fees": 590, "tax": 90,
                "reference_id": reference_id, "fund_account_id": fund_account_id}
    razorpayx_service.create_contact = _contact
    razorpayx_service.create_vpa_fund_account = _fa
    razorpayx_service.create_payout = _payout


async def _mk_order(upi, name, items):
    return await payment_service.create_merchant_payment_order(
        TEST_USER, payee_name=name, payee_upi=upi,
        expense_draft={"category": "food", "items": items,
                       "payment": {"merchant_name": name, "merchant_upi": upi}},
        billing_session_id=None,
    )


async def run():
    install_mocks()
    await payment_service.ensure_indexes()
    await payout_service.ensure_indexes()

    # ---- A. Fee math (§52/53/54) ----
    for rupee, exp_fee, exp_total in [(200, 2000, 22000), (100, 1000, 11000), (500, 5000, 55000)]:
        b = compute_fee_breakdown(rupee * 100, "10")
        check(f"fee math ₹{rupee}", b["merchant_amount_paise"] == rupee * 100 and b["platform_fee_paise"] == exp_fee
              and b["customer_total_paise"] == exp_total and b["merchant_payout_amount_paise"] == rupee * 100,
              f"got {b}")

    # ---- B. Order locks payee + amounts (§14/§15) ----
    o = await _mk_order("dhiraj@ybl", "DHIRAJ KUMAR", [{"name": "Food", "quantity": 1, "unit_price": 200}])
    tid = o["transaction_id"]
    check("order customer_total=22000", o["customer_total_paise"] == 22000, str(o))
    txn = await db.payment_orders.find_one({"id": tid})
    check("payee locked upi", txn["payee_upi_snapshot"] == "dhiraj@ybl")
    check("merchant_payout=merchant_amount", txn["merchant_payout_amount_paise"] == 20000 and txn["merchant_amount_paise"] == 20000)

    # ---- C. Capture via checkout callback → 1 bill + 1 payout (₹200→₹220 pay, ₹200 payout) ----
    _payout_mode["mode"] = "processed"
    r1 = await payment_service.reconcile_payment(transaction_id=tid, order_id=txn["order_id"],
                                                 payment_id="pay_1", signature="sig", source="checkout")
    check("capture -> captured", r1.get("payment_status") == PaymentStatus.CAPTURED, str(r1))
    check("capture -> bill generated", bool(r1.get("bill_id")), str(r1))
    check("capture -> payout processed", r1.get("payout_status") == PayoutStatus.PROCESSED, str(r1))
    key = payout_service.idempotency_key(tid)
    check("exactly ONE payout provider call", _payout_calls.get(key) == 1, f"calls={_payout_calls.get(key)}")

    # ---- D. Duplicate webhook + callback race: reconcile 5x → still one bill, one payout ----
    for i in range(5):
        await payment_service.reconcile_payment(order_id=txn["order_id"], payment_id="pay_1",
                                                 source="webhook", amount_paise=22000, verified_captured=True)
    bills = await db.expenses.count_documents({"transaction_id": tid})
    check("5x reconcile -> exactly one expense/bill", bills == 1, f"bills={bills}")
    check("5x reconcile -> still ONE payout call", _payout_calls.get(key) == 1, f"calls={_payout_calls.get(key)}")

    # ---- E. Payout FAILURE isolation (§37/§61): payment stays captured, bill stays, payout failed → retry ----
    _payout_mode["mode"] = "fail"
    of = await _mk_order("fail@upi", "FAIL CO", [{"name": "X", "quantity": 1, "unit_price": 300}])
    tf = of["transaction_id"]
    rf = await payment_service.reconcile_payment(transaction_id=tf, order_id=(await db.payment_orders.find_one({"id": tf}))["order_id"],
                                                 payment_id="pay_f", signature="sig", source="checkout")
    txf = await db.payment_orders.find_one({"id": tf})
    check("payout fail: payment still captured", txf["payment_status"] == PaymentStatus.CAPTURED)
    check("payout fail: bill still generated", txf["bill_status"] == BillStatus.GENERATED)
    check("payout fail: payout_status failed", txf["payout_status"] == PayoutStatus.FAILED, str(txf.get("payout_status")))
    _payout_mode["mode"] = "processed"
    rr = await payout_service.retry_payout(tf)
    check("payout retry -> processed", rr.get("payout_status") == PayoutStatus.PROCESSED, str(rr))
    check("payout retry reused SAME idempotency key (2 calls total)", _payout_calls.get(payout_service.idempotency_key(tf)) == 2,
          f"calls={_payout_calls.get(payout_service.idempotency_key(tf))}")

    # ---- F. Low balance -> queued, payment captured, no re-charge (§33/§62) ----
    _payout_mode["mode"] = "queued"
    oq = await _mk_order("queue@upi", "QUEUE CO", [{"name": "Y", "quantity": 1, "unit_price": 150}])
    tq = oq["transaction_id"]
    rq = await payment_service.reconcile_payment(transaction_id=tq, order_id=(await db.payment_orders.find_one({"id": tq}))["order_id"],
                                                 payment_id="pay_q", signature="sig", source="checkout")
    check("low balance: payout queued", rq.get("payout_status") == PayoutStatus.QUEUED, str(rq))
    txq = await db.payment_orders.find_one({"id": tq})
    check("low balance: payment captured + bill", txq["payment_status"] == PaymentStatus.CAPTURED and txq["bill_status"] == BillStatus.GENERATED)
    _payout_mode["mode"] = "processed"

    # ---- G. App-close recovery: WEBHOOK ONLY (no checkout callback) still bills + pays (§21/§57) ----
    oc = await _mk_order("closeapp@upi", "CLOSE APP", [{"name": "Z", "quantity": 1, "unit_price": 250}])
    tc = oc["transaction_id"]
    order_c = (await db.payment_orders.find_one({"id": tc}))["order_id"]
    rc = await payment_service.reconcile_payment(order_id=order_c, payment_id="pay_c", source="webhook",
                                                 amount_paise=27500, verified_captured=True)
    check("webhook-only: bill generated", bool(rc.get("bill_id")), str(rc))
    check("webhook-only: payout processed", rc.get("payout_status") == PayoutStatus.PROCESSED, str(rc))

    # ---- H. Payout webhook status transition processing->processed ----
    txc = await db.payment_orders.find_one({"id": tc})
    await payout_service.reconcile_payout_from_provider({"id": txc["razorpayx_payout_id"], "status": "processing", "reference_id": tc})
    s1 = (await db.payment_orders.find_one({"id": tc}))["payout_status"]
    await payout_service.reconcile_payout_from_provider({"id": txc["razorpayx_payout_id"], "status": "processed", "utr": "UTRZZZ", "reference_id": tc})
    s2 = await db.payment_orders.find_one({"id": tc})
    check("payout webhook processing->processed", s1 == PayoutStatus.PROCESSING and s2["payout_status"] == PayoutStatus.PROCESSED and s2.get("payout_utr") == "UTRZZZ")

    # ---- I. 20 distinct recipients: each pays ITS OWN upi, no leakage (§55) ----
    _contact_calls["n"] = 0
    tids = []
    for i in range(20):
        upi = f"recipient{i}@bank{i%3}"
        oo = await _mk_order(upi, f"R{i}", [{"name": "Item", "quantity": 1, "unit_price": 100 + i}])
        t = oo["transaction_id"]; tids.append((t, upi, 100 + i))
        await payment_service.reconcile_payment(transaction_id=t, order_id=(await db.payment_orders.find_one({"id": t}))["order_id"],
                                                 payment_id=f"pay_{i}", signature="sig", source="checkout")
    ok_all = True
    for t, upi, rup in tids:
        d = await db.payment_orders.find_one({"id": t})
        if d["payee_upi_snapshot"] != upi or d["merchant_payout_amount_paise"] != rup * 100 or d["payout_status"] != PayoutStatus.PROCESSED:
            ok_all = False
    check("20 recipients each pay own upi + own amount", ok_all)

    # ---- J. Beneficiary reuse: same upi twice -> contact created once ----
    _contact_calls["n"] = 0
    for i in range(2):
        oo = await _mk_order("repeat@ybl", "REPEAT", [{"name": "I", "quantity": 1, "unit_price": 100}])
        t = oo["transaction_id"]
        await payment_service.reconcile_payment(transaction_id=t, order_id=(await db.payment_orders.find_one({"id": t}))["order_id"],
                                                 payment_id=f"pr_{i}", signature="sig", source="checkout")
    check("beneficiary reuse: contact created once for repeat upi", _contact_calls["n"] == 1, f"contacts={_contact_calls['n']}")

    # ---- cleanup ----
    await db.payment_orders.delete_many({"user_id": TEST_USER["id"]})
    await db.expenses.delete_many({"user_id": TEST_USER["id"]})
    await db.beneficiaries.delete_many({"normalized_upi": {"$in": ["dhiraj@ybl", "fail@upi", "queue@upi", "closeapp@upi", "repeat@ybl"] + [f"recipient{i}@bank{i%3}" for i in range(20)]}})
    await db.payouts.delete_many({"transaction_id": {"$exists": True}})

    passed = sum(1 for _, c, _ in results if c)
    total = len(results)
    print(f"\n===== {passed}/{total} checks passed =====")
    return passed == total


if __name__ == "__main__":
    ok = asyncio.get_event_loop().run_until_complete(run())
    sys.exit(0 if ok else 1)
