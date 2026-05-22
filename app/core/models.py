from typing import Any, Literal

from pydantic import BaseModel, Field


AgentRole = str
ScenarioName = Literal["code_review", "customer_complaint", "technical_interview"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    timestamp: str


class Persona(BaseModel):
    persona_id: str | None = None
    agent_id: str
    role: AgentRole
    name: str | None = None
    personality: str
    style: str
    focus: str
    goal: str
    tolerance: str


class Message(BaseModel):
    turn: int
    agent_id: str
    role: AgentRole
    content: str


class QualityScores(BaseModel):
    realism: float = Field(..., ge=0, le=10)
    difficulty: float = Field(..., ge=0, le=10)
    diversity: float = Field(..., ge=0, le=10)
    consistency: float = Field(..., ge=0, le=10)
    conflict: float = Field(..., ge=0, le=10)
    training_value: float = Field(..., ge=0, le=10)
    safety: float = Field(..., ge=0, le=10)
    final_score: float = Field(..., ge=0, le=10)


class ConversationRecord(BaseModel):
    conversation_id: str
    task_type: str
    scenario: str
    language: str | None = None
    code_diff: str | None = None
    review_focus: list[str] = Field(default_factory=list)
    task_input: dict[str, Any] = Field(default_factory=dict)
    agents: list[Persona]
    messages: list[Message]
    scores: QualityScores
    accepted: bool
    generation_mode: str = "mock"
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_error: str | None = None
    scoring_mode: str = "heuristic"
    scoring_provider: str | None = None
    scoring_model: str | None = None
    scoring_error: str | None = None
    score_feedback: list[str] = Field(default_factory=list)
    workflow_engine: str = "legacy"
    workflow_steps: list[str] = Field(default_factory=list)
    agent_trace: list[dict[str, Any]] = Field(default_factory=list)
    created_at: str


class ConversationListResponse(BaseModel):
    items: list[ConversationRecord]
    total: int
    page: int = 1
    page_size: int = 10
    total_pages: int = 1


class ScenarioDescriptor(BaseModel):
    name: str
    title: str
    description: str
    status: str
    agent_roles: list[str]
    endpoint: str


class ScenarioListResponse(BaseModel):
    items: list[ScenarioDescriptor]
    total: int


class PersonaRecord(BaseModel):
    persona_id: str
    scenario: str
    role: AgentRole
    name: str
    personality: str
    style: str
    focus: str
    goal: str
    tolerance: str
    usage_count: int = 0
    average_score: float = 0.0
    success_count: int = 0
    weight: float = 1.0
    memory_notes: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class PersonaListResponse(BaseModel):
    items: list[PersonaRecord]
    total: int
