from typing import Any, Literal

from pydantic import BaseModel, Field


AgentRole = str
ScenarioName = Literal["code_review"]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    timestamp: str


class Persona(BaseModel):
    agent_id: str
    role: AgentRole
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
    created_at: str


class ConversationListResponse(BaseModel):
    items: list[ConversationRecord]
    total: int


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

