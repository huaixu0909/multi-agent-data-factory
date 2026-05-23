from fastapi import APIRouter, Query

from app.core.job_queue import get_batch_job, get_batch_jobs, submit_batch_job
from app.core.models import BatchJobCreateRequest, BatchJobListResponse, BatchJobRecord


router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.post("", response_model=BatchJobRecord)
def create_batch_job(request: BatchJobCreateRequest) -> BatchJobRecord:
    return submit_batch_job(request)


@router.get("", response_model=BatchJobListResponse)
def list_jobs(limit: int = Query(default=20, ge=1, le=100)) -> BatchJobListResponse:
    items = get_batch_jobs(limit=limit)
    return BatchJobListResponse(items=items, total=len(items))


@router.get("/{job_id}", response_model=BatchJobRecord)
def read_job(job_id: str) -> BatchJobRecord:
    return get_batch_job(job_id)
