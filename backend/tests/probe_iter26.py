"""Observational probes (not pass/fail): exact degraded status codes + CORS posture."""
import os
import uuid

import requests
from dotenv import dotenv_values

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"

s = requests.Session()
s.headers.update({"Content-Type": "application/json", "X-Forwarded-For": "10.7.7.7"})
em = f"TEST_probe_{uuid.uuid4().hex[:8]}@example.com"
tok = s.post(f"{API}/auth/register", json={"email": em, "password": "TestPass@123", "name": "TEST Probe"}, timeout=45).json()["token"]
s.headers.update({"Authorization": f"Bearer {tok}"})

probes = [
    ("POST /payments/create-order", "post", "/payments/create-order", {"purpose": "wallet_recharge", "amount": 100}),
    ("POST /payments/merchant/create-order", "post", "/payments/merchant/create-order", {"payee_upi": "t@upi", "merchant_amount": 100}),
    ("POST /payments/razorpay/order", "post", "/payments/razorpay/order", {"purpose": "wallet_recharge", "amount": 100}),
    ("POST /payments/verify(fake)", "post", "/payments/verify", {"razorpay_order_id": "order_X", "razorpay_payment_id": "pay_X", "razorpay_signature": "bad"}),
    ("POST /wallet/recharge(-1000)", "post", "/wallet/recharge", {"amount": -1000}),
    ("POST /wallet/recharge(1000)", "post", "/wallet/recharge", {"amount": 1000}),
]
for label, m, path, body in probes:
    r = getattr(s, m)(f"{API}{path}", json=body, timeout=45)
    print(f"{label:42s} -> {r.status_code} {r.text[:180]}")

for path in ["/webhooks/razorpay", "/webhooks/razorpay/payments", "/webhooks/razorpayx/payouts"]:
    r = s.post(f"{API}{path}", json={"event": "payment.captured"}, timeout=45)
    print(f"unsigned {path:32s} -> {r.status_code} {r.text[:120]}")

# CORS posture
for origin in ["https://billing-test-4.preview.emergentagent.com", "https://evil.example.com"]:
    r = requests.options(f"{API}/auth/login", headers={
        "Origin": origin, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type", "X-Forwarded-For": "10.7.7.8"}, timeout=45)
    print(f"CORS preflight {origin} -> {r.status_code} allow-origin={r.headers.get('access-control-allow-origin')}")
