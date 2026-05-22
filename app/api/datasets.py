import json

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse

from app.core.database import query_conversations


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
        for conversation in conversations:
            rows.append(
                json.dumps(
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
                        "agents": [agent.model_dump() for agent in conversation.agents],
                        "messages": [
                            {"role": message.role, "content": message.content}
                            for message in conversation.messages
                        ],
                        "scores": conversation.scores.model_dump(),
                    },
                    ensure_ascii=False,
                )
            )
        if page >= total_pages:
            break
        page += 1
    return "\n".join(rows)
