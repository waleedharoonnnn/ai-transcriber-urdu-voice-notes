import os
import tempfile
import uuid

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.db.supabase import get_client
from app.models.schemas import NoteUpdateRequest
from app.services import embedding, transcription, translation
from app.services.vectorstore import VectorStoreNotConfiguredError, get_vectorstore

router = APIRouter(prefix="/notes", tags=["notes"])


def _audio_bucket() -> str:
    return (os.getenv("SUPABASE_AUDIO_BUCKET") or "audio").strip()


def _ensure_storage_bucket(supabase, bucket_id: str) -> None:
    """Ensure a Supabase Storage bucket exists.

    If the configured Supabase key does not have permissions to create buckets,
    this will raise a helpful error instructing how to fix it manually.
    """

    try:
        buckets = supabase.storage.list_buckets()
        if any((b.get("id") == bucket_id) for b in (buckets or [])):
            return
    except Exception:
        # If listing buckets fails (permissions), we'll still try create and
        # then fall back to a helpful error.
        pass

    try:
        supabase.storage.create_bucket(bucket_id, options={"public": True})
    except Exception as e:
        msg = str(e) or ""
        msg_lc = msg.lower()
        if "already exists" in msg_lc:
            return
        raise RuntimeError(
            "Supabase Storage bucket is missing and could not be created automatically. "
            f"Please create a bucket named '{bucket_id}' in Supabase Storage, or set "
            "SUPABASE_AUDIO_BUCKET to an existing bucket id. "
            f"(raw: {msg})"
        )


def _normalize_user_id(user_id: str) -> str:
    """Ensure user_id is a UUID string.

    Supabase schemas commonly use UUID for user_id. For no-auth testing (e.g. "test-user-123"),
    deterministically map arbitrary strings into a UUID so inserts/queries work.
    """

    try:
        return str(uuid.UUID(user_id))
    except Exception:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"no-auth:{user_id}"))


@router.post("/create")
async def create_note(user_id: str, audio: UploadFile = File(...)) -> dict:
    user_id = _normalize_user_id(user_id)
    suffix = os.path.splitext(audio.filename)[1] if audio.filename else ".m4a"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await audio.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        urdu_raw = await transcription.transcribe_urdu(tmp_path)

        processed = await translation.process_note(urdu_raw)

        embed = embedding.generate_embedding(processed["english_text"])

        supabase = get_client()
        bucket_id = _audio_bucket()
        _ensure_storage_bucket(supabase, bucket_id)
        file_name = f"{user_id}/{os.path.basename(tmp_path)}"
        with open(tmp_path, "rb") as f:
            data = f.read()
            supabase.storage.from_(bucket_id).upload(
                file_name,
                data,
                file_options={
                    "content-type": audio.content_type or "application/octet-stream",
                    "x-upsert": "true",
                },
            )

        public_url = supabase.storage.from_(bucket_id).get_public_url(file_name)
        audio_url = public_url.get("publicUrl") if isinstance(public_url, dict) else public_url

        result = supabase.table("notes").insert({
            "user_id": user_id,
            "urdu_text": urdu_raw,
            "urdu_text_corrected": processed["urdu_corrected"],
            "english_text": processed["english_text"],
            "title": processed["title"],
            "tags": processed["tags"],
            "audio_url": audio_url,
            "embedding": embed,
        }).execute()

        note_id = result.data[0]["id"]

        # Best-effort Pinecone upsert for semantic search (no hard dependency).
        try:
            vs = get_vectorstore()
            if vs.is_configured():
                vs.upsert(
                    namespace=user_id,
                    vector_id=str(note_id),
                    values=embed,
                    metadata={
                        "user_id": user_id,
                        "title": processed["title"],
                        "tags": processed["tags"],
                    },
                )
        except Exception:
            pass

        return {
            "id": note_id,
            "urdu_original": urdu_raw,
            "urdu_corrected": processed["urdu_corrected"],
            "english": processed["english_text"],
            "title": processed["title"],
            "tags": processed["tags"],
            "audio_url": audio_url,
        }
    except Exception as e:
        msg = str(e) or ""
        msg_lc = msg.lower()
        if (
            "rate limit" in msg_lc
            or "too many requests" in msg_lc
            or "quota" in msg_lc
            or "insufficient_quota" in msg_lc
            or "429" in msg_lc
        ):
            raise HTTPException(
                status_code=429,
                detail=(
                    "Groq rate limit/quota reached. Please wait a bit and try again. "
                    "If it keeps happening, reduce test recordings." 
                    f"(raw: {msg})"
                ),
            )
        raise HTTPException(status_code=500, detail=msg)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


