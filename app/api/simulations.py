from fastapi import APIRouter, Depends

from app.core.security import rate_limit
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


@router.post(
    "/code-review",
    response_model=ConversationRecord,
    dependencies=[Depends(rate_limit("simulation_code_review", limit=10, window_seconds=60))],
)
def simulate_code_review(request: CodeReviewSimulationRequest) -> ConversationRecord:
    return run_and_store_simulation(code_review_scenario.name, request.model_dump())


@router.post(
    "/customer-complaint",
    response_model=ConversationRecord,
    dependencies=[Depends(rate_limit("simulation_customer_complaint", limit=10, window_seconds=60))],
)
def simulate_customer_complaint(request: CustomerComplaintSimulationRequest) -> ConversationRecord:
    return run_and_store_simulation(customer_complaint_scenario.name, request.model_dump())


@router.post(
    "/technical-interview",
    response_model=ConversationRecord,
    dependencies=[Depends(rate_limit("simulation_technical_interview", limit=10, window_seconds=60))],
)
def simulate_technical_interview(request: TechnicalInterviewSimulationRequest) -> ConversationRecord:
    return run_and_store_simulation(technical_interview_scenario.name, request.model_dump())
