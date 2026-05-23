from typing import Any

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


def run_and_store_simulation(scenario: str, payload: dict[str, Any]) -> ConversationRecord:
    if scenario == "code_review":
        conversation = code_review_scenario.simulate(CodeReviewSimulationRequest(**payload))
    elif scenario == "customer_complaint":
        conversation = customer_complaint_scenario.simulate(CustomerComplaintSimulationRequest(**payload))
    elif scenario == "technical_interview":
        conversation = technical_interview_scenario.simulate(TechnicalInterviewSimulationRequest(**payload))
    else:
        raise ValueError(f"Unsupported scenario: {scenario}")

    save_conversation(conversation)
    update_persona_memory(conversation)
    return conversation
