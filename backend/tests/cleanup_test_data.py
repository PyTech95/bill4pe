"""Cleanup: remove TEST_-prefixed accounts and their data from the staging DB."""
import asyncio
import os

from dotenv import dotenv_values
from motor.motor_asyncio import AsyncIOMotorClient

env = dotenv_values("/app/backend/.env")
url = os.environ.get("MONGO_URL") or env["MONGO_URL"]
name = os.environ.get("DB_NAME") or env["DB_NAME"]


async def main():
    db = AsyncIOMotorClient(url)[name]
    users = await db.users.find({"email": {"$regex": "^test_", "$options": "i"}}, {"_id": 0, "id": 1}).to_list(5000)
    ids = [u["id"] for u in users]
    print("test users:", len(ids))
    for coll in ("expenses", "wallet_txns", "reports", "payment_orders", "manual_transactions"):
        r = await db[coll].delete_many({"user_id": {"$in": ids}})
        print(coll, r.deleted_count)
    r = await db.users.delete_many({"id": {"$in": ids}})
    print("users", r.deleted_count)


asyncio.run(main())
