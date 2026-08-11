from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

_backend_dir = Path(__file__).resolve().parents[1]
load_dotenv(_backend_dir / ".env")

from app.core.storage import audio_storage_dir  # noqa: E402
from app.routers import auth, memory, notes  # noqa: E402

app = FastAPI(title="Urdu Notes API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(notes.router)
app.include_router(memory.router)

app.mount("/audio", StaticFiles(directory=str(audio_storage_dir())), name="audio")


@app.get("/")
def root() -> dict:
    return {"status": "Urdu Notes API is running"}

