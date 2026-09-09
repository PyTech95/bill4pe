"""MongoDB-backed storage for uploaded payment receipt screenshots.

New payment proofs are stored in the ``payment_proofs`` MongoDB collection,
not on the application filesystem.  Keeping proof bytes outside the code tree
means a deploy/re-extract/rebuild cannot delete customer receipt images.

The upload route caps files at 5 MiB, safely below MongoDB's 16 MiB BSON
document limit.  Only authenticated proof endpoints ever load the ``data``
field; normal transaction/history queries store and return metadata/reference
fields only.
"""
from __future__ import annotations

import mimetypes
import uuid
from pathlib import Path

from bson.binary import Binary

from core.config import logger
from core.db import db
from core.security import now_iso

LEGACY_PROOF_DIR = Path(__file__).resolve().parent.parent / "private_uploads" / "payment_proofs"


async def ensure_indexes() -> None:
    await db.payment_proofs.create_index("id", unique=True)
    await db.payment_proofs.create_index([("transaction_id", 1), ("created_at", -1)])
    await db.payment_proofs.create_index([("user_id", 1), ("created_at", -1)])


async def store_payment_proof(
    *,
    data: bytes,
    filename: str | None,
    content_type: str,
    transaction_id: str,
    user_id: str,
) -> dict:
    if not data:
        raise ValueError("Empty payment proof")

    proof_id = str(uuid.uuid4())
    safe_name = Path(filename or "payment-receipt").name[:180]
    doc = {
        "id": proof_id,
        "transaction_id": transaction_id,
        "user_id": user_id,
        "filename": safe_name,
        "content_type": content_type or "application/octet-stream",
        "size_bytes": len(data),
        "data": Binary(data),
        "created_at": now_iso(),
    }
    await db.payment_proofs.insert_one(doc)
    logger.info(
        "[payment_proof_storage] stored proof=%s txn=%s bytes=%s in MongoDB",
        proof_id,
        transaction_id,
        len(data),
    )
    return {
        "id": proof_id,
        "storage": "mongodb",
        "filename": safe_name,
        "content_type": doc["content_type"],
        "size_bytes": len(data),
    }


async def get_payment_proof(proof_id: str, *, transaction_id: str | None = None) -> dict | None:
    query = {"id": proof_id}
    if transaction_id:
        query["transaction_id"] = transaction_id
    doc = await db.payment_proofs.find_one(query)
    if not doc:
        return None
    payload = doc.get("data")
    if payload is None:
        return None
    return {
        "id": doc["id"],
        "transaction_id": doc.get("transaction_id"),
        "user_id": doc.get("user_id"),
        "filename": doc.get("filename") or "payment-receipt",
        "content_type": doc.get("content_type") or "application/octet-stream",
        "size_bytes": doc.get("size_bytes") or len(payload),
        "data": bytes(payload),
        "created_at": doc.get("created_at"),
    }


async def delete_payment_proof(proof_id: str) -> None:
    if proof_id:
        await db.payment_proofs.delete_one({"id": proof_id})


async def migrate_legacy_files_to_mongodb() -> dict:
    """Best-effort one-time migration of legacy filesystem proofs.

    This intentionally does *not* delete the old physical files.  After the
    migration reports success, an operator may back up/remove the legacy folder.
    Missing files are logged and left untouched so no record is silently lost.
    """
    if not LEGACY_PROOF_DIR.exists():
        return {"migrated": 0, "missing": 0, "skipped": 0}

    query = {
        "proof_file": {"$type": "string", "$ne": ""},
        "$or": [
            {"proof_db_id": {"$exists": False}},
            {"proof_db_id": None},
            {"proof_db_id": ""},
        ],
    }
    migrated = missing = skipped = 0
    async for txn in db.manual_transactions.find(query):
        legacy_name = Path(txn.get("proof_file") or "").name
        path = LEGACY_PROOF_DIR / legacy_name
        if not legacy_name or not path.is_file():
            missing += 1
            logger.warning(
                "[payment_proof_storage] legacy proof missing txn=%s file=%s",
                txn.get("id"), legacy_name,
            )
            continue
        try:
            data = path.read_bytes()
            mime = mimetypes.guess_type(legacy_name)[0] or "application/octet-stream"
            stored = await store_payment_proof(
                data=data,
                filename=legacy_name,
                content_type=mime,
                transaction_id=txn["id"],
                user_id=txn["user_id"],
            )
            set_fields = {
                "proof_storage": "mongodb",
                "proof_db_id": stored["id"],
                "proof_filename": stored["filename"],
                "proof_mime": stored["content_type"],
                "proof_size_bytes": stored["size_bytes"],
                "proof_migrated_at": now_iso(),
            }
            await db.manual_transactions.update_one(
                {"id": txn["id"]},
                {"$set": set_fields, "$unset": {"proof_file": ""}},
            )
            await db.receipt_verifications.update_many(
                {"transaction_id": txn["id"]},
                {
                    "$set": {
                        "receipt_storage": "mongodb",
                        "receipt_db_id": stored["id"],
                        "receipt_filename": stored["filename"],
                        "receipt_mime": stored["content_type"],
                        "receipt_size_bytes": stored["size_bytes"],
                    },
                    "$unset": {"receipt_file": ""},
                },
            )
            migrated += 1
        except Exception:  # noqa: BLE001
            skipped += 1
            logger.exception(
                "[payment_proof_storage] legacy proof migration failed txn=%s file=%s",
                txn.get("id"), legacy_name,
            )

    if migrated or missing or skipped:
        logger.info(
            "[payment_proof_storage] legacy migration complete migrated=%s missing=%s skipped=%s",
            migrated, missing, skipped,
        )
    return {"migrated": migrated, "missing": missing, "skipped": skipped}
