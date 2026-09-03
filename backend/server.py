"""BILL4PE — slim FastAPI entry point.

Real logic lives in `core/`, `services/`, and `routers/`. This file only wires
the app together: CORS, the `/api` umbrella router, and lifecycle hooks.
"""
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import CORS_ORIGINS
from core.db import client
from core.ratelimit import RateLimitMiddleware
from core.security import now_iso

from routers import (
    auth as auth_router,
    referrals as referrals_router,
    ai as ai_router,
    expenses as expenses_router,
    wallet as wallet_router,
    favourites as favourites_router,
    bills as bills_router,
    reports as reports_router,
    contact as contact_router,
    company as company_router,
    verify as verify_router,
    superadmin as superadmin_router,
    payments as payments_router,
    health as health_router,
    webhooks as webhooks_router,
    admin_payments as admin_payments_router,
    manual_pay as manual_pay_router,
)
from core.seed import seed_super_admin

app = FastAPI(title="BILL4PE API")

api = APIRouter(prefix="/api")
api.include_router(auth_router.router)
api.include_router(referrals_router.router)
api.include_router(ai_router.router)
api.include_router(expenses_router.router)
api.include_router(wallet_router.router)
api.include_router(favourites_router.router)
api.include_router(bills_router.router)
api.include_router(reports_router.router)
api.include_router(contact_router.router)
api.include_router(company_router.router)
api.include_router(verify_router.router)
api.include_router(superadmin_router.router)
api.include_router(payments_router.router)
api.include_router(health_router.router)
api.include_router(webhooks_router.router)
api.include_router(admin_payments_router.router)
api.include_router(manual_pay_router.router)


@api.get("/")
async def root():
    return {"app": "BILL4PE", "status": "ok", "time": now_iso()}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Basic brute-force / abuse protection on auth + payment routes.
app.add_middleware(RateLimitMiddleware)


@app.on_event("startup")
async def seed_platform_defaults():
    """Ensure the configured Super Admin account exists at boot."""
    try:
        uid = await seed_super_admin()
        from core.config import logger
        logger.info(f"Super admin seeded/verified (uid={uid})")
    except Exception as e:
        from core.config import logger
        logger.error(f"Super admin seed failed: {e}")


@app.on_event("startup")
async def init_payments_subsystem():
    """Indexes for idempotency/concurrency + loud Razorpay/RazorpayX config validation."""
    from core.config import logger
    from services import payment_service, payout_service, razorpay_service, razorpayx_service
    try:
        razorpay_service.validate_config()
        razorpayx_service.validate_config()
    except Exception as e:
        logger.error(f"Payment provider config validation error: {e}")
    try:
        await payment_service.ensure_indexes()
        await payout_service.ensure_indexes()
        from services import manual_flow_service
        await manual_flow_service.ensure_indexes()
    except Exception as e:
        logger.error(f"Payment index creation failed: {e}")


@app.on_event("startup")
async def start_reconciliation_worker():
    """Background safety net: periodically reconcile stale pending payments with
    Razorpay so a missed webhook can never leave a paid customer without a bill."""
    import asyncio
    import os as _os
    from core.config import logger
    from services import payment_service, razorpay_service

    if not razorpay_service.enabled():
        return
    interval = int(_os.environ.get("RECONCILE_INTERVAL_SECONDS", "300"))
    older_than = int(_os.environ.get("RECONCILE_OLDER_THAN_MINUTES", "3"))

    async def _loop():
        while True:
            await asyncio.sleep(interval)
            try:
                await payment_service.scan_and_reconcile_pending(older_than_minutes=older_than)
            except Exception as e:  # noqa: BLE001
                logger.error(f"[background] reconciliation sweep error: {e}")

    asyncio.create_task(_loop())
    logger.info(f"Reconciliation worker started (every {interval}s, threshold {older_than}m)")


@app.on_event("startup")
async def backfill_legacy_corporate():
    """Legacy corporate users created before B2B feature lacked role/company_id.
    On startup, ensure each corporate user has a `companies` doc and is set to
    role='admin', so they correctly land on the Company Dashboard after login."""
    import uuid
    from core.db import db
    cursor = db.users.find({
        "user_type": "corporate",
        "$or": [{"role": {"$exists": False}}, {"role": None}, {"company_id": None}, {"company_id": {"$exists": False}}],
    })
    count = 0
    async for u in cursor:
        company_id = str(uuid.uuid4())
        await db.companies.insert_one({
            "id": company_id,
            "name": u.get("corporate_name") or u.get("name") or "My Company",
            "admin_id": u["id"],
            "wallet_balance": 0.0,
            "subscription_plan": u.get("subscription_plan"),
            "employee_limit": u.get("employee_limit"),
            "subscription_status": u.get("subscription_status") or "trial",
            "created_at": now_iso(),
        })
        await db.users.update_one({"id": u["id"]}, {"$set": {
            "role": "admin", "company_id": company_id,
        }})
        count += 1
    if count:
        from core.config import logger
        logger.info(f"Backfilled {count} legacy corporate users with company_id + role=admin")


@app.on_event("shutdown")
async def shutdown():
    client.close()
