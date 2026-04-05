import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException

from app.db.supabase import get_client
from app.models.schemas import MemoryAddRequest
from app.services import embedding
from app.services.vectorstore import VectorStoreNotConfiguredError, get_vectorstore

router = APIRouter(prefix="/memory", tags=["memory"])


def _normalize_user_id(user_id: str) -> str:
    try:
        return str(uuid.UUID(user_id))
    except Exception:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"no-auth:{user_id}"))


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _memory_namespace(user_id: str) -> str:
    return f"memory:{user_id}"


@router.post("/add")
async def add_memory(user_id: str, payload: MemoryAddRequest) -> dict:
    user_id = _normalize_user_id(user_id)
    text = (payload.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Missing 'text'.")

    kind = (payload.kind or "long").strip().lower()
    if kind not in ("short", "long"):
        raise HTTPException(status_code=400, detail="kind must be 'short' or 'long'.")

    expires_at = None
    if kind == "short":
        ttl_hours = payload.ttl_hours if payload.ttl_hours is not None else 24
        if ttl_hours <= 0 or ttl_hours > 24 * 30:
            raise HTTPException(status_code=400, detail="ttl_hours must be 1..720")
        expires_at = _now_utc() + timedelta(hours=int(ttl_hours))

    mem_id = str(uuid.uuid4())
    vec = embedding.generate_embedding(text)

    supabase = get_client()
    row = {
        "id": mem_id,
        "user_id": user_id,
        "text": text,
        "kind": kind,
        "embedding": vec,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }

    res = supabase.table("memories").insert(row).execute()
    if not getattr(res, "data", None):
        # If insert response doesn't include data, still return what we know.
        created_at = _now_utc().isoformat()
    else:
        created_at = res.data[0].get("created_at") or _now_utc().isoformat()

    # Best-effort Pinecone upsert.
    try:
        vs = get_vectorstore()
        if vs.is_configured():
            vs.upsert(
                namespace=_memory_namespace(user_id),
                vector_id=mem_id,
                values=vec,
                metadata={
                    "user_id": user_id,
                    "kind": kind,
                    "expires_at": expires_at.isoformat() if expires_at else None,
                },
            )
    except Exception:
        pass

    return {
        "id": mem_id,
        "text": text,
        "kind": kind,
        "created_at": created_at,
        "expires_at": expires_at.isoformat() if expires_at else None,
    }


@router.get("/list")
async def list_memories(user_id: str, kind: str | None = None, limit: int = 50) -> list[dict]:
    user_id = _normalize_user_id(user_id)
    kind_lc = (kind or "").strip().lower()
    if kind_lc and kind_lc not in ("short", "long"):
        raise HTTPException(status_code=400, detail="kind must be 'short' or 'long'.")

    supabase = get_client()
    q = supabase.table("memories").select("id, text, kind, created_at, expires_at").eq(
        "user_id", user_id
    )
    if kind_lc:
        q = q.eq("kind", kind_lc)

    res = q.order("created_at", desc=True).limit(int(limit)).execute()
    rows = res.data or []

    now = _now_utc()
    out: list[dict] = []
    for r in rows:
        exp = r.get("expires_at")
        if exp:
            try:
                exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                if exp_dt <= now:
                    continue
            except Exception:
                # If parsing fails, keep it.
                pass
        out.append(r)
    return out


@router.get("/search")
async def search_memories(user_id: str, q: str, top_k: int = 10, kind: str | None = None) -> list[dict]:
    user_id = _normalize_user_id(user_id)
    q = (q or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Missing search query 'q'.")

    kind_lc = (kind or "").strip().lower()
    if kind_lc and kind_lc not in ("short", "long"):
        raise HTTPException(status_code=400, detail="kind must be 'short' or 'long'.")

    vs = get_vectorstore()
    if not vs.is_configured():
        raise HTTPException(
            status_code=501,
            detail="Memory search is not configured. Set PINECONE_API_KEY and PINECONE_INDEX.",
        )

    query_embed = embedding.generate_embedding(q)

    try:
        matches = vs.query(namespace=_memory_namespace(user_id), values=query_embed, top_k=top_k)
    except VectorStoreNotConfiguredError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pinecone query failed: {e}")

    ids: list[str] = []
    scores: dict[str, float] = {}
    for m in matches:
        mid = m.get("id")
        if mid is None:
            continue
        mid = str(mid)
        ids.append(mid)
        try:
            scores[mid] = float(m.get("score") or 0.0)
        except Exception:
            scores[mid] = 0.0

    if not ids:
        return []

    supabase = get_client()
    mem_res = (
        supabase.table("memories")
        .select("id, text, kind, created_at, expires_at")
        .eq("user_id", user_id)
        .in_("id", ids)
        .execute()
    )

    by_id = {str(m["id"]): m for m in (mem_res.data or [])}
    now = _now_utc()

    ordered: list[dict] = []
    for mem_id in ids:
        m = by_id.get(str(mem_id))
        if not m:
            continue
        if kind_lc and (m.get("kind") or "").lower() != kind_lc:
            continue
        exp = m.get("expires_at")
        if exp:
            try:
                exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                if exp_dt <= now:
                    continue
            except Exception:
                pass
        ordered.append({**m, "similarity": scores.get(str(mem_id), 0.0)})

    return ordered


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str, user_id: str) -> dict:
    user_id = _normalize_user_id(user_id)
    supabase = get_client()
    (
        supabase.table("memories")
        .delete()
        .eq("id", memory_id)
        .eq("user_id", user_id)
        .execute()
    )

    try:
        vs = get_vectorstore()
        if vs.is_configured():
            vs.delete(namespace=_memory_namespace(user_id), vector_id=str(memory_id))
    except Exception:
        pass

    return {"message": "deleted"}
