import os
from pathlib import Path

_backend_dir = Path(__file__).resolve().parents[2]


def audio_storage_dir() -> Path:
    configured = (os.getenv("AUDIO_STORAGE_DIR") or "storage/audio").strip()
    path = Path(configured)
    if not path.is_absolute():
        path = _backend_dir / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def audio_base_url() -> str:
    return (os.getenv("AUDIO_BASE_URL") or "http://127.0.0.1:8001").rstrip("/")
