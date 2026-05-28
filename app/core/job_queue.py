import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from app.core.database import find_batch_job, list_batch_jobs, save_batch_job, update_batch_job
from app.core.models import BatchJobCreateRequest, BatchJobRecord
from app.core.simulation_runner import run_and_store_simulation


_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="data-factory-job")
_submit_lock = threading.Lock()
logger = logging.getLogger(__name__)


def submit_batch_job(request: BatchJobCreateRequest) -> BatchJobRecord:
    now = _utc_now()
    job = BatchJobRecord(
        job_id=f"job_{uuid.uuid4().hex[:12]}",
        scenario=request.scenario,
        status="queued",
        total=request.total,
        min_score=request.min_score,
        payload=request.payload,
        created_at=now,
    )
    save_batch_job(job)
    with _submit_lock:
        _executor.submit(_run_batch_job, job.job_id)
    return job


def get_batch_job(job_id: str) -> BatchJobRecord:
    return find_batch_job(job_id)


def get_batch_jobs(limit: int = 20) -> list[BatchJobRecord]:
    return list_batch_jobs(limit=limit)


def _run_batch_job(job_id: str) -> None:
    job = find_batch_job(job_id)
    update_batch_job(job_id, status="running", started_at=_utc_now())

    conversation_ids: list[str] = []
    completed = 0
    accepted = 0
    failed = 0
    last_error: str | None = None

    for index in range(job.total):
        try:
            conversation = run_and_store_simulation(job.scenario, _payload_for_turn(job.payload, index))
            conversation_ids.append(conversation.conversation_id)
            completed += 1
            if conversation.accepted and conversation.scores.final_score >= job.min_score:
                accepted += 1
        except Exception as error:
            logger.warning("Batch job item failed: job_id=%s index=%s", job_id, index + 1, exc_info=True)
            failed += 1
            last_error = str(error)[:800]

        update_batch_job(
            job_id,
            completed=completed,
            accepted=accepted,
            failed=failed,
            conversation_ids=conversation_ids,
            error=last_error,
        )

    status = "completed" if failed < job.total else "failed"
    update_batch_job(
        job_id,
        status=status,
        completed=completed,
        accepted=accepted,
        failed=failed,
        conversation_ids=conversation_ids,
        error=last_error,
        finished_at=_utc_now(),
    )


def _payload_for_turn(payload: dict, index: int) -> dict:
    next_payload = dict(payload)
    next_payload.setdefault("max_turns", 8)
    next_payload["batch_index"] = index + 1
    return next_payload


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()
