import json
import sqlite3

from fastapi import HTTPException

from app.core.config import DATA_DIR, DATABASE_FILE
from app.core.models import ConversationRecord, Message, Persona, QualityScores


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
                scenario TEXT NOT NULL DEFAULT 'code_review',
                task_input TEXT NOT NULL DEFAULT '{}',
                language TEXT,
                code_diff TEXT,
                review_focus TEXT NOT NULL DEFAULT '[]',
                agents TEXT NOT NULL,
                messages TEXT NOT NULL,
                scores TEXT NOT NULL,
                accepted INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        _ensure_column(connection, "conversations", "scenario", "TEXT NOT NULL DEFAULT 'code_review'")
        _ensure_column(connection, "conversations", "task_input", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(connection, "conversations", "language", "TEXT")
        _ensure_column(connection, "conversations", "code_diff", "TEXT")
        _ensure_column(connection, "conversations", "review_focus", "TEXT NOT NULL DEFAULT '[]'")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_scenario ON conversations(scenario)"
        )
        connection.commit()


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def conversation_to_row(conversation: ConversationRecord) -> tuple:
    return (
        conversation.conversation_id,
        conversation.task_type,
        conversation.scenario,
        json.dumps(conversation.task_input, ensure_ascii=False),
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
    task_input_raw = row["task_input"] if "task_input" in row.keys() else "{}"
    scenario = row["scenario"] if "scenario" in row.keys() else row["task_type"]
    language = row["language"] if "language" in row.keys() else None
    code_diff = row["code_diff"] if "code_diff" in row.keys() else None
    review_focus_raw = row["review_focus"] if "review_focus" in row.keys() else "[]"

    return ConversationRecord(
        conversation_id=str(row["conversation_id"]),
        task_type=str(row["task_type"]),
        scenario=str(scenario or row["task_type"]),
        language=str(language) if language is not None else None,
        code_diff=str(code_diff) if code_diff is not None else None,
        review_focus=json.loads(str(review_focus_raw or "[]")),
        task_input=json.loads(str(task_input_raw or "{}")),
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
                conversation_id, task_type, scenario, task_input, language, code_diff,
                review_focus, agents, messages, scores, accepted, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            conversation_to_row(conversation),
        )
        connection.commit()


def load_conversations(scenario: str | None = None) -> list[ConversationRecord]:
    ensure_data_dirs()
    with open_database() as connection:
        if scenario:
            rows = connection.execute(
                """
                SELECT conversation_id, task_type, scenario, task_input, language, code_diff,
                       review_focus, agents, messages, scores, accepted, created_at
                FROM conversations
                WHERE scenario = ?
                ORDER BY created_at DESC
                """,
                (scenario,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT conversation_id, task_type, scenario, task_input, language, code_diff,
                       review_focus, agents, messages, scores, accepted, created_at
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
            SELECT conversation_id, task_type, scenario, task_input, language, code_diff,
                   review_focus, agents, messages, scores, accepted, created_at
            FROM conversations
            WHERE conversation_id = ?
            """,
            (conversation_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return row_to_conversation(row)

