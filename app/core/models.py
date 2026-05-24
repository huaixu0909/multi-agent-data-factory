from typing import Any, Literal

from pydantic import BaseModel, Field


AgentRole = str
ScenarioName = Literal["code_review", "customer_complaint", "technical_interview"]
BatchJobStatus = Literal["queued", "running", "completed", "failed"]


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
    memory_notes: list[str] = Field(default_factory=list)
    success_patterns: list[str] = Field(default_factory=list)
    failure_patterns: list[str] = Field(default_factory=list)
    strategy_notes: list[str] = Field(default_factory=list)


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


class QualityReport(BaseModel):
    grade: str = "C"
    decision: str = "review"
    pass_threshold: float = 7.0
    judge_votes: list[dict[str, Any]] = Field(default_factory=list)
    dimension_diagnostics: list[dict[str, Any]] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    improvement_actions: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)


class DiversityReport(BaseModel):
    content_hash: str = ""
    duplicate_level: str = "unchecked"
    duplicate_of: str | None = None
    similarity_score: float = Field(default=0, ge=0, le=1)
    uniqueness_score: float = Field(default=1, ge=0, le=1)
    recommendation: str = ""
    signals: list[str] = Field(default_factory=list)


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
    quality_report: QualityReport = Field(default_factory=QualityReport)
    content_hash: str | None = None
    duplicate_of: str | None = None
    similarity_score: float = Field(default=0, ge=0, le=1)
    diversity_report: DiversityReport = Field(default_factory=DiversityReport)
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
    success_patterns: list[str] = Field(default_factory=list)
    failure_patterns: list[str] = Field(default_factory=list)
    strategy_notes: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str


class PersonaListResponse(BaseModel):
    items: list[PersonaRecord]
    total: int


class BatchJobCreateRequest(BaseModel):
    scenario: ScenarioName
    payload: dict[str, Any] = Field(default_factory=dict)
    total: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0, ge=0, le=10)


class BatchJobRecord(BaseModel):
    job_id: str
    scenario: ScenarioName
    status: BatchJobStatus
    total: int
    completed: int = 0
    accepted: int = 0
    failed: int = 0
    min_score: float = 0
    payload: dict[str, Any] = Field(default_factory=dict)
    conversation_ids: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: str
    started_at: str | None = None
    finished_at: str | None = None


class BatchJobListResponse(BaseModel):
    items: list[BatchJobRecord]
    total: int


class DatasetVersionCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    scenario: str | None = None
    accepted: bool | None = None
    min_score: float | None = Field(default=None, ge=0, le=10)
    max_score: float | None = Field(default=None, ge=0, le=10)
    q: str | None = None


class DatasetVersionRecord(BaseModel):
    version_id: str
    name: str
    description: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    conversation_ids: list[str] = Field(default_factory=list)
    total: int = 0
    accepted: int = 0
    average_score: float = 0
    duplicate_count: int = 0
    duplicate_rate: float = 0
    diversity_score: float = 1
    created_at: str


class DatasetVersionListResponse(BaseModel):
    items: list[DatasetVersionRecord]
    total: int
