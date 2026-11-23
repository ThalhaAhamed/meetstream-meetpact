from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api import serializers as S
from app.auth import clear_session, current_user, hash_password, optional_user, set_session, verify_password
from app.db import get_db
from app.models import Employee, User

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SetupBody(BaseModel):
    name: str = Field(min_length=1)
    email: str = Field(min_length=3)
    password: str = Field(min_length=8)


class LoginBody(BaseModel):
    email: str
    password: str


@router.get("/state")
def state(db: Session = Depends(get_db), user: Optional[User] = Depends(optional_user)):
    count = db.scalar(select(func.count(User.id)))
    return {"needs_setup": count == 0, "user": S.user(user) if user else None}


@router.post("/setup")
def setup(body: SetupBody, response: Response, db: Session = Depends(get_db)):
    """Create the first admin. Only allowed while there are no users."""
    if db.scalar(select(func.count(User.id))):
        raise HTTPException(409, "Setup is already done. Sign in instead.")
    emp = Employee(name=body.name, email=body.email.lower())
    db.add(emp)
    db.flush()
    user = User(email=body.email.lower(), name=body.name, password_hash=hash_password(body.password), role="admin", employee_id=emp.id)
    db.add(user)
    db.commit()
    set_session(response, user)
    return S.user(user)


@router.post("/login")
def login(body: LoginBody, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower().strip()))
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Email or password is wrong.")
    set_session(response, user)
    return S.user(user)


@router.post("/logout")
def logout(response: Response):
    clear_session(response)
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return S.user(user)
