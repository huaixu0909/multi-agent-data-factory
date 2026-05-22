import json

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.core.database import load_conversations


router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.get("/export.jsonl", response_class=PlainTextResponse)
def export_dataset_jsonl() -> str:
    rows: list[str] = []
    for conversation in load_conversations():
        if not conversation.accepted:
            continue
        rows.append(
            json.dumps(
                {
                    "conversation_id": conversation.conversation_id,
                    "task_type": conversation.task_type,
                    "scenario": conversation.scenario,
                    "task_input": conversation.task_input,
                    "generation_mode": conversation.generation_mode,
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
    return "\n".join(rows)
