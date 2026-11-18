"""Session auth (signed cookie) and role checks."""
from __future__ import annotations

from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.config import secret_key
from app.db import get_db
from app.models import User

COOKIE = "ept_session"
MAX_AGE = 60 * 60 * 24 * 14


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(secret_key(), salt="ept-session")


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def set_session(response: Response, user: User) -> None:
    token = _serializer().dumps({"uid": user.id})
    response.set_cookie(COOKIE, token, max_age=MAX_AGE, httponly=True, samesite="lax")


def clear_session(response: Response) -> None:
    response.delete_cookie(COOKIE)


def optional_user(request: Request, db: Session = Depends(get_db)) -> Optional[User]:
    token = request.cookies.get(COOKIE)
    if not token:
        return None
    try:
        data = _serializer().loads(token, max_age=MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    return db.get(User, data.get("uid"))


def current_user(user: Optional[User] = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in first.")
    return user


def require_manager(user: User = Depends(current_user)) -> User:
    if user.role not in ("admin", "manager"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only managers and admins can do this.")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only admins can do this.")
    return user
