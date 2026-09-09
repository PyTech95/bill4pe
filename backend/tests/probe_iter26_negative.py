"""Escalation probe: does a negative-amount expense credit the wallet on bill generation?"""
import os
import uuid

import requests
from dotenv import dotenv_values

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE}/api"

s = requests.Session()
s.headers.update({"Content-Type": "application/json", "X-Forwarded-For": "10.6.6.6"})
em = f"TEST_neg_{uuid.uuid4().hex[:8]}@example.com"
tok = s.post(f"{API}/auth/register", json={"email": em, "password": "TestPass@123", "name": "TEST Neg"}, timeout=45).json()["token"]
s.headers.update({"Authorization": f"Bearer {tok}"})

before = s.get(f"{API}/auth/me", timeout=45).json()["wallet_balance"]
exp = s.post(f"{API}/expenses", json={
    "category": "Travel",
    "items": [{"name": "TEST_neg", "quantity": 1, "unit_price": -100000.0}],
    "payment": {"amount": -100000.0, "payment_method": "UPI"},
}, timeout=45).json()
print("expense total:", exp.get("total"))
gen = s.post(f"{API}/bills/{exp['id']}/generate", json={}, timeout=45)
print("generate:", gen.status_code, gen.text[:300])
after = s.get(f"{API}/auth/me", timeout=45).json()["wallet_balance"]
print(f"wallet {before} -> {after}  DELTA={round(after - before, 2)}")
