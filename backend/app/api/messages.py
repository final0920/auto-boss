"""messages — HR 对话消息（鉴权 AC12）。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.db import get_db
from app.models import Application, Job, Message, MessageRole
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


@router.get("/inbox", dependencies=[Depends(require_auth)])
async def inbox(db: Session = Depends(get_db)) -> list[dict]:
    """收件箱：仅含有 HR 回复的会话，带公司/岗位/HR 信息 + 最新消息。

    只返回存在 role=HR 消息、且未接管的 Application；按最新消息时间倒序。
    无 HR 回复的投递不进收件箱。
    注意：此路由必须注册在 /{msg_id} 之前，否则 'inbox' 会被当作 msg_id。
    """
    # 有 HR 回复的 application id（去重）
    hr_app_ids = db.exec(
        select(Message.application_id)
        .where(Message.role == MessageRole.HR)
        .distinct()
    ).all()
    result: list[dict] = []
    for app_id in hr_app_ids:
        app = db.get(Application, app_id)
        if app is None:
            continue
        job = db.get(Job, app.job_id)
        last = db.exec(
            select(Message)
            .where(Message.application_id == app_id)
            .order_by(Message.ts.desc())
            .limit(1)
        ).first()
        result.append({
            "application_id": app_id,
            "company": job.company if job else "",
            "title": job.title if job else "",
            "hr_name": job.hr_name if job else "",
            "salary": job.salary if job else "",
            "last_message": _msg_dict(last) if last else None,
        })
    result.sort(
        key=lambda r: (r["last_message"]["ts"] or "") if r["last_message"] else "",
        reverse=True,
    )
    return result



@router.get("/{msg_id}", dependencies=[Depends(require_auth)])
async def get_message(msg_id: int, db: Session = Depends(get_db)) -> dict:
    m = db.get(Message, msg_id)
    if m is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
    return _msg_dict(m)
