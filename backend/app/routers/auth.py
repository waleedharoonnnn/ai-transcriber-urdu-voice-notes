from fastapi import APIRouter, HTTPException

from app.db.supabase import get_client
from app.models.schemas import AuthRequest

router = APIRouter(prefix="/auth", tags=["auth"])


def _get_user_by_email(supabase, email: str):
    email_lc = (email or "").lower()
    try:
        res = supabase.auth.admin.list_users()
        users = res if isinstance(res, list) else getattr(res, "users", [])
        for u in users:
            u_email = (u.get("email") if isinstance(u, dict) else getattr(u, "email", None))
            if (u_email or "").lower() == email_lc:
                return u
    except Exception:
        return None
    return None


@router.post("/signup")
async def signup(body: AuthRequest) -> dict:
    try:
        supabase = get_client()
        user = None

        if hasattr(supabase.auth, "admin") and hasattr(supabase.auth.admin, "create_user"):
            try:
                created = supabase.auth.admin.create_user({
                    "email": body.email,
                    "password": body.password,
                    "email_confirm": True,
                })
                user = created if isinstance(created, dict) else getattr(created, "user", None)
            except Exception:
                user = _get_user_by_email(supabase, body.email)
        else:
            result = supabase.auth.sign_up({
                "email": body.email,
                "password": body.password,
            })
            user = getattr(result, "user", None)

        if user is None:
            raise HTTPException(status_code=400, detail="Signup failed")

        user_id = str(user.get("id") if isinstance(user, dict) else getattr(user, "id"))
        email = user.get("email") if isinstance(user, dict) else getattr(user, "email", body.email)

        supabase.table("user_preferences").upsert(
            {
                "user_id": user_id,
                "summary_frequency": 7,
            },
            on_conflict="user_id",
        ).execute()

        return {
            "user_id": user_id,
            "email": email,
            "message": "Signup successful.",
        }
    except Exception as e:
        detail = str(e) or "Signup failed"
        raise HTTPException(status_code=400, detail=detail)


@router.post("/login")
async def login(body: AuthRequest) -> dict:
    try:
        supabase = get_client()
        result = supabase.auth.sign_in_with_password({
            "email": body.email,
            "password": body.password,
        })
        return {
            "access_token": result.session.access_token,
            "user_id": str(result.user.id),
            "email": result.user.email,
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e) or "Invalid credentials")
