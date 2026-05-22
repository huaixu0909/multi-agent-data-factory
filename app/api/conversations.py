from fastapi import APIRouter, Query

from app.core.database import find_conversation, load_conversations
from app.core.models import ConversationListResponse, ConversationRecord


router = APIRouter(prefix="/api/conversations", tags=["conversations"])


@router.get("", response_model=ConversationListResponse)
def list_conversations(scenario: str | None = Query(default=None)) -> ConversationListResponse:
    items = load_conversations(scenario=scenario)
    return ConversationListResponse(items=items, total=len(items))


@router.get("/{conversation_id}", response_model=ConversationRecord)
def get_conversation(conversation_id: str) -> ConversationRecord:
    return find_conversation(conversation_id)

