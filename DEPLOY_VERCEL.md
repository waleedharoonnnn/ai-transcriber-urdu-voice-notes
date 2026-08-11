# Deploying to Vercel

This app has two parts, and only one of them belongs on Vercel:

| Part | Deploy to Vercel? | Why |
|---|---|---|
| `frontend/` (Vite + React) | ✅ Yes | Static site, exactly what Vercel is built for. |
| `backend/` (FastAPI) | ❌ No | Vercel serverless functions cap out around 250 MB unzipped. This backend's dependencies — `torch` + `sentence-transformers` alone — are well over 1 GB installed. It also writes uploaded audio to local disk (`backend/storage/audio/`), and Vercel functions have no persistent/writable disk between requests. |

So the plan is: **frontend on Vercel**, **backend on a host that runs a normal, always-on container** (Render, Railway, Fly.io, or Google Cloud Run — a `backend/Dockerfile` is already in the repo, written for Cloud Run). Point the two at each other with an env var.

## Part 1 — Backend first (so you have a URL to give the frontend)

Pick one host. All of them can build straight from `backend/Dockerfile`.

### Option: Render (simplest, free tier available)

1. [render.com](https://render.com) → **New → Web Service** → connect this GitHub repo.
2. Root directory: `backend`. Runtime: **Docker** (it will pick up `backend/Dockerfile`).
3. Add environment variables (from `backend/.env.example`):
   - `GROQ_API_KEY`
   - `GEMINI_API_KEY`
   - `DATABASE_URL` (your Neon connection string, keep `?sslmode=require`)
   - `JWT_SECRET` (generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"`)
   - `AUDIO_STORAGE_DIR=storage/audio`
   - `AUDIO_BASE_URL` — set this to the Render URL you'll be given, e.g. `https://your-backend.onrender.com`
   - `PINECONE_API_KEY` / `PINECONE_INDEX` (optional)
4. **Persistent disk for audio**: by default the container's filesystem resets on every deploy/restart, so uploaded recordings would vanish. Add a Render **Disk**, mount it at `/app/storage`, and keep `AUDIO_STORAGE_DIR=storage/audio`. (Railway and Fly.io have equivalent "volume" features if you use one of those instead.)
5. Deploy. Once live, run the schema once against Neon (from your machine, since Neon is reachable from anywhere):
   ```
   cd backend
   python -c "
   import os, psycopg2
   from dotenv import load_dotenv
   load_dotenv('.env')
   psycopg2.connect(os.getenv('DATABASE_URL')).cursor().execute(open('app/db/schema.sql').read())
   "
   ```
   (Or use `psql "$DATABASE_URL" -f backend/app/db/schema.sql` if you have `psql` installed.)
6. Note the live backend URL (e.g. `https://your-backend.onrender.com`) — you need it for Part 2.

## Part 2 — Frontend on Vercel

1. [vercel.com](https://vercel.com) → **Add New → Project** → import this GitHub repo.
2. **Root Directory**: `frontend`.
3. Framework preset: Vite (Vercel usually detects this automatically).
   - Build command: `npm run build`
   - Output directory: `dist`
4. **Environment Variables** → add:
   - `VITE_API_BASE_URL` = the backend URL from Part 1 (e.g. `https://your-backend.onrender.com`), **no trailing slash**.
5. Deploy.

### Or via CLI

```
npm i -g vercel
cd frontend
vercel link
vercel env add VITE_API_BASE_URL production
# paste your backend URL when prompted
vercel --prod
```

## Part 3 — Wire it back together (CORS)

`backend/app/main.py` currently allows all origins (`allow_origins=["*"]`), so it will accept requests from your Vercel domain without extra config. If you later lock this down to specific origins, make sure to include your Vercel production URL (and any preview-deployment URLs, which Vercel generates per-branch/PR).

## Checklist after deploying

- [ ] Backend `/` responds: `curl https://your-backend.onrender.com/`
- [ ] `backend/app/db/schema.sql` has been run against your Neon database
- [ ] Frontend loads and can sign up / log in (hits the backend, not `127.0.0.1`)
- [ ] Recording a note round-trips: upload → transcription → saved note → audio playback works from the deployed `AUDIO_BASE_URL`
- [ ] If you change the backend URL later, update `VITE_API_BASE_URL` in Vercel and redeploy the frontend
