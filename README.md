# AItranscriber (Urdu Voice Notes)

A simple web app to record Urdu voice notes, transcribe them, generate English/Urdu outputs, and save them to a Neon (Postgres) database.
Includes optional semantic search via Pinecone.

## What’s inside

- `backend/`: FastAPI API (Groq Whisper + Gemini + Neon Postgres + embeddings)
- `frontend/`: Vite + React web UI (record, list, view, edit, semantic search)

## Quick start (local)

### 1) Backend

1. Create your environment file:
   - Copy `backend/.env.example` → `backend/.env`
   - Fill in the real keys/values (including `DATABASE_URL` from your Neon project)
2. Install dependencies (uses your existing venv if present):
   - Windows Git Bash:
     - `cd backend`
     - `source .venv/Scripts/activate`
     - `python -m pip install -r requirements.txt`
3. Create the database schema:
   - `psql "$DATABASE_URL" -f app/db/schema.sql`
4. Run the API:
   - `uvicorn app.main:app --reload --host 127.0.0.1 --port 8001`

Open Swagger: `http://127.0.0.1:8001/docs`

Uploaded audio files are saved locally under `backend/storage/audio/` and served from `/audio/...`.

### 2) Frontend

1. (Optional) Configure API base URL:
   - By default the frontend uses `http://127.0.0.1:8001`.
   - If you want to override it, create `frontend/.env` with:
     - `VITE_API_BASE_URL=http://127.0.0.1:8001`
2. Install + run:
   - `cd frontend`
   - `npm install`
   - `npm run dev`

Open the app (Vite prints the URL, usually `http://127.0.0.1:5173`).

## Pinecone semantic search (optional)

- Create a Pinecone index with:
  - Dimension: **384**
  - Metric: **cosine**
- Set `PINECONE_API_KEY` + `PINECONE_INDEX` in `backend/.env`
- Indexing behavior:
  - New notes are indexed automatically.
  - Existing notes become indexed after you edit/save them (or re-create them).

## More detailed setup

See `SETUP.md` for step-by-step configuration (Neon database, Pinecone index, and troubleshooting).
