# Setup Guide (Backend + Frontend + Supabase + Pinecone)

This guide is designed to be copy/paste friendly.

## Prerequisites

- Python **3.10** (you already have a venv in `backend/.venv`)
- Node.js **18+** recommended
- A Supabase project (DB + Storage)
- API keys:
  - Groq (Whisper)
  - Gemini
  - (Optional) Pinecone

## 1) Supabase setup

### 1.1 Create the `notes` table

The backend expects a `notes` table with (at minimum) these columns:

- `id` (uuid, primary key, default generated)
- `user_id` (uuid)
- `urdu_text` (text)
- `urdu_text_corrected` (text, nullable)
- `english_text` (text)
- `title` (text, nullable)
- `tags` (text[] or json, nullable)
- `audio_url` (text, nullable)
- `embedding` (vector or json, nullable)
- `created_at` (timestamp, default now())

If you’re using pgvector, set `embedding` to `vector(384)`.

### 1.2 Create the Storage bucket

The API uploads audio to a Supabase Storage bucket.

- Default bucket name: `audio`
- You can override it via `SUPABASE_AUDIO_BUCKET` in `backend/.env`

## 2) Backend setup (FastAPI)

### 2.1 Create env file

Copy the example:

- `backend/.env.example` → `backend/.env`

Fill values.

### 2.2 Install dependencies

Using Git Bash on Windows:

- `cd backend`
- `source .venv/Scripts/activate`
- `python -m pip install -r requirements.txt`

### 2.3 Run the server

- `cd backend`
- `source .venv/Scripts/activate`
- `uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`

Docs: `http://127.0.0.1:8000/docs`

## 3) Frontend setup (Vite + React)

### 3.1 Create env file

- `frontend/.env.example` → `frontend/.env`

### 3.2 Install + run

- `cd frontend`
- `npm install`
- `npm run dev`

If port `5173` is busy, Vite will choose another port (it prints it).

## 4) Pinecone semantic search (optional but recommended)

### 4.1 Create Pinecone index

Your embedding model is `sentence-transformers/all-MiniLM-L6-v2`.

Create an index with:

- **Dimension:** `384`
- **Metric:** `cosine`

### 4.2 Configure backend env

Set these in `backend/.env`:

- `PINECONE_API_KEY=...`
- `PINECONE_INDEX=...` (your index name)

Restart the backend after changing env.

### 4.3 Backfill existing notes

Only newly created/edited notes get indexed automatically. For your existing saved notes, run:

- `cd backend`
- `source .venv/Scripts/activate`
- `python scripts/reindex_pinecone.py --user-id YOUR_USER_ID`

### 4.4 Test it

Once Pinecone is configured, semantic search is available at:

- `GET /notes/search?user_id=YOUR_USER_ID&q=YOUR_QUERY&top_k=20`

The frontend search bar calls this endpoint.

## 5) Common env tips

### Generate `JWT_SECRET`

From inside the backend venv:

- `python -c "import secrets; print(secrets.token_urlsafe(32))"`

## Troubleshooting

- Search returns 501: Pinecone not configured (missing `PINECONE_API_KEY` / `PINECONE_INDEX`).
- Pinecone returns dimension error: your index must be **384**.
- Storage errors: ensure the bucket exists (default `audio`) or set `SUPABASE_AUDIO_BUCKET`.
