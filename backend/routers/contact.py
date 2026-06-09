"""Landing-page contact form submissions."""
import uuid
from fastapi import APIRouter

from core.db import db
from core.models import ContactMsg
from core.security import now_iso

router = APIRouter(tags=["contact"])


@router.post("/contact")
async def contact(body: ContactMsg):
    await db.contact_messages.insert_one({
        "id": str(uuid.uuid4()), "name": body.name, "email": body.email,
        "message": body.message, "created_at": now_iso()
    })
    return {"ok": True}
