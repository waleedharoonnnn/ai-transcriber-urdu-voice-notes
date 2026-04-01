import argparse
import uuid
from pathlib import Path

from dotenv import load_dotenv


def _normalize_user_id(user_id: str) -> str:
    try:
        return str(uuid.UUID(user_id))
    except Exception:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"no-auth:{user_id}"))


def main() -> int:
    backend_dir = Path(__file__).resolve().parents[1]
    load_dotenv(backend_dir / ".env")

    from app.db.supabase import get_client
    from app.services import embedding
    from app.services.vectorstore import get_vectorstore

    parser = argparse.ArgumentParser(description="Backfill existing notes into Pinecone")
    parser.add_argument("--user-id", required=True, help="Supabase user_id (UUID) or test id")
    parser.add_argument("--limit", type=int, default=1000)
    args = parser.parse_args()

    user_id = _normalize_user_id(args.user_id)

    vs = get_vectorstore()
    if not vs.is_configured():
        raise SystemExit(
            "Pinecone not configured. Set PINECONE_API_KEY and PINECONE_INDEX in backend/.env"
        )

    supabase = get_client()
    res = (
        supabase.table("notes")
        .select("id, title, tags, english_text, embedding")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(int(args.limit))
        .execute()
    )

    rows = res.data or []
    print(f"Found {len(rows)} notes to index")

    indexed = 0
    for n in rows:
        note_id = str(n.get("id"))
        eng = (n.get("english_text") or "").strip()
        if not note_id or not eng:
            continue

        values = n.get("embedding")
        if not isinstance(values, list) or not values:
            values = embedding.generate_embedding(eng)

        vs.upsert(
            namespace=user_id,
            vector_id=note_id,
            values=values,
            metadata={
                "user_id": user_id,
                "title": n.get("title"),
                "tags": n.get("tags"),
            },
        )
        indexed += 1

    print(f"Indexed {indexed} notes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
