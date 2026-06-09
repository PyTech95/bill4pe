"""BILL4PE — slim FastAPI entry point.

Real logic lives in `core/`, `services/`, and `routers/`. This file only wires
the app together: CORS, the `/api` umbrella router, and lifecycle hooks.
"""
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from core.config import CORS_ORIGINS
from core.db import client
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
)

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


@app.on_event("shutdown")
async def shutdown():
    client.close()
