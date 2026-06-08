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
