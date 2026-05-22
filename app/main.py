import json
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATABASE_FILE = DATA_DIR / "factory.db"
APP_VERSION = "0.1.0"

AgentRole = Literal["Developer", "Reviewer", "Challenger", "Judge"]


app = FastAPI(
    title="Multi-Agent Synthetic Data Factory",
    description="A local MVP for multi-agent code review dialogue generation.",
    version=APP_VERSION,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


class CodeReviewSimulationRequest(BaseModel):
    language: str = Field(default="python", max_length=40)
    code_diff: str = Field(..., min_length=1, max_length=12000)
    review_focus: list[str] = Field(default_factory=lambda: ["bug", "security", "performance"])
    max_turns: int = Field(default=8, ge=6, le=12)


class ConversationRecord(BaseModel):
    conversation_id: str
    task_type: Literal["code_review"]
    language: str
    code_diff: str
    review_focus: list[str]
    agents: list[Persona]
    messages: list[Message]
    scores: QualityScores
    accepted: bool
    created_at: str


class ConversationListResponse(BaseModel):
    items: list[ConversationRecord]
    total: int


class CodeIssue(BaseModel):
    issue_type: str
    severity: Literal["low", "medium", "high"]
    evidence: str
    suggestion: str


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    initialize_database()


def open_database() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_FILE)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open_database() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                task_type TEXT NOT NULL,
                language TEXT NOT NULL,
                code_diff TEXT NOT NULL,
                review_focus TEXT NOT NULL,
                agents TEXT NOT NULL,
                messages TEXT NOT NULL,
                scores TEXT NOT NULL,
                accepted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at DESC)"
        )
        connection.commit()


def conversation_to_row(conversation: ConversationRecord) -> tuple[str, str, str, str, str, str, str, str, int, str]:
    return (
        conversation.conversation_id,
        conversation.task_type,
        conversation.language,
        conversation.code_diff,
        json.dumps(conversation.review_focus, ensure_ascii=False),
        json.dumps([agent.model_dump() for agent in conversation.agents], ensure_ascii=False),
        json.dumps([message.model_dump() for message in conversation.messages], ensure_ascii=False),
        json.dumps(conversation.scores.model_dump(), ensure_ascii=False),
        1 if conversation.accepted else 0,
        conversation.created_at,
    )


def row_to_conversation(row: sqlite3.Row) -> ConversationRecord:
    return ConversationRecord(
        conversation_id=str(row["conversation_id"]),
        task_type="code_review",
        language=str(row["language"]),
        code_diff=str(row["code_diff"]),
        review_focus=json.loads(str(row["review_focus"] or "[]")),
        agents=[Persona(**item) for item in json.loads(str(row["agents"] or "[]"))],
        messages=[Message(**item) for item in json.loads(str(row["messages"] or "[]"))],
        scores=QualityScores(**json.loads(str(row["scores"] or "{}"))),
        accepted=bool(row["accepted"]),
        created_at=str(row["created_at"]),
    )


def save_conversation(conversation: ConversationRecord) -> None:
    ensure_data_dirs()
    with open_database() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO conversations (
                conversation_id, task_type, language, code_diff, review_focus,
                agents, messages, scores, accepted, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            conversation_to_row(conversation),
        )
        connection.commit()


def load_conversations() -> list[ConversationRecord]:
    ensure_data_dirs()
    with open_database() as connection:
        rows = connection.execute(
            """
            SELECT conversation_id, task_type, language, code_diff, review_focus,
                   agents, messages, scores, accepted, created_at
            FROM conversations
            ORDER BY created_at DESC
            """
        ).fetchall()
    return [row_to_conversation(row) for row in rows]


