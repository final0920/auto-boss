"""messages — HR 对话消息（鉴权 AC12）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.db import get_db
from app.models import Message
from app.security.auth import require_auth

router = APIRouter(prefix="/messages", tags=["messages"])


def _msg_dict(m: Message) -> dict:
    return {
        "id": m.id,
        "application_id": m.application_id,
        "role": m.role.value,
        "text": m.text,
        "ts": m.ts.isoformat() if m.ts else None,
    }


@router.get("", dependencies=[Depends(require_auth)])
async def list_messages(
    application_id: int = Query(...),
    db: Session = Depends(get_db),
) -> list[dict]:
    msgs = db.exec(
        select(Message)
        .where(Message.application_id == application_id)
        .order_by(Message.ts)
    ).all()
    return [_msg_dict(m) for m in msgs]


@router.get("/{msg_id}", dependencies=[Depends(require_auth)])
async def get_message(msg_id: int, db: Session = Depends(get_db)) -> dict:
    m = db.get(Message, msg_id)
    if m is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return _msg_dict(m)
