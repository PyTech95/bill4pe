"""Quick Re-stock favourites for pantry/grocery categories."""
from fastapi import APIRouter, Depends, HTTPException

from core.config import FAV_ALLOWED_CATEGORIES, FAV_MAX_PER_CATEGORY
from core.db import db
from core.models import FavouritesSave
from core.security import get_current_user, now_iso

router = APIRouter(tags=["favourites"])


def _norm_fav_name(s: str) -> str:
    return (s or "").strip().lower()


@router.get("/favourites")
async def list_favourites(category: str, user=Depends(get_current_user)):
    if category not in FAV_ALLOWED_CATEGORIES:
        raise HTTPException(400, "Favourites available only for pantry/grocery")
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "favourites": 1})
    favs = ((u or {}).get("favourites") or {}).get(category, [])
    favs = sorted(favs, key=lambda x: x.get("last_used", ""), reverse=True)
    return {"category": category, "items": favs}


@router.post("/favourites")
async def save_favourites(body: FavouritesSave, user=Depends(get_current_user)):
    if body.category not in FAV_ALLOWED_CATEGORIES:
        raise HTTPException(400, "Favourites available only for pantry/grocery")
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "favourites": 1})
    existing = ((u or {}).get("favourites") or {}).get(body.category, [])
    by_name = {_norm_fav_name(it.get("name")): it for it in existing if it.get("name")}
    ts = now_iso()
    for it in body.items:
        nm = (it.name or "").strip()
        if not nm:
            continue
        key = _norm_fav_name(nm)
        by_name[key] = {
            "name": nm,
            "unit_price": float(it.unit_price or 0.0),
            "last_used": ts,
        }
    merged = sorted(by_name.values(), key=lambda x: x.get("last_used", ""), reverse=True)
    merged = merged[:FAV_MAX_PER_CATEGORY]
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {f"favourites.{body.category}": merged}},
    )
    return {"category": body.category, "items": merged}


@router.delete("/favourites")
async def delete_favourite(category: str, name: str, user=Depends(get_current_user)):
    if category not in FAV_ALLOWED_CATEGORIES:
        raise HTTPException(400, "Favourites available only for pantry/grocery")
    u = await db.users.find_one({"id": user["id"]}, {"_id": 0, "favourites": 1})
    existing = ((u or {}).get("favourites") or {}).get(category, [])
    filtered = [it for it in existing if _norm_fav_name(it.get("name")) != _norm_fav_name(name)]
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {f"favourites.{category}": filtered}},
    )
    return {"category": category, "items": filtered}
