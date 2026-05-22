from fastapi import APIRouter

from app.core.database import save_conversation
from app.core.models import ConversationRecord
from app.scenarios.code_review import CodeReviewSimulationRequest, code_review_scenario


router = APIRouter(prefix="/api/simulations", tags=["simulations"])


@router.post("/code-review", response_model=ConversationRecord)
def simulate_code_review(request: CodeReviewSimulationRequest) -> ConversationRecord:
    conversation = code_review_scenario.simulate(request)
    save_conversation(conversation)
    return conversation

