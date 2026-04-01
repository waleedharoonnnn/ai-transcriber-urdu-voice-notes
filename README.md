# AItranscriber (Urdu Voice Notes)

A simple web app to record Urdu voice notes, transcribe them, generate English/Urdu outputs, and save them to Supabase.
Includes optional semantic search via Pinecone.

## What’s inside

- `backend/`: FastAPI API (Groq Whisper + Gemini + Supabase + embeddings)
- `frontend/`: Vite + React web UI (record, list, view, edit, semantic search)

## Quick start (local)

### 1) Backend

1. Create your environment file:
   - Copy `backend/.env.example` → `backend/.env`
   - Fill in the real keys/values
2. Install dependencies (uses your existing venv if present):
   - Windows Git Bash:
     - `cd backend`
     - `source .venv/Scripts/activate`
     - `python -m pip install -r requirements.txt`

3. Run the API:
   - `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`

Open Swagger: `http://127.0.0.1:8000/docs`

### 2) Frontend

1. Create your environment file:
   - Copy `frontend/.env.example` → `frontend/.env`
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
- Backfill existing notes into Pinecone:
  - `cd backend`
  - `source .venv/Scripts/activate`
  - `python scripts/reindex_pinecone.py --user-id YOUR_USER_ID`

## More detailed setup

See `SETUP.md` for step-by-step configuration (Supabase table/bucket, Pinecone index, and troubleshooting).
