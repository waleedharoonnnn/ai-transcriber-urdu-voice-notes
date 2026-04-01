import os

from groq import Groq


def _get_client() -> Groq:
    return Groq(api_key=os.getenv("GROQ_API_KEY"))


async def transcribe_urdu(audio_path: str) -> str:
    client = _get_client()
    with open(audio_path, "rb") as f:
        result = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=f,
            language="ur",
            response_format="text",
        )
    return result
