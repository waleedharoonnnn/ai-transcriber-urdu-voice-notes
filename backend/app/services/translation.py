import json
import os
import re

import logging

try:
    from google import genai as genai_new
    from google.genai import types as genai_types
except Exception:  # pragma: no cover
    genai_new = None
    genai_types = None

try:
    import google.generativeai as genai_legacy
except Exception:  # pragma: no cover
    genai_legacy = None

logger = logging.getLogger(__name__)

_client = None
_legacy_configured = False


def _candidate_models() -> list[str]:
    preferred = (os.getenv("GEMINI_MODEL") or "").strip()
    candidates = [
        preferred or None,
        "gemini-2.5-flash",
        "gemini-2.0-flash",
        "gemini-1.5-flash",
    ]
    return [c for c in candidates if c]


def _ensure_client():
    global _client
    if _client is not None:
        return _client

    if genai_new is None:
        raise RuntimeError("google-genai is not installed")

    api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    api_version = (os.getenv("GEMINI_API_VERSION") or "").strip()

    kwargs = {}
    if api_key:
        kwargs["api_key"] = api_key
    if api_version:
        # Examples: v1beta, v1alpha, v1
        kwargs["http_options"] = genai_types.HttpOptions(api_version=api_version)

    _client = genai_new.Client(**kwargs) if kwargs else genai_new.Client()
    return _client


def _ensure_legacy_configured() -> None:
    global _legacy_configured
    if _legacy_configured:
        return
    if genai_legacy is None:
        raise RuntimeError("google-generativeai is not installed")
    api_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
    genai_legacy.configure(api_key=api_key)
    _legacy_configured = True


async def _generate(prompt: str) -> str:
    last_err: Exception | None = None

    # Prefer the new SDK if installed; otherwise fall back to the legacy SDK
    if genai_new is not None and genai_types is not None:
        client = _ensure_client()
        for model in _candidate_models():
            try:
                resp = await client.aio.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.2,
                        max_output_tokens=1024,
                        response_mime_type="application/json",
                    ),
                )
                return (getattr(resp, "text", "") or "").strip()
            except Exception as e:
                msg = (str(e) or "").lower()
                code = getattr(e, "code", None)
                if code == 404 or ("model" in msg and "not found" in msg):
                    logger.warning("Gemini model '%s' unavailable: %s", model, str(e))
                    last_err = e
                    continue
                raise

    _ensure_legacy_configured()
    for model in _candidate_models():
        try:
            legacy_model = genai_legacy.GenerativeModel(model)
            resp = legacy_model.generate_content(prompt)
            return (getattr(resp, "text", "") or "").strip()
        except Exception as e:
            msg = (str(e) or "").lower()
            if "model" in msg and ("not found" in msg or "not supported" in msg):
                logger.warning("Gemini model '%s' unavailable: %s", model, str(e))
                last_err = e
                continue
            if "404" in msg and "models/" in msg:
                logger.warning("Gemini model '%s' unavailable: %s", model, str(e))
                last_err = e
                continue
            raise

    raise last_err or RuntimeError("No Gemini model succeeded")


async def _generate_text(prompt: str) -> str:
    last_err: Exception | None = None

    # Prefer the new SDK if installed; otherwise fall back to the legacy SDK
    if genai_new is not None and genai_types is not None:
        client = _ensure_client()
        for model in _candidate_models():
            try:
                resp = await client.aio.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=genai_types.GenerateContentConfig(
                        temperature=0.2,
                        max_output_tokens=512,
                    ),
                )
                return (getattr(resp, "text", "") or "").strip()
            except Exception as e:
                msg = (str(e) or "").lower()
                code = getattr(e, "code", None)
                if code == 404 or ("model" in msg and "not found" in msg):
                    logger.warning("Gemini model '%s' unavailable: %s", model, str(e))
                    last_err = e
                    continue
                raise

    _ensure_legacy_configured()
    for model in _candidate_models():
        try:
            legacy_model = genai_legacy.GenerativeModel(model)
            resp = legacy_model.generate_content(prompt)
            return (getattr(resp, "text", "") or "").strip()
        except Exception as e:
            msg = (str(e) or "").lower()
            if "model" in msg and ("not found" in msg or "not supported" in msg):
                logger.warning("Gemini model '%s' unavailable: %s", model, str(e))
                last_err = e
                continue
            if "404" in msg and "models/" in msg:
                logger.warning("Gemini model '%s' unavailable: %s", model, str(e))
                last_err = e
                continue
            raise

    raise last_err or RuntimeError("No Gemini model succeeded")


