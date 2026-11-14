import hashlib
import secrets
import time
from collections import defaultdict, deque

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request

from . import config, db

ph = PasswordHasher()
_hits: dict[str, deque] = defaultdict(deque)


def client_ip(req: Request) -> str:
    xf = req.headers.get("x-forwarded-for")
    return xf.split(",")[0].strip() if xf else (req.client.host if req.client else "?")


def rate_limit(key: str, n: int, per_s: int):
    q = _hits[key]
    now = time.time()
    while q and q[0] < now - per_s:
        q.popleft()
    if len(q) >= n:
        raise HTTPException(429, {"success": False, "error": f"Rate limit: max {n} requests per {per_s}s",
                                  "code": "RATE_LIMITED"})
    q.append(now)


def make_token(uid: int) -> str:
    return jwt.encode({"sub": str(uid), "exp": int(time.time()) + 7 * 86400}, config.JWT_SECRET, algorithm="HS256")


def hash_key(k: str) -> str:
    return hashlib.sha256(k.encode()).hexdigest()


async def signup(email: str, password: str) -> int:
    email = email.strip().lower()
    if "@" not in email or len(email) > 200:
        raise HTTPException(400, {"success": False, "error": "Invalid email"})
    if len(password) < 8:
        raise HTTPException(400, {"success": False, "error": "Password must be at least 8 characters"})
    try:
        return await db.P().fetchval("INSERT INTO users(email,pw_hash,webhook_secret) VALUES($1,$2,$3) RETURNING id",
                                     email, ph.hash(password), secrets.token_hex(24))
    except Exception:
        raise HTTPException(409, {"success": False, "error": "Account already exists; log in instead"})


async def login(email: str, password: str) -> int:
    row = await db.P().fetchrow("SELECT id,pw_hash FROM users WHERE email=$1", email.strip().lower())
    try:
        if not row or not ph.verify(row["pw_hash"], password):
            raise VerifyMismatchError
    except VerifyMismatchError:
        raise HTTPException(401, {"success": False, "error": "Wrong email or password"})
    return row["id"]


async def create_key(uid: int, name: str | None) -> str:
    k = "cm-" + secrets.token_urlsafe(30)
    await db.P().execute("INSERT INTO api_keys(user_id,key_hash,prefix,name) VALUES($1,$2,$3,$4)",
                         uid, hash_key(k), k[:9], name or "default")
    return k


async def current_user(req: Request) -> int:
    h = req.headers.get("authorization", "")
    tok = h[7:].strip() if h.lower().startswith("bearer ") else req.query_params.get("token", "")
    if not tok:
        raise HTTPException(401, {"success": False, "error": "Missing Authorization: Bearer <token or API key>"})
    uid = None
    if tok.startswith(("cm-", "fc-")):
        uid = await db.P().fetchval("SELECT user_id FROM api_keys WHERE key_hash=$1 AND NOT revoked", hash_key(tok))
    else:
        try:
            uid = int(jwt.decode(tok, config.JWT_SECRET, algorithms=["HS256"])["sub"])
        except Exception:
            uid = None
    if not uid:
        raise HTTPException(401, {"success": False, "error": "Invalid or expired token/API key"})
    rate_limit(f"u:{uid}", 120, 60)
    return uid


async def charge(uid: int, endpoint: str, credits: int):
    await db.P().execute("INSERT INTO usage(user_id,endpoint,credits) VALUES($1,$2,$3)", uid, endpoint, credits)


async def used_today(uid: int) -> int:
    return await db.P().fetchval("SELECT coalesce(sum(credits),0) FROM usage WHERE user_id=$1 AND at > now() - interval '1 day'", uid)


async def require_credits(uid: int, need: int = 1):
    used = await used_today(uid)
    if used + need > config.DAILY_CREDITS:
        raise HTTPException(402, {"success": False, "code": "CREDITS_EXHAUSTED",
                                  "error": f"Daily credit limit reached ({used}/{config.DAILY_CREDITS} in last 24h)"})


User = Depends(current_user)
