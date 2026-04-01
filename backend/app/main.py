from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

_backend_dir = Path(__file__).resolve().parents[1]
load_dotenv(_backend_dir / ".env")

from app.routers import auth, notes  # noqa: E402

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


@app.get("/")
def root() -> dict:
    return {"status": "Urdu Notes API is running"}