async def answer_question_from_notes(question: str, notes: list[dict]) -> str:
    """Generate a concise answer to a question using retrieved note snippets.

    The caller is responsible for retrieving relevant notes (e.g., via Pinecone).
    """

    q = (question or "").strip()
    if not q:
        raise ValueError("question is required")

    # Keep prompt small and predictable.
    blocks: list[str] = []
    for i, n in enumerate(notes[:10], start=1):
        title = (n.get("title") or "").strip()
        eng = (n.get("english_text") or "").strip()
        urdu = (n.get("urdu_text_corrected") or n.get("urdu_text") or "").strip()

        snippet = eng or urdu
        if not snippet:
            continue

        snippet = snippet.replace("\n", " ").strip()
        if len(snippet) > 600:
            snippet = snippet[:600] + "…"

        header = f"Note {i}:" + (f" {title}" if title else "")
        blocks.append(f"{header}\n{snippet}")

    context_text = "\n\n".join(blocks) if blocks else "(no notes found)"

    prompt = f"""You are a helpful assistant answering questions using the user's personal notes.

Rules:
- Use ONLY the provided notes as your source of truth.
- If the notes don't contain the answer, say you don't know based on the notes.
- Keep the answer concise.

Question:
{q}

Notes:
{context_text}
"""

    return await _generate_text(prompt)


async def answer_question_from_notes_and_memories(
    question: str, notes: list[dict], memories: list[dict]
) -> str:
    q = (question or "").strip()
    if not q:
        raise ValueError("question is required")

    # Notes section
    note_blocks: list[str] = []
    for i, n in enumerate(notes[:10], start=1):
        title = (n.get("title") or "").strip()
        eng = (n.get("english_text") or "").strip()
        urdu = (n.get("urdu_text_corrected") or n.get("urdu_text") or "").strip()

        snippet = eng or urdu
        if not snippet:
            continue
        snippet = snippet.replace("\n", " ").strip()
        if len(snippet) > 600:
            snippet = snippet[:600] + "…"
        header = f"Note {i}:" + (f" {title}" if title else "")
        note_blocks.append(f"{header}\n{snippet}")

    # Memories section
    mem_blocks: list[str] = []
    for i, m in enumerate(memories[:10], start=1):
        kind = (m.get("kind") or "").strip().lower() or "long"
        text = (m.get("text") or "").strip()
        if not text:
            continue
        text = text.replace("\n", " ").strip()
        if len(text) > 600:
            text = text[:600] + "…"
        mem_blocks.append(f"Memory {i} ({kind}):\n{text}")

    notes_text = "\n\n".join(note_blocks) if note_blocks else "(no notes found)"
    mem_text = "\n\n".join(mem_blocks) if mem_blocks else "(no memories found)"

    prompt = f"""You are a helpful assistant answering questions using the user's personal notes and saved memory.

Rules:
- Use ONLY the provided Notes and Memory as your source of truth.
- If they don't contain the answer, say you don't know based on the provided context.
- Keep the answer concise.

Question:
{q}

Notes:
{notes_text}

Memory:
{mem_text}
"""

    return await _generate_text(prompt)


async def romanize_urdu(urdu_text: str) -> str:
    """Convert Urdu script into Roman Urdu (transliteration).

    Best-effort helper used for UI display when the DB column isn't present yet
    or older notes don't have the value.
    """

    text = (urdu_text or "").strip()
    if not text:
        return ""

    prompt = f"""Convert the following Urdu text into Roman Urdu (Urdu written in English letters).

Rules:
- Output ONLY the Roman Urdu text (no quotes, no explanations).
- Keep it natural and readable for Pakistani users.
- Preserve any English words as-is.

Urdu:
{text}
"""

    try:
        return (await _generate_text(prompt)).strip()
    except Exception:
        return ""


async def process_note(urdu_text: str) -> dict:
    prompt = f"""You are processing a personal voice note spoken in Urdu.

Do these five things:

1. CORRECT the Urdu text: Fix any grammatical errors, spelling mistakes,
   or unclear words in the Urdu. Keep the meaning identical.
   Handle mixed Urdu/English (code-switching) naturally — many Pakistani
   speakers mix English words into Urdu sentences, preserve those English
   words as-is.

2. TRANSLATE to English: Translate the corrected Urdu text into natural,
   clear English. Do not translate it word-for-word. Make it read naturally.

3. ROMAN URDU: Convert the corrected Urdu text into Roman Urdu (Urdu written
    using English letters). Keep it readable for Pakistani users. Preserve any
    English words as-is.

4. TITLE: Generate a short title for this note in English. Max 6 words.
   Examples: \"Meeting with Ahmed\", \"Doctor visit reminder\", \"Weekend plan\"

5. TAGS: Generate 2 to 4 single-word tags in English that describe the
   topic. Examples: work, health, family, finance, personal, reminder, idea

Original Urdu text: {urdu_text}

Respond in this exact JSON format only. No extra text, no markdown:
{{
  \"urdu_corrected\": \"corrected urdu text here\",
    \"urdu_roman\": \"roman urdu here\",
  \"english_text\": \"natural english translation here\",
  \"title\": \"short title here\",
  \"tags\": [\"tag1\", \"tag2\"]
}}"""

    response_text = await _generate(prompt)
    cleaned = re.sub(r"```json|```", "", response_text).strip()

    try:
        data = json.loads(cleaned)
        if isinstance(data, dict):
            # Backward compatible defaults
            if "urdu_roman" not in data:
                data["urdu_roman"] = ""
        return data
    except json.JSONDecodeError:
        return {
            "urdu_corrected": urdu_text,
            "urdu_roman": "",
            "english_text": urdu_text,
            "title": "Voice Note",
            "tags": ["personal"],
        }
