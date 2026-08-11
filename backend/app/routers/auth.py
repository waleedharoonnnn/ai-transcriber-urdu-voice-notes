from fastapi import APIRouter, HTTPException

from app.core.security import create_access_token, hash_password, verify_password
from app.db.database import execute, execute_returning, fetch_one
from app.models.schemas import AuthRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup")
async def signup(body: AuthRequest) -> dict:
    email = (body.email or "").strip().lower()
    if not email or not body.password:
        raise HTTPException(status_code=400, detail="Email and password are required.")

    existing = fetch_one("select id from users where email = %s", (email,))
    if existing:
        raise HTTPException(status_code=400, detail="An account with this email already exists.")

    password_hash = hash_password(body.password)
    rows = execute_returning(
        "insert into users (email, password_hash) values (%s, %s) returning id, email",
        (email, password_hash),
    )
    user = rows[0]

    execute(
        "insert into user_preferences (user_id, summary_frequency) values (%s, %s) "
        "on conflict (user_id) do nothing",
        (user["id"], 7),
    )

    return {
        "user_id": str(user["id"]),
        "email": user["email"],
        "message": "Signup successful.",
    }


@router.post("/login")
async def login(body: AuthRequest) -> dict:
    email = (body.email or "").strip().lower()
    user = fetch_one(
        "select id, email, password_hash from users where email = %s", (email,)
    )
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(str(user["id"]), user["email"])
    return {
        "access_token": token,
        "user_id": str(user["id"]),
        "email": user["email"],
    }
