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


async def process_note(urdu_text: str) -> dict:
    prompt = f"""You are processing a personal voice note spoken in Urdu.

Do these four things:

1. CORRECT the Urdu text: Fix any grammatical errors, spelling mistakes,
   or unclear words in the Urdu. Keep the meaning identical.
   Handle mixed Urdu/English (code-switching) naturally — many Pakistani
   speakers mix English words into Urdu sentences, preserve those English
   words as-is.

2. TRANSLATE to English: Translate the corrected Urdu text into natural,
   clear English. Do not translate it word-for-word. Make it read naturally.

3. TITLE: Generate a short title for this note in English. Max 6 words.
   Examples: \"Meeting with Ahmed\", \"Doctor visit reminder\", \"Weekend plan\"

4. TAGS: Generate 2 to 4 single-word tags in English that describe the
   topic. Examples: work, health, family, finance, personal, reminder, idea

Original Urdu text: {urdu_text}

Respond in this exact JSON format only. No extra text, no markdown:
{{
  \"urdu_corrected\": \"corrected urdu text here\",
  \"english_text\": \"natural english translation here\",
  \"title\": \"short title here\",
  \"tags\": [\"tag1\", \"tag2\"]
}}"""

    response_text = await _generate(prompt)
    cleaned = re.sub(r"```json|```", "", response_text).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        return {
            "urdu_corrected": urdu_text,
            "english_text": urdu_text,
            "title": "Voice Note",
            "tags": ["personal"],
        }
