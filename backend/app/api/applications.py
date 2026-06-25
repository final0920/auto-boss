"""applications — 投递看板 + SENDING 待确认队列 + 人工确认归位（AC8）。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlmodel import Session, select

from app.db import get_db
from app.models import Application, ApplicationStatus, Job
from app.security.auth import require_auth

router = APIRouter(prefix="/applications", tags=["applications"])


def _app_dict(a: Application, job: Optional[Job] = None) -> dict:
    d = {
        "id": a.id,
        "job_id": a.job_id,
        "status": a.status.value,
        "greeting": a.greeting,
        "fail_reason": a.fail_reason,
        "sent_at": a.sent_at.isoformat() if a.sent_at else None,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "updated_at": a.updated_at.isoformat() if a.updated_at else None,
    }
    if job is not None:
        d["job"] = {
            "title": job.title,
            "company": job.company,
            "salary": job.salary,
            "salary_min_k": job.salary_min_k,
            "salary_max_k": job.salary_max_k,
            "area": job.area,
            "jd": job.jd,
            "score": job.score,
            "reasons": job.reasons,
            "degree": job.degree,
            "experience": job.experience,
            "company_scale": job.company_scale,
            "finance_stage": job.finance_stage,
            "hr_name": job.hr_name,
            "hr_active": job.hr_active,
        }
    return d


def _apply_filters(stmt, status_filter: Optional[str], keyword: Optional[str]):
    """把 status + keyword 过滤条件下推到 SQL（list 与 count 共用，保证一致）。"""
    if status_filter:
        try:
            st = ApplicationStatus(status_filter.upper())
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid status filter: {status_filter}",
            )
        stmt = stmt.where(Application.status == st)
    if keyword:
        kw = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(Job.company.like(kw), Job.title.like(kw), Job.jd.like(kw)))
    return stmt


@router.get("", dependencies=[Depends(require_auth)])
async def list_applications(
    status_filter: Optional[str] = Query(None, alias="status"),
    keyword: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    db: Session = Depends(get_db),
) -> dict:
    """投递历史（分页 + 状态/关键词筛选，join Job 全字段）。

    返回 {items, total, skip, limit}；total 为同筛选条件下的全量计数，供前端算页数。
    keyword 匹配 公司/岗位/JD。
    """
    base = select(Application, Job).join(Job, Application.job_id == Job.id)  # type: ignore[arg-type]
    base = _apply_filters(base, status_filter, keyword)
    count_stmt = select(func.count()).select_from(Application).join(  # type: ignore[arg-type]
        Job, Application.job_id == Job.id
    )
    count_stmt = _apply_filters(count_stmt, status_filter, keyword)
    total = db.exec(count_stmt).one()
    rows = db.exec(
        base.order_by(Application.id.desc()).offset(skip).limit(limit)  # type: ignore[attr-defined]
    ).all()
    return {
        "items": [_app_dict(a, j) for a, j in rows],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.delete("/clear", dependencies=[Depends(require_auth)])
async def clear_history(db: Session = Depends(get_db)) -> dict:
    """清空全部投递历史（application/job/message/run_log/quota），保留规则配置。

    必须注册在 /{app_id} 之前，否则 "clear" 会被当作 app_id 匹配。
    """
    from sqlmodel import delete

    from app.models import Job, Message, Quota, RunLog

    counts: dict[str, int] = {}
    for model in (Message, RunLog, Application, Job, Quota):
        res = db.exec(delete(model))
        counts[model.__tablename__] = res.rowcount or 0
    db.commit()
    return {"cleared": counts}


@router.get("/sending", dependencies=[Depends(require_auth)])
async def list_sending(db: Session = Depends(get_db)) -> list[dict]:
    """SENDING 待人工确认队列（join Job 显示岗位信息；AC8 崩溃恢复）。"""
    rows = db.exec(
        select(Application, Job)
        .join(Job, Application.job_id == Job.id)  # type: ignore[arg-type]
        .where(Application.status == ApplicationStatus.SENDING)
    ).all()
    return [_app_dict(a, j) for a, j in rows]


@router.get("/stats", dependencies=[Depends(require_auth)])
async def applications_stats(
    keyword: Optional[str] = Query(None),
    db: Session = Depends(get_db),
) -> dict:
    """各状态全局计数（供筛选 chips 角标）。keyword 与列表一致（仅匹配公司/岗位/JD）。

    返回 {'': 总数, 'SENT': n, 'FAILED': n, ...}。必须注册在 /{app_id} 之前。
    """
    stmt = (
        select(Application.status, func.count())  # type: ignore[arg-type]
        .select_from(Application)
        .join(Job, Application.job_id == Job.id)  # type: ignore[arg-type]
    )
    if keyword:
        kw = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(Job.company.like(kw), Job.title.like(kw), Job.jd.like(kw)))
    stmt = stmt.group_by(Application.status)  # type: ignore[arg-type]
    result: dict[str, int] = {}
    total = 0
    for st, cnt in db.exec(stmt).all():
        result[st.value] = cnt
        total += cnt
    result[""] = total
    return result


@router.get("/{app_id}", dependencies=[Depends(require_auth)])
async def get_application(app_id: int, db: Session = Depends(get_db)) -> dict:
    a = db.get(Application, app_id)
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    return _app_dict(a)


@router.post("/{app_id}/confirm", dependencies=[Depends(require_auth)])
async def confirm_sending(
    app_id: int,
    body: dict,
    db: Session = Depends(get_db),
) -> dict:
    """人工确认 SENDING 记录归位（sent=True→SENT，sent=False→FAILED）。AC8。"""
    a = db.get(Application, app_id)
    if a is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Application not found")
    if a.status != ApplicationStatus.SENDING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Application is not in SENDING state (current: {a.status.value})",
        )
    sent = bool(body.get("sent", False))
    a.status = ApplicationStatus.SENT if sent else ApplicationStatus.FAILED
    a.fail_reason = "" if sent else str(body.get("reason", "manual_confirm_failed"))
    if sent:
        a.sent_at = datetime.now()
    a.updated_at = datetime.now()
    db.add(a)
    db.commit()
    db.refresh(a)
    return _app_dict(a)
