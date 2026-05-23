from fastapi import APIRouter

from app.core.models import ConversationRecord
from app.core.simulation_runner import run_and_store_simulation
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
    return run_and_store_simulation(code_review_scenario.name, request.model_dump())


@router.post("/customer-complaint", response_model=ConversationRecord)
def simulate_customer_complaint(request: CustomerComplaintSimulationRequest) -> ConversationRecord:
    return run_and_store_simulation(customer_complaint_scenario.name, request.model_dump())


@router.post("/technical-interview", response_model=ConversationRecord)
def simulate_technical_interview(request: TechnicalInterviewSimulationRequest) -> ConversationRecord:
    return run_and_store_simulation(technical_interview_scenario.name, request.model_dump())
