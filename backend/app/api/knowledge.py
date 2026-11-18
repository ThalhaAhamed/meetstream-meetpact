"""Search, Ask, and person erasure."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import current_user, require_admin
from app.db import get_db
from app.models import User
from app.services import knowledge, retention
from app.services.extraction import AnalysisError

router = APIRouter(prefix="/api", tags=["knowledge"])


@router.get("/search")
def search(q: str, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return knowledge.search(db, user, q)


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)


@router.post("/ask")
async def ask(body: AskBody, db: Session = Depends(get_db), user: User = Depends(current_user)):
    """Answer a question from the meeting records this user is allowed to see."""
    try:
        return await knowledge.ask(db, user, body.question)
    except AnalysisError as exc:
        raise HTTPException(502, str(exc))


@router.post("/employees/{employee_id}/erase")
def erase(employee_id: str, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Delete everything recorded about one person (admin only, irreversible)."""
    counts = retention.erase_employee(db, employee_id, actor=admin.name)
    if not counts:
        raise HTTPException(404, "Employee not found.")
    return counts
