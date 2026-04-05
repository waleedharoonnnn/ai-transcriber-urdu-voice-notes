import os
import tempfile
import uuid
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.db.supabase import get_client
from app.models.schemas import NoteAnswerRequest, NoteUpdateRequest
from app.services import embedding, transcription, translation
from app.services.vectorstore import VectorStoreNotConfiguredError, get_vectorstore

router = APIRouter(prefix="/notes", tags=["notes"])

logger = logging.getLogger(__name__)


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


def _is_unknown_column_error(exc: Exception, column: str) -> bool:
    msg = (str(exc) or "").lower()
    col = (column or "").lower()
    if not msg:
        return False
    # PostgREST/Supabase messages vary, so we keep this heuristic broad.
    return (col in msg and "column" in msg) or (col in msg and "not" in msg and "exist" in msg)


def _text_search_notes(supabase, user_id: str, q: str, limit: int) -> list[dict]:
    q = (q or "").strip()
    if not q:
        return []

    # Note: Supabase uses PostgREST filters. We try an OR ilike query, and if the
    # client/library differs, we fall back to a simpler english_text ilike.
    try:
        res = (
            supabase.table("notes")
            .select(
                "id, title, english_text, urdu_text, urdu_text_corrected, urdu_text_roman, tags, created_at"
            )
            .eq("user_id", user_id)
            .or_(
                f"english_text.ilike.%{q}%,urdu_text_corrected.ilike.%{q}%,urdu_text.ilike.%{q}%,title.ilike.%{q}%"
            )
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception:
        try:
            res = (
                supabase.table("notes")
                .select(
                    "id, title, english_text, urdu_text, urdu_text_corrected, urdu_text_roman, tags, created_at"
                )
                .eq("user_id", user_id)
                .ilike("english_text", f"%{q}%")
                .order("created_at", desc=True)
                .limit(limit)
                .execute()
            )
            return res.data or []
        except Exception:
            return []


def _text_search_memories(supabase, user_id: str, q: str, limit: int) -> list[dict]:
    q = (q or "").strip()
    if not q:
        return []
    try:
        res = (
            supabase.table("memories")
            .select("id, text, kind, created_at, expires_at")
            .eq("user_id", user_id)
            .ilike("text", f"%{q}%")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception:
        return []


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

        insert_row = {
            "user_id": user_id,
            "urdu_text": urdu_raw,
            "urdu_text_corrected": processed.get("urdu_corrected") or processed.get("urdu_text_corrected"),
            "urdu_text_roman": (processed.get("urdu_roman") or "").strip() or None,
            "english_text": processed["english_text"],
            "title": processed["title"],
            "tags": processed["tags"],
            "audio_url": audio_url,
            "embedding": embed,
        }

        try:
            result = supabase.table("notes").insert(insert_row).execute()
        except Exception as e:
            # If the DB schema doesn't have the new column yet, gracefully retry without it.
            if _is_unknown_column_error(e, "urdu_text_roman"):
                insert_row.pop("urdu_text_roman", None)
                result = supabase.table("notes").insert(insert_row).execute()
            else:
                raise

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
        except Exception as e:
            logger.warning("Pinecone upsert failed (note create): %s", str(e))

        return {
            "id": note_id,
            "urdu_original": urdu_raw,
            "urdu_corrected": processed.get("urdu_corrected")
            or processed.get("urdu_text_corrected")
            or urdu_raw,
            "urdu_text_roman": (processed.get("urdu_roman") or "").strip() or None,
            "urdu_roman": (processed.get("urdu_roman") or "").strip() or None,
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
    try:
        result = (
            supabase.table("notes")
            .select(
                "id, title, english_text, urdu_text_corrected, urdu_text_roman, tags, created_at, audio_url"
            )
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .range(offset, offset + limit - 1)
            .execute()
        )
    except Exception as e:
        if _is_unknown_column_error(e, "urdu_text_roman"):
            result = (
                supabase.table("notes")
                .select("id, title, english_text, urdu_text_corrected, tags, created_at, audio_url")
                .eq("user_id", user_id)
                .order("created_at", desc=True)
                .range(offset, offset + limit - 1)
                .execute()
            )
        else:
            raise
    return result.data


@router.get("/search")
async def search_notes(user_id: str, q: str, top_k: int = 10):
    user_id = _normalize_user_id(user_id)
    q = (q or "").strip()
    if not q:
        raise HTTPException(status_code=400, detail="Missing search query 'q'.")

    vs = get_vectorstore()
    matches = []
    if vs.is_configured():
        query_embed = embedding.generate_embedding(q)
        try:
            matches = vs.query(namespace=user_id, values=query_embed, top_k=top_k)
        except VectorStoreNotConfiguredError:
            matches = []
        except Exception as e:
            logger.warning("Pinecone query failed (search): %s", str(e))
            matches = []

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
        # Fallback: simple DB text search so the UI can still find records.
        supabase = get_client()
        rows = _text_search_notes(supabase, user_id, q, top_k)
        for r in rows:
            r["similarity"] = 0.0
        return rows

    supabase = get_client()
    try:
        notes_res = (
            supabase.table("notes")
            .select(
                "id, title, english_text, urdu_text, urdu_text_corrected, urdu_text_roman, tags, created_at"
            )
            .eq("user_id", user_id)
            .in_("id", ids)
            .execute()
        )
    except Exception as e:
        if _is_unknown_column_error(e, "urdu_text_roman"):
            notes_res = (
                supabase.table("notes")
                .select("id, title, english_text, urdu_text, urdu_text_corrected, tags, created_at")
                .eq("user_id", user_id)
                .in_("id", ids)
                .execute()
            )
        else:
            raise

    by_id = {str(n["id"]): n for n in (notes_res.data or [])}
    ordered = []
    for note_id in ids:
        n = by_id.get(str(note_id))
        if not n:
            continue
        ordered.append({**n, "similarity": scores.get(str(note_id), 0.0)})
    return ordered


@router.post("/answer")
async def answer_from_notes(user_id: str, payload: NoteAnswerRequest) -> dict:
    user_id = _normalize_user_id(user_id)
    question = (payload.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Missing 'question'.")

    vs = get_vectorstore()
    query_embed = embedding.generate_embedding(question)
    matches = []
    if vs.is_configured():
        try:
            matches = vs.query(namespace=user_id, values=query_embed, top_k=payload.top_k)
        except VectorStoreNotConfiguredError:
            matches = []
        except Exception as e:
            logger.warning("Pinecone query failed (answer): %s", str(e))
            matches = []

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

    supabase = get_client()
    notes: list[dict] = []
    if ids:
        try:
            notes_res = (
                supabase.table("notes")
                .select(
                    "id, title, english_text, urdu_text, urdu_text_corrected, urdu_text_roman, tags, created_at"
                )
                .eq("user_id", user_id)
                .in_("id", ids)
                .execute()
            )
        except Exception as e:
            if _is_unknown_column_error(e, "urdu_text_roman"):
                notes_res = (
                    supabase.table("notes")
                    .select(
                        "id, title, english_text, urdu_text, urdu_text_corrected, tags, created_at"
                    )
                    .eq("user_id", user_id)
                    .in_("id", ids)
                    .execute()
                )
            else:
                raise
        by_id = {str(n["id"]): n for n in (notes_res.data or [])}
        for note_id in ids:
            n = by_id.get(str(note_id))
            if not n:
                continue
            n = {**n, "similarity": scores.get(str(note_id), 0.0)}
            notes.append(n)

    if not notes:
        # Fallback to text search if Pinecone returns no matches (or isn't configured).
        rows = _text_search_notes(supabase, user_id, question, int(payload.top_k))
        if not rows:
            # If the question doesn't share keywords with the note text (common for
            # queries like "what did I record?"), fall back to recent notes.
            try:
                rows = (
                    supabase.table("notes")
                    .select(
                        "id, title, english_text, urdu_text, urdu_text_corrected, urdu_text_roman, tags, created_at"
                    )
                    .eq("user_id", user_id)
                    .order("created_at", desc=True)
                    .limit(int(payload.top_k))
                    .execute()
                ).data or []
            except Exception as e:
                if _is_unknown_column_error(e, "urdu_text_roman"):
                    rows = (
                        supabase.table("notes")
                        .select(
                            "id, title, english_text, urdu_text, urdu_text_corrected, tags, created_at"
                        )
                        .eq("user_id", user_id)
                        .order("created_at", desc=True)
                        .limit(int(payload.top_k))
                        .execute()
                    ).data or []
                else:
                    rows = []

        for r in rows:
            r["similarity"] = 0.0
        notes = rows

    # Also retrieve memories (best-effort; if the table doesn't exist yet, we still answer from notes).
    memories: list[dict] = []
    try:
        mem_matches = []
        if vs.is_configured():
            mem_matches = vs.query(
                namespace=f"memory:{user_id}",
                values=query_embed,
                top_k=min(10, int(payload.top_k)),
            )
        mem_ids: list[str] = []
        mem_scores: dict[str, float] = {}
        for m in mem_matches:
            mid = m.get("id")
            if mid is None:
                continue
            mid = str(mid)
            mem_ids.append(mid)
            try:
                mem_scores[mid] = float(m.get("score") or 0.0)
            except Exception:
                mem_scores[mid] = 0.0

        if mem_ids:
            mem_res = (
                supabase.table("memories")
                .select("id, text, kind, created_at, expires_at")
                .eq("user_id", user_id)
                .in_("id", mem_ids)
                .execute()
            )
            by_id_mem = {str(m["id"]): m for m in (mem_res.data or [])}

            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            for mem_id in mem_ids:
                m = by_id_mem.get(str(mem_id))
                if not m:
                    continue
                exp = m.get("expires_at")
                if exp:
                    try:
                        exp_dt = datetime.fromisoformat(exp.replace("Z", "+00:00"))
                        if exp_dt <= now:
                            continue
                    except Exception:
                        pass
                memories.append({**m, "similarity": mem_scores.get(str(mem_id), 0.0)})
    except Exception:
        memories = []

    if not memories:
        # Fallback to simple text search in memories.
        rows = _text_search_memories(supabase, user_id, question, min(10, int(payload.top_k)))
        for r in rows:
            r["similarity"] = 0.0
        memories = rows

    try:
        answer = await translation.answer_question_from_notes_and_memories(
            question, notes, memories
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Gemini answer failed: {e}")

    sources: list[dict] = []
    for n in notes:
        sources.append({"type": "note", **n})
    for m in memories:
        sources.append({"type": "memory", **m})

    return {"answer": answer, "sources": sources, "note_sources": notes, "memory_sources": memories}


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
    note = result.data or {}

    # Best-effort: if roman Urdu isn't stored yet, generate it for display.
    try:
        roman = (note.get("urdu_text_roman") or "").strip() if isinstance(note, dict) else ""
        if not roman and isinstance(note, dict):
            base = (
                (note.get("urdu_text_corrected") or "").strip()
                or (note.get("urdu_text") or "").strip()
            )
            if base:
                roman = (await translation.romanize_urdu(base)).strip()
                if roman:
                    note["urdu_text_roman"] = roman
    except Exception:
        pass

    return note


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
    if payload.urdu_text_roman is not None:
        updates["urdu_text_roman"] = payload.urdu_text_roman
    if payload.english_text is not None:
        updates["english_text"] = payload.english_text
        updates["embedding"] = embedding.generate_embedding(payload.english_text)

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")

    supabase = get_client()
    try:
        updated = (
            supabase.table("notes")
            .update(updates)
            .eq("id", note_id)
            .eq("user_id", user_id)
            .execute()
        )
    except Exception as e:
        # If the DB schema doesn't have the roman column yet, gracefully retry without it.
        if _is_unknown_column_error(e, "urdu_text_roman") and "urdu_text_roman" in updates:
            updates.pop("urdu_text_roman", None)
            updated = (
                supabase.table("notes")
                .update(updates)
                .eq("id", note_id)
                .eq("user_id", user_id)
                .execute()
            )
        else:
            raise

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
    except Exception as e:
        logger.warning("Pinecone upsert failed (note update): %s", str(e))

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
    except Exception as e:
        logger.warning("Pinecone delete failed (note delete): %s", str(e))

    return {"message": "deleted"}
