from fastapi import APIRouter, Depends, Query

from app.core.database import delete_conversation, find_conversation, query_conversations
from app.core.models import ConversationListResponse, ConversationRecord
from app.core.security import require_admin


router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=ConversationListResponse)
def list_conversations(
    scenario: str | None = Query(default=None),
    accepted: bool | None = Query(default=None),
    min_score: float | None = Query(default=None, ge=0, le=10),
    max_score: float | None = Query(default=None, ge=0, le=10),
    q: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
) -> ConversationListResponse:
    items, total, total_pages = query_conversations(
        scenario=scenario,
        accepted=accepted,
        min_score=min_score,
        max_score=max_score,
        q=q,
        page=page,
        page_size=page_size,
    )
    return ConversationListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.get("/{conversation_id}", response_model=ConversationRecord)
def get_conversation(conversation_id: str) -> ConversationRecord:
    return find_conversation(conversation_id)


@router.delete("/{conversation_id}", dependencies=[Depends(require_admin)])
def remove_conversation(conversation_id: str) -> dict[str, str]:
    delete_conversation(conversation_id)
    return {"status": "deleted", "conversation_id": conversation_id}
