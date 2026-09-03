"""Helper: create throwaway corporate admin + employee + individual for FE testing."""
import json
import time
import uuid

import requests
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
PW = "Test@1234"
S = requests.Session()
S.headers.update({"Content-Type": "application/json"})


def post_rl(path, **kw):
    for _ in range(20):
        r = S.post(f"{BASE}{path}", **kw)
        if r.status_code != 429:
            return r
        time.sleep(int(r.headers.get("Retry-After", 12)) + 2)
    return r


def hdr(t):
    return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}


tag = uuid.uuid4().hex[:6]
out = {}

# super admin: set individual fee to 1%
sup = post_rl("/auth/login", json={"email": "ujjwal@bill4pe.com", "password": "03PfTZY6W76PrZAa1!"})
sup.raise_for_status()
stok = sup.json()["token"]
r = S.put(f"{BASE}/superadmin/bill-fees", json={"individual": 1}, headers=hdr(stok))
print("bill-fees ->", r.status_code, r.text[:120])

# corporate admin
aemail = f"TEST_fe_ca_{tag}@example.com"
r = post_rl("/auth/register", json={"email": aemail, "password": PW, "name": "TEST FE Corp Admin",
                                    "user_type": "corporate", "corporate_name": "TEST FE Corp Pvt Ltd",
                                    "subscription_plan": "monthly_50", "employee_limit": 50})
r.raise_for_status()
out["corp_admin"] = {"email": aemail, "token": r.json()["token"], "user": r.json()["user"]}

# employee
eemail = f"TEST_fe_emp_{tag}@example.com"
r = S.post(f"{BASE}/company/employees", json={"email": eemail, "name": "TEST FE Emp"},
           headers=hdr(out["corp_admin"]["token"]))
r.raise_for_status()
j = r.json()
tpw = (j.get("credentials") or {}).get("temp_password") or j.get("temp_password")
r = post_rl("/auth/login", json={"email": eemail, "password": tpw})
r.raise_for_status()
out["employee"] = {"email": eemail, "password": tpw, "token": r.json()["token"], "user": r.json()["user"]}

# individual
iemail = f"TEST_fe_ind_{tag}@example.com"
r = post_rl("/auth/register", json={"email": iemail, "password": PW, "name": "TEST FE Indiv"})
r.raise_for_status()
out["individual"] = {"email": iemail, "password": PW, "token": r.json()["token"], "user": r.json()["user"]}

with open("/tmp/fe_creds.json", "w") as f:
    json.dump(out, f)
print(json.dumps({k: {"email": v["email"], "user_type": v["user"].get("user_type"),
                      "role": v["user"].get("role")} for k, v in out.items()}, indent=1))