@router.get("/list")
async def list_notes(user_id: str, limit: int = 20, offset: int = 0):
    user_id = _normalize_user_id(user_id)
    supabase = get_client()
    result = (
        supabase.table("notes")
        .select("id, title, english_text, urdu_text_corrected, tags, created_at, audio_url")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .range(offset, offset + limit - 1)
        .execute()
    )
    return result.data


@router.get("/search")
async def search_notes(user_id: str, q: str, top_k: int = 10):
    user_id = _normalize_user_id(user_id)
    q = (q or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Missing search query 'q'.")

    vs = get_vectorstore()
    if not vs.is_configured():
        raise HTTPException(
            status_code=501,
            detail=(
                "Semantic search is not configured. Set PINECONE_API_KEY and PINECONE_INDEX "
                "(and ensure your index dimension matches the embedding model)."
            ),
        )

    query_embed = embedding.generate_embedding(q)

    try:
        matches = vs.query(namespace=user_id, values=query_embed, top_k=top_k)
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
    notes_res = (
        supabase.table("notes")
        .select("id, title, english_text, urdu_text, urdu_text_corrected, tags, created_at")
        .eq("user_id", user_id)
        .in_("id", ids)
        .execute()
    )

    by_id = {str(n["id"]): n for n in (notes_res.data or [])}
    ordered = []
    for note_id in ids:
        n = by_id.get(str(note_id))
        if not n:
            continue
        ordered.append({**n, "similarity": scores.get(str(note_id), 0.0)})
    return ordered


@router.get("/{note_id}")
async def get_note(note_id: str, user_id: str):
    user_id = _normalize_user_id(user_id)
    supabase = get_client()
    result = (
        supabase.table("notes")
        .select("*")
        .eq("id", note_id)
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    return result.data


@router.patch("/{note_id}")
async def update_note(note_id: str, user_id: str, payload: NoteUpdateRequest):
    user_id = _normalize_user_id(user_id)

    updates: dict = {}
    if payload.title is not None:
        updates["title"] = payload.title
    if payload.tags is not None:
        updates["tags"] = payload.tags
    if payload.urdu_text is not None:
        updates["urdu_text"] = payload.urdu_text
    if payload.urdu_text_corrected is not None:
        updates["urdu_text_corrected"] = payload.urdu_text_corrected
    if payload.english_text is not None:
        updates["english_text"] = payload.english_text
        updates["embedding"] = embedding.generate_embedding(payload.english_text)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")

    supabase = get_client()
    updated = (
        supabase.table("notes")
        .update(updates)
        .eq("id", note_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not updated.data:
        raise HTTPException(status_code=404, detail="Note not found")

    note = updated.data[0]

    # Best-effort Pinecone upsert on update (only when Pinecone configured).
    try:
        vs = get_vectorstore()
        if vs.is_configured():
            values = updates.get("embedding")
            if values is None:
                values = note.get("embedding")
            if values is not None:
                vs.upsert(
                    namespace=user_id,
                    vector_id=str(note.get("id")),
                    values=values,
                    metadata={
                        "user_id": user_id,
                        "title": note.get("title"),
                        "tags": note.get("tags"),
                    },
                )
    except Exception:
        pass

    return note


@router.delete("/{note_id}")
async def delete_note(note_id: str, user_id: str) -> dict:
    user_id = _normalize_user_id(user_id)
    supabase = get_client()
    (
        supabase.table("notes")
        .delete()
        .eq("id", note_id)
        .eq("user_id", user_id)
        .execute()
    )

    # Best-effort Pinecone delete.
    try:
        vs = get_vectorstore()
        if vs.is_configured():
            vs.delete(namespace=user_id, vector_id=str(note_id))
    except Exception:
        pass

    return {"message": "deleted"}
