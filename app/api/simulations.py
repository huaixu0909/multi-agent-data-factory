from fastapi import APIRouter

from app.core.database import save_conversation, update_persona_memory
from app.core.models import ConversationRecord
from app.scenarios.code_review import CodeReviewSimulationRequest, code_review_scenario
from app.scenarios.customer_complaint import (
    CustomerComplaintSimulationRequest,
    customer_complaint_scenario,
)
from app.scenarios.technical_interview import (
    TechnicalInterviewSimulationRequest,
    technical_interview_scenario,
)


router = APIRouter(prefix="/api/simulations", tags=["simulations"])


@router.post("/code-review", response_model=ConversationRecord)
def simulate_code_review(request: CodeReviewSimulationRequest) -> ConversationRecord:
    conversation = code_review_scenario.simulate(request)
    save_conversation(conversation)
    update_persona_memory(conversation)
    return conversation


@router.post("/customer-complaint", response_model=ConversationRecord)
def simulate_customer_complaint(request: CustomerComplaintSimulationRequest) -> ConversationRecord:
    conversation = customer_complaint_scenario.simulate(request)
    save_conversation(conversation)
    update_persona_memory(conversation)
    return conversation


@router.post("/technical-interview", response_model=ConversationRecord)
def simulate_technical_interview(request: TechnicalInterviewSimulationRequest) -> ConversationRecord:
    conversation = technical_interview_scenario.simulate(request)
    save_conversation(conversation)
    update_persona_memory(conversation)
    return conversation
