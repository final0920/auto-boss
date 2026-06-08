"""scheduled — 定时任务管理（鉴权 AC12）。

通过 APScheduler 管理巡检/夜停/限速窗口定时任务。
调度器实例挂载在 app.state.scheduler，由 main.py lifespan 初始化。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.security.auth import require_auth

router = APIRouter(prefix="/scheduled", tags=["scheduled"])


def _get_scheduler(request: Request):
    scheduler = getattr(request.app.state, "scheduler", None)
    if scheduler is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Scheduler not initialized",
        )
    return scheduler


@router.get("", dependencies=[Depends(require_auth)])
async def list_jobs(request: Request) -> list[dict]:
    """列出所有已调度任务。"""
    scheduler = _get_scheduler(request)
    jobs = scheduler.get_jobs()
    return [
        {
            "id": j.id,
            "name": j.name,
            "next_run": j.next_run_time.isoformat() if j.next_run_time else None,
            "trigger": str(j.trigger),
        }
        for j in jobs
    ]


@router.post("/{job_id}/pause", dependencies=[Depends(require_auth)])
async def pause_job(job_id: str, request: Request) -> dict:
    scheduler = _get_scheduler(request)
    try:
        scheduler.pause_job(job_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return {"paused": job_id}


@router.post("/{job_id}/resume", dependencies=[Depends(require_auth)])
async def resume_job(job_id: str, request: Request) -> dict:
    scheduler = _get_scheduler(request)
    try:
        scheduler.resume_job(job_id)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    return {"resumed": job_id}
