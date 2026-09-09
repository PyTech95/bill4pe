"""Concurrency: simultaneous generate calls must debit fee once and produce one bill."""
import os
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests
from dotenv import dotenv_values

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
API = f"{BASE_URL}/api"
DRAFT = {"category": "Food", "items": [{"name": "Lunch", "quantity": 1, "unit_price": 200}]}


def test_concurrent_generate_single_debit_single_bill():
    email = f"TEST_conc_{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{API}/auth/register", json={"email": email, "password": "Test@12345", "name": "TEST Conc"}, timeout=30)
    assert r.status_code in (200, 201), r.text[:200]
    token = r.json()["token"]
    h = {"Authorization": f"Bearer {token}"}

    bal0 = float(requests.get(f"{API}/wallet", headers=h, timeout=30).json()["balance"])
    t = requests.post(f"{API}/manual-pay/first-scan", headers=h,
                      json={"payee_upi": "abcstore@ybl", "payee_name": "ABC STORE", "expense_draft": DRAFT}, timeout=30).json()
    tid = t["transaction_id"]
    requests.post(f"{API}/manual-pay/{tid}/second-scan", headers=h, json={"payee_upi": "abcstore@ybl"}, timeout=30)
    requests.post(f"{API}/manual-pay/{tid}/confirm", headers=h, json={"completed": True}, timeout=30)
    requests.post(f"{API}/manual-pay/{tid}/proof", headers=h, data={"utr_full": "121212121212"}, timeout=30)

    def gen(_):
        return requests.post(f"{API}/manual-pay/{tid}/generate", headers=h, timeout=60)

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(ex.map(gen, range(4)))
    codes = [x.status_code for x in results]
    assert all(c == 200 for c in codes), codes
    bill_ids = {x.json().get("bill_id") for x in results if x.json().get("bill_id")}
    assert len(bill_ids) == 1, f"multiple bills created: {bill_ids}"

    bal1 = float(requests.get(f"{API}/wallet", headers=h, timeout=30).json()["balance"])
    assert round(bal0 - bal1, 2) == 2.0, f"fee debited more than once: {bal0} -> {bal1}"

    ex_rows = requests.get(f"{API}/expenses", headers=h, timeout=30).json()
    rows = ex_rows if isinstance(ex_rows, list) else ex_rows.get("expenses", [])
    assert len([e for e in rows if e.get("transaction_id") == tid]) == 1
