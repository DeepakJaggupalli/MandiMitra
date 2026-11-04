"""Staff login with role-based access (JWT). Farmers use the app without an account."""
from __future__ import annotations

import hmac
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from backend.app.settings import JWT_SECRET, STAFF_USERS, TOKEN_HOURS

bearer = HTTPBearer(auto_error=False)


def authenticate(username: str, password: str) -> dict | None:
    for u in STAFF_USERS:
        if hmac.compare_digest(u["username"], username.strip().lower()) and hmac.compare_digest(u["password"], password):
            return {"username": u["username"], "role": u["role"], "name": u.get("name", u["username"])}
    return None


def make_token(user: dict) -> str:
    payload = {**user, "exp": datetime.now(timezone.utc) + timedelta(hours=TOKEN_HOURS)}
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def current_user(cred: HTTPAuthorizationCredentials | None = Depends(bearer)) -> dict | None:
    if not cred:
        return None
    try:
        data = jwt.decode(cred.credentials, JWT_SECRET, algorithms=["HS256"])
        return {"username": data["username"], "role": data["role"], "name": data.get("name", data["username"])}
    except jwt.PyJWTError:
        return None


def require(*roles: str):
    def dep(user: dict | None = Depends(current_user)) -> dict:
        if user is None:
            raise HTTPException(401, "Please log in")
        if roles and user["role"] not in roles:
            raise HTTPException(403, "Your role cannot do this")
        return user

    return dep
