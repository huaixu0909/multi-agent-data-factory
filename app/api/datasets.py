import json

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from app.core.database import (
    create_dataset_version,
    delete_dataset_version,
    find_dataset_version,
    list_dataset_versions,
    load_dataset_version_conversations,
    query_all_conversations,
    query_conversations,
)
from app.core.models import (
    ConversationRecord,
    DatasetVersionCreateRequest,
    DatasetVersionListResponse,
    DatasetVersionRecord,
)


router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("/export.jsonl", response_class=PlainTextResponse)
def export_dataset_jsonl(
    scenario: str | None = Query(default=None),
    accepted: bool | None = Query(default=None),
    min_score: float | None = Query(default=None, ge=0, le=10),
    max_score: float | None = Query(default=None, ge=0, le=10),
    q: str | None = Query(default=None),
) -> str:
    rows: list[str] = []
    page = 1
    while True:
        conversations, _, total_pages = query_conversations(
            scenario=scenario,
            accepted=accepted,
            min_score=min_score,
            max_score=max_score,
            q=q,
            page=page,
            page_size=100,
        )
        rows.extend(conversation_to_jsonl_row(conversation) for conversation in conversations)
        if page >= total_pages:
            break
        page += 1
    return "\n".join(rows)


@router.post("/versions", response_model=DatasetVersionRecord)
def create_version(request: DatasetVersionCreateRequest) -> DatasetVersionRecord:
    filters = {
        "scenario": request.scenario,
        "accepted": request.accepted,
        "min_score": request.min_score,
        "max_score": request.max_score,
        "q": request.q,
    }
    filters = {key: value for key, value in filters.items() if value is not None and value != ""}
    conversations = query_all_conversations(
        scenario=request.scenario,
        accepted=request.accepted,
        min_score=request.min_score,
        max_score=request.max_score,
        q=request.q,
    )
    return create_dataset_version(
        name=request.name.strip(),
        description=request.description.strip() if request.description else None,
        filters=filters,
        conversations=conversations,
    )


@router.get("/versions", response_model=DatasetVersionListResponse)
def get_versions(limit: int = Query(default=20, ge=1, le=100)) -> DatasetVersionListResponse:
    items = list_dataset_versions(limit=limit)
    return DatasetVersionListResponse(items=items, total=len(items))


@router.get("/versions/{version_id}", response_model=DatasetVersionRecord)
def get_version(version_id: str) -> DatasetVersionRecord:
    return find_dataset_version(version_id)


@router.delete("/versions/{version_id}")
def remove_version(version_id: str) -> dict[str, str]:
    delete_dataset_version(version_id)
    return {"status": "deleted", "version_id": version_id}


@router.get("/versions/{version_id}/export.jsonl", response_class=PlainTextResponse)
def export_version_jsonl(version_id: str) -> str:
    conversations = load_dataset_version_conversations(version_id)
    return "\n".join(conversation_to_jsonl_row(conversation) for conversation in conversations)


def conversation_to_jsonl_row(conversation: ConversationRecord) -> str:
    return json.dumps(
        {
            "conversation_id": conversation.conversation_id,
            "task_type": conversation.task_type,
            "scenario": conversation.scenario,
            "task_input": conversation.task_input,
            "generation_mode": conversation.generation_mode,
            "workflow_engine": conversation.workflow_engine,
            "workflow_steps": conversation.workflow_steps,
            "agent_trace": conversation.agent_trace,
            "llm_provider": conversation.llm_provider,
            "llm_model": conversation.llm_model,
            "scoring_mode": conversation.scoring_mode,
            "scoring_provider": conversation.scoring_provider,
            "scoring_model": conversation.scoring_model,
            "scoring_error": conversation.scoring_error,
            "score_feedback": conversation.score_feedback,
            "quality_report": conversation.quality_report.model_dump(),
            "content_hash": conversation.content_hash,
            "duplicate_of": conversation.duplicate_of,
            "similarity_score": conversation.similarity_score,
            "diversity_report": conversation.diversity_report.model_dump(),
            "agents": [agent.model_dump() for agent in conversation.agents],
            "messages": [
                {"role": message.role, "content": message.content}
                for message in conversation.messages
            ],
            "scores": conversation.scores.model_dump(),
        },
        ensure_ascii=False,
    )
