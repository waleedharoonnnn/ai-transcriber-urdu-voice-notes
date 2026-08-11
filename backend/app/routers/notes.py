import os
import shutil
import tempfile
import uuid
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.core.storage import audio_base_url, audio_storage_dir
from app.db.database import execute, execute_returning, fetch_all, fetch_one
from app.models.schemas import NoteAnswerRequest, NoteUpdateRequest
from app.services import embedding, transcription, translation
from app.services.vectorstore import VectorStoreNotConfiguredError, get_vectorstore

router = APIRouter(prefix="/notes", tags=["notes"])

logger = logging.getLogger(__name__)

NOTE_FIELDS = "id, title, english_text, urdu_text, urdu_text_corrected, urdu_text_roman, tags, created_at"


def _normalize_user_id(user_id: str) -> str:
    """Ensure user_id is a UUID string.

    For no-auth testing (e.g. "test-user-123"), deterministically map arbitrary
    strings into a UUID so inserts/queries work.
    """

    try:
        return str(uuid.UUID(user_id))
    except Exception:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"no-auth:{user_id}"))


def _save_audio_file(user_id: str, tmp_path: str) -> str:
    suffix = os.path.splitext(tmp_path)[1] or ".m4a"
    file_name = f"{uuid.uuid4().hex}{suffix}"
    user_dir = audio_storage_dir() / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(tmp_path, user_dir / file_name)
    return f"{audio_base_url()}/audio/{user_id}/{file_name}"


def _text_search_notes(user_id: str, q: str, limit: int) -> list[dict]:
    q = (q or "").strip()
    if not q:
        return []
    like = f"%{q}%"
    return fetch_all(
        f"""
        select {NOTE_FIELDS} from notes
        where user_id = %s
          and (english_text ilike %s or urdu_text_corrected ilike %s
               or urdu_text ilike %s or title ilike %s)
        order by created_at desc
        limit %s
        """,
        (user_id, like, like, like, like, limit),
    )


def _text_search_memories(user_id: str, q: str, limit: int) -> list[dict]:
    q = (q or "").strip()
    if not q:
        return []
    return fetch_all(
        """
        select id, text, kind, created_at, expires_at from memories
        where user_id = %s and text ilike %s
        order by created_at desc
        limit %s
        """,
        (user_id, f"%{q}%", limit),
    )


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

        audio_url = _save_audio_file(user_id, tmp_path)

        urdu_corrected = processed.get("urdu_corrected") or processed.get("urdu_text_corrected")
        urdu_roman = (processed.get("urdu_roman") or "").strip() or None

        rows = execute_returning(
            """
            insert into notes
                (user_id, urdu_text, urdu_text_corrected, urdu_text_roman,
                 english_text, title, tags, audio_url, embedding)
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            returning id
            """,
            (
                user_id,
                urdu_raw,
                urdu_corrected,
                urdu_roman,
                processed["english_text"],
                processed["title"],
                processed["tags"],
                audio_url,
                embed,
            ),
        )
        note_id = rows[0]["id"]

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
            "id": str(note_id),
            "urdu_original": urdu_raw,
            "urdu_corrected": urdu_corrected or urdu_raw,
            "urdu_text_roman": urdu_roman,
            "urdu_roman": urdu_roman,
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
    return fetch_all(
        f"""
        select {NOTE_FIELDS}, audio_url from notes
        where user_id = %s
        order by created_at desc
        limit %s offset %s
        """,
        (user_id, limit, offset),
    )


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
        rows = _text_search_notes(user_id, q, top_k)
        for r in rows:
            r["similarity"] = 0.0
        return rows

    notes_rows = fetch_all(
        f"select {NOTE_FIELDS} from notes where user_id = %s and id = any(%s::uuid[])",
        (user_id, ids),
    )
    by_id = {str(n["id"]): n for n in notes_rows}
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

    notes: list[dict] = []
    if ids:
        notes_rows = fetch_all(
            f"select {NOTE_FIELDS} from notes where user_id = %s and id = any(%s::uuid[])",
            (user_id, ids),
        )
        by_id = {str(n["id"]): n for n in notes_rows}
        for note_id in ids:
            n = by_id.get(str(note_id))
            if not n:
                continue
            notes.append({**n, "similarity": scores.get(str(note_id), 0.0)})

    if not notes:
        # Fallback to text search if Pinecone returns no matches (or isn't configured).
        rows = _text_search_notes(user_id, question, int(payload.top_k))
        if not rows:
            # If the question doesn't share keywords with the note text (common for
            # queries like "what did I record?"), fall back to recent notes.
            rows = fetch_all(
                f"""
                select {NOTE_FIELDS} from notes
                where user_id = %s
                order by created_at desc
                limit %s
                """,
                (user_id, int(payload.top_k)),
            )

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
            mem_rows = fetch_all(
                "select id, text, kind, created_at, expires_at from memories "
                "where user_id = %s and id = any(%s::uuid[])",
                (user_id, mem_ids),
            )
            by_id_mem = {str(m["id"]): m for m in mem_rows}

            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            for mem_id in mem_ids:
                m = by_id_mem.get(str(mem_id))
                if not m:
                    continue
                exp = m.get("expires_at")
                if exp and exp <= now:
                    continue
                memories.append({**m, "similarity": mem_scores.get(str(mem_id), 0.0)})
    except Exception:
        memories = []

    if not memories:
        # Fallback to simple text search in memories.
        rows = _text_search_memories(user_id, question, min(10, int(payload.top_k)))
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
    note = fetch_one(
        "select * from notes where id = %s and user_id = %s",
        (note_id, user_id),
    ) or {}

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

    set_clause = ", ".join(f"{col} = %s" for col in updates)
    params = tuple(updates.values()) + (note_id, user_id)
    rows = execute_returning(
        f"update notes set {set_clause} where id = %s and user_id = %s returning *",
        params,
    )
    if not rows:
        raise HTTPException(status_code=404, detail="Note not found")

    note = rows[0]

    # Best-effort Pinecone upsert on update (only when Pinecone configured).
    try:
        vs = get_vectorstore()
        if vs.is_configured():
            values = updates.get("embedding") or note.get("embedding")
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
    execute("delete from notes where id = %s and user_id = %s", (note_id, user_id))

    # Best-effort Pinecone delete.
    try:
        vs = get_vectorstore()
        if vs.is_configured():
            vs.delete(namespace=user_id, vector_id=str(note_id))
    except Exception as e:
        logger.warning("Pinecone delete failed (note delete): %s", str(e))

    return {"message": "deleted"}
