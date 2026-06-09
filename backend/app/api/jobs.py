"""jobs — 岗位列表/详情/打分/黑名单（鉴权 AC12）。"""
from __future__ import annotations


from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session, select

from app.db import get_db
from app.models import Job
from app.security.auth import require_auth

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("", dependencies=[Depends(require_auth)])
async def list_jobs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[dict]:
    jobs = db.exec(select(Job).offset(skip).limit(limit)).all()
    return [_job_dict(j) for j in jobs]


@router.get("/{job_id}", dependencies=[Depends(require_auth)])
async def get_job(job_id: int, db: Session = Depends(get_db)) -> dict:
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return _job_dict(job)


@router.post("/fetch", dependencies=[Depends(require_auth)])
async def trigger_fetch() -> dict:
    """触发岗位抓取（stub）。

    TODO 真机阶段：经 device_mode 锁调用 pipeline.collector 抓取当前列表页岗位。
    当前返回占位，便于前端按钮联调。
    """
    return {"triggered": True, "note": "stub — 真机阶段接 pipeline.collector"}


@router.post("/{job_id}/blacklist", dependencies=[Depends(require_auth)])
async def set_blacklist(job_id: int, body: dict) -> dict:
    """加入/移出黑名单（stub）。

    TODO 真机阶段：持久化（需 Job.blacklisted 字段 + 迁移），筛选时跳过。
    """
    return {"id": job_id, "blacklisted": bool(body.get("blacklisted", True))}


@router.post("/{job_id}/pin", dependencies=[Depends(require_auth)])
async def set_pin(job_id: int, body: dict) -> dict:
    """置顶/取消置顶（stub）。

    TODO 真机阶段：持久化（需 Job.pinned 字段 + 迁移）。
    """
    return {"id": job_id, "pinned": bool(body.get("pinned", True))}


def _job_dict(j: Job) -> dict:
    return {
        "id": j.id,
        "title": j.title,
        "company": j.company,
        "salary": j.salary,
        "area": j.area,
        "jd": j.jd,
        "score": j.score,
        "reasons": j.reasons,
        "created_at": j.created_at.isoformat() if j.created_at else None,
    }