def find_conversation(conversation_id: str) -> ConversationRecord:
    ensure_data_dirs()
    with open_database() as connection:
        row = connection.execute(
            """
            SELECT conversation_id, task_type, language, code_diff, review_focus,
                   agents, messages, scores, accepted, created_at
            FROM conversations
            WHERE conversation_id = ?
            """,
            (conversation_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return row_to_conversation(row)


def generate_personas(review_focus: list[str]) -> list[Persona]:
    focus_text = ", ".join(review_focus) if review_focus else "code quality"
    return [
        Persona(
            agent_id="agent_developer",
            role="Developer",
            personality="pragmatic",
            style="defensive but cooperative",
            focus="shipping speed and implementation intent",
            goal="explain the change and get the review accepted",
            tolerance="medium",
        ),
        Persona(
            agent_id="agent_reviewer",
            role="Reviewer",
            personality="strict",
            style="precise and evidence-driven",
            focus=focus_text,
            goal="identify concrete risks and request actionable fixes",
            tolerance="low",
        ),
        Persona(
            agent_id="agent_challenger",
            role="Challenger",
            personality="skeptical",
            style="argumentative and alternative-seeking",
            focus="edge cases and trade-offs",
            goal="increase reasoning depth by challenging easy conclusions",
            tolerance="low",
        ),
        Persona(
            agent_id="agent_judge",
            role="Judge",
            personality="balanced",
            style="concise and criteria-based",
            focus="training data quality and final decision",
            goal="summarize the discussion and label the review outcome",
            tolerance="high",
        ),
    ]


def detect_code_issues(code_diff: str, language: str) -> list[CodeIssue]:
    lower = code_diff.lower()
    issues: list[CodeIssue] = []

    patterns = [
        (
            "security",
            "high",
            ["select ", " where ", "f\"", "format(", "%"],
            "Potential SQL injection or unsafe query construction. Prefer parameterized queries.",
        ),
        (
            "security",
            "high",
            ["eval(", "exec("],
            "Dynamic code execution can become remote code execution. Remove eval/exec or sandbox strictly.",
        ),
        (
            "secret",
            "high",
            ["api_key", "password", "secret", "token"],
            "Possible hardcoded secret. Move sensitive values into environment variables or a secret manager.",
        ),
        (
            "reliability",
            "medium",
            ["except:", "except exception"],
            "Broad exception handling can hide failures. Catch specific exceptions and log context.",
        ),
        (
            "observability",
            "low",
            ["print("],
            "Debug prints are not production logging. Use structured logging with request context.",
        ),
        (
            "performance",
            "medium",
            ["for ", "query(", "select "],
            "Loop-level database calls may create N+1 queries. Batch loading or prefetching may be safer.",
        ),
        (
            "testing",
            "medium",
            ["def ", "class ", "return "],
            "The diff appears functional but has no visible test update. Add a regression test for the changed behavior.",
        ),
    ]

    for issue_type, severity, tokens, suggestion in patterns:
        if all(token in lower for token in tokens[:2]) or any(token in lower for token in tokens[2:]):
            evidence = next((line.strip() for line in code_diff.splitlines() if any(token in line.lower() for token in tokens)), "")
            issues.append(
                CodeIssue(
                    issue_type=issue_type,
                    severity=severity,  # type: ignore[arg-type]
                    evidence=evidence[:220] or f"{language} diff contains {issue_type} signal",
                    suggestion=suggestion,
                )
            )

    if not issues:
        issues.append(
            CodeIssue(
                issue_type="maintainability",
                severity="medium",
                evidence="No obvious syntactic risk was detected from simple heuristics.",
                suggestion="Ask reviewers to focus on naming, boundary conditions, tests, and rollback behavior.",
            )
        )

    unique: list[CodeIssue] = []
    seen: set[str] = set()
    for issue in issues:
        key = f"{issue.issue_type}:{issue.suggestion}"
        if key not in seen:
            seen.add(key)
            unique.append(issue)
    return unique[:5]


def message(turn: int, agent: Persona, content: str) -> Message:
    return Message(turn=turn, agent_id=agent.agent_id, role=agent.role, content=content)


def generate_messages(agents: list[Persona], issues: list[CodeIssue], max_turns: int) -> list[Message]:
    developer, reviewer, challenger, judge = agents
    primary = issues[0]
    secondary = issues[1] if len(issues) > 1 else issues[0]
    messages = [
        message(
            1,
            developer,
            "I submitted this diff to unblock the feature quickly. The intent is to keep the change small and avoid touching unrelated modules.",
        ),
        message(
            2,
            reviewer,
            f"I see a {primary.severity}-severity {primary.issue_type} risk. Evidence: `{primary.evidence}`. {primary.suggestion}",
        ),
        message(
            3,
            developer,
            "That concern is fair, but the input currently comes from an internal path. I chose the smaller change because the release is time-sensitive.",
        ),
        message(
            4,
            challenger,
            "Internal input is not a stable safety boundary. If this code path is reused later, the risk becomes invisible. We should fix the design rather than rely on caller discipline.",
        ),
        message(
            5,
            reviewer,
            f"There is also a {secondary.issue_type} concern: `{secondary.evidence}`. The review should require a test or a safer implementation before approval.",
        ),
        message(
            6,
            developer,
            "I can update the patch with a safer implementation and add a regression test. I would prefer not to expand the scope beyond the risky path.",
        ),
        message(
            7,
            challenger,
            "A narrow fix is acceptable if the test proves the risky case. Otherwise this becomes a style-only review and loses training value.",
        ),
        message(
            8,
            judge,
            "Decision: request changes. The discussion contains a concrete risk, evidence from the diff, a counterargument, and an actionable resolution. This is useful code review training data.",
        ),
    ]

    if max_turns >= 10:
        messages.insert(
            6,
            message(
                7,
                reviewer,
                "Please include the exact failure mode in the test name so future maintainers understand why the safer path exists.",
            ),
        )
        messages.insert(
            7,
            message(
                8,
                developer,
                "Agreed. I will add the test name and keep the implementation localized to this function.",
            ),
        )

    return [
        Message(turn=index + 1, agent_id=item.agent_id, role=item.role, content=item.content)
        for index, item in enumerate(messages[:max_turns])
    ]


def score_conversation(messages: list[Message], issues: list[CodeIssue]) -> QualityScores:
    role_count = len({message.role for message in messages})
    conflict_signals = sum(
        1
        for item in messages
        if any(token in item.content.lower() for token in ["risk", "concern", "not", "should", "otherwise"])
    )
    evidence_count = sum(1 for item in messages if "`" in item.content or "Evidence:" in item.content)
    high_severity = sum(1 for issue in issues if issue.severity == "high")

    realism = min(10.0, 6.2 + len(messages) * 0.18 + role_count * 0.35)
    difficulty = min(10.0, 5.8 + len(issues) * 0.55 + high_severity * 0.45)
    diversity = min(10.0, 5.5 + role_count * 0.8)
    consistency = min(10.0, 7.2 + evidence_count * 0.25)
    conflict = min(10.0, 5.0 + conflict_signals * 0.45)
    training_value = min(10.0, 6.0 + evidence_count * 0.4 + len(issues) * 0.35)
    safety = 9.0
    final_score = round(
        realism * 0.16
        + difficulty * 0.16
        + diversity * 0.12
        + consistency * 0.16
        + conflict * 0.14
        + training_value * 0.18
        + safety * 0.08,
        2,
    )

    return QualityScores(
        realism=round(realism, 2),
        difficulty=round(difficulty, 2),
        diversity=round(diversity, 2),
        consistency=round(consistency, 2),
        conflict=round(conflict, 2),
        training_value=round(training_value, 2),
        safety=round(safety, 2),
        final_score=final_score,
    )


def generate_code_review_conversation(request: CodeReviewSimulationRequest) -> ConversationRecord:
    agents = generate_personas(request.review_focus)
    issues = detect_code_issues(request.code_diff, request.language)
    messages = generate_messages(agents, issues, request.max_turns)
    scores = score_conversation(messages, issues)
    return ConversationRecord(
        conversation_id=f"conv_{uuid.uuid4().hex[:12]}",
        task_type="code_review",
        language=request.language,
        code_diff=request.code_diff,
        review_focus=request.review_focus,
        agents=agents,
        messages=messages,
        scores=scores,
        accepted=scores.final_score >= 7.0,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/")
def read_root() -> dict[str, str]:
    return {
        "name": "Multi-Agent Synthetic Data Factory",
        "status": "running",
        "version": APP_VERSION,
        "docs": "http://localhost:8001/docs",
        "health": "http://localhost:8001/health",
    }


@app.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="multi-agent-data-factory",
        version=APP_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.post("/api/simulations/code-review", response_model=ConversationRecord)
def simulate_code_review(request: CodeReviewSimulationRequest) -> ConversationRecord:
    conversation = generate_code_review_conversation(request)
    save_conversation(conversation)
    return conversation


@app.get("/api/conversations", response_model=ConversationListResponse)
def list_conversations() -> ConversationListResponse:
    items = load_conversations()
    return ConversationListResponse(items=items, total=len(items))


@app.get("/api/conversations/{conversation_id}", response_model=ConversationRecord)
def get_conversation(conversation_id: str) -> ConversationRecord:
    return find_conversation(conversation_id)


@app.get("/api/datasets/export.jsonl", response_class=PlainTextResponse)
def export_dataset_jsonl() -> str:
    rows: list[str] = []
    for conversation in load_conversations():
        if not conversation.accepted:
            continue
        rows.append(
            json.dumps(
                {
                    "conversation_id": conversation.conversation_id,
                    "task_type": conversation.task_type,
                    "messages": [
                        {"role": message.role, "content": message.content}
                        for message in conversation.messages
                    ],
                    "scores": conversation.scores.model_dump(),
                },
                ensure_ascii=False,
            )
        )
    return "\n".join(rows)
