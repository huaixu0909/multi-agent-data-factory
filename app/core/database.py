import hashlib
import json
import math
import re
import sqlite3
import uuid

from fastapi import HTTPException

from app.core.config import DATA_DIR, DATABASE_FILE
from app.core.models import (
    BatchJobRecord,
    ConversationRecord,
    DatasetVersionRecord,
    DiversityReport,
    Message,
    Persona,
    PersonaRecord,
    QualityReport,
    QualityScores,
)


DEFAULT_PERSONAS = [
    {
        "persona_id": "persona_code_dev_fastship",
        "scenario": "code_review",
        "role": "Developer",
        "name": "赶进度开发者",
        "personality": "务实、略带防御性",
        "style": "解释实现意图，倾向先保证交付，再接受证据充分的修改建议",
        "focus": "交付速度、改动范围、实现成本",
        "goal": "说明为什么这样改，并尽量让评审通过",
        "tolerance": "中",
    },
    {
        "persona_id": "persona_code_reviewer_security",
        "scenario": "code_review",
        "role": "Reviewer",
        "name": "安全审查者",
        "personality": "严格、证据导向",
        "style": "直接指出风险，并要求可执行的修复方案",
        "focus": "安全风险、测试覆盖、生产可观测性",
        "goal": "识别具体代码风险，推动补测试和安全修复",
        "tolerance": "低",
    },
    {
        "persona_id": "persona_code_challenger_arch",
        "scenario": "code_review",
        "role": "Challenger",
        "name": "架构挑战者",
        "personality": "怀疑主义、喜欢追问边界",
        "style": "反驳过于轻松的结论，提出替代方案",
        "focus": "边界条件、长期维护成本、架构取舍",
        "goal": "制造有价值的技术冲突，提升讨论深度",
        "tolerance": "低",
    },
    {
        "persona_id": "persona_code_judge_standard",
        "scenario": "code_review",
        "role": "Judge",
        "name": "标准裁判",
        "personality": "平衡、标准清晰",
        "style": "根据证据总结争议点和最终结论",
        "focus": "训练数据质量、结论可执行性、讨论一致性",
        "goal": "总结讨论并给出是否通过评审的判断",
        "tolerance": "高",
    },
    {
        "persona_id": "persona_customer_emotional",
        "scenario": "customer_complaint",
        "role": "Customer",
        "name": "高情绪投诉用户",
        "personality": "情绪化、强烈要求解释",
        "style": "表达不满，反复追问责任和补偿",
        "focus": "问题解决、时间成本、被尊重感",
        "goal": "获得明确解释、合理补偿和可执行解决方案",
        "tolerance": "低",
    },
    {
        "persona_id": "persona_support_patient",
        "scenario": "customer_complaint",
        "role": "SupportAgent",
        "name": "耐心客服专员",
        "personality": "耐心、克制、以解决问题为导向",
        "style": "先共情，再澄清事实，逐步给出方案",
        "focus": "安抚情绪、确认事实、控制承诺边界",
        "goal": "在政策范围内解决投诉并降低升级风险",
        "tolerance": "高",
    },
    {
        "persona_id": "persona_compliance_guard",
        "scenario": "customer_complaint",
        "role": "ComplianceReviewer",
        "name": "合规守门人",
        "personality": "谨慎、合规优先",
        "style": "提醒不能过度承诺，要求话术准确",
        "focus": "合规边界、赔付承诺、敏感措辞",
        "goal": "避免客服给出违反政策或不可兑现的承诺",
        "tolerance": "中",
    },
    {
        "persona_id": "persona_escalation_closer",
        "scenario": "customer_complaint",
        "role": "EscalationManager",
        "name": "闭环主管",
        "personality": "务实、重视最终闭环",
        "style": "在冲突升级时给出决策和后续动作",
        "focus": "升级处理、补偿审批、客户留存",
        "goal": "形成最终处理结论，并明确下一步负责人和时限",
        "tolerance": "中",
    },
    {
        "persona_id": "persona_interviewer_structured",
        "scenario": "technical_interview",
        "role": "Interviewer",
        "name": "结构化面试官",
        "personality": "结构化、目标明确",
        "style": "先问核心概念，再要求候选人结合项目经验说明",
        "focus": "技术原理、工程落地、岗位匹配度",
        "goal": "判断候选人是否具备目标岗位所需的技术理解",
        "tolerance": "中",
    },
    {
        "persona_id": "persona_candidate_realistic",
        "scenario": "technical_interview",
        "role": "Candidate",
        "name": "真实候选人",
        "personality": "认真、略有紧张",
        "style": "先给出自己的理解，再用项目经历补充说明",
        "focus": "展示经验、解释取舍、暴露真实认知边界",
        "goal": "尽量完整回答问题，并体现可成长性",
        "tolerance": "中",
    },
    {
        "persona_id": "persona_followup_deepdive",
        "scenario": "technical_interview",
        "role": "FollowupInterviewer",
        "name": "深挖追问官",
        "personality": "犀利、喜欢追问细节",
        "style": "抓住模糊回答继续追问边界条件和失败场景",
        "focus": "深度追问、反例、生产问题排查",
        "goal": "识别候选人是否只是会背概念，还是理解底层机制",
        "tolerance": "低",
    },
    {
        "persona_id": "persona_evaluator_standard",
        "scenario": "technical_interview",
        "role": "Evaluator",
        "name": "标准评估官",
        "personality": "客观、标准化",
        "style": "基于回答质量给出分项评价和改进建议",
        "focus": "能力评分、知识缺口、训练价值",
        "goal": "总结候选人的优势、短板和是否进入下一轮",
        "tolerance": "高",
    },
]


def ensure_data_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    initialize_database()


def open_database() -> sqlite3.Connection:
    connection = sqlite3.connect(DATABASE_FILE, timeout=30)
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
                generation_mode TEXT NOT NULL DEFAULT 'mock',
                llm_provider TEXT,
                llm_model TEXT,
                llm_error TEXT,
                scoring_mode TEXT NOT NULL DEFAULT 'heuristic',
                scoring_provider TEXT,
                scoring_model TEXT,
                scoring_error TEXT,
                score_feedback TEXT NOT NULL DEFAULT '[]',
                quality_report TEXT NOT NULL DEFAULT '{}',
                content_hash TEXT,
                duplicate_of TEXT,
                similarity_score REAL NOT NULL DEFAULT 0,
                diversity_report TEXT NOT NULL DEFAULT '{}',
                workflow_engine TEXT NOT NULL DEFAULT 'legacy',
                workflow_steps TEXT NOT NULL DEFAULT '[]',
                agent_trace TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS personas (
                persona_id TEXT PRIMARY KEY,
                scenario TEXT NOT NULL,
                role TEXT NOT NULL,
                name TEXT NOT NULL,
                personality TEXT NOT NULL,
                style TEXT NOT NULL,
                focus TEXT NOT NULL,
                goal TEXT NOT NULL,
                tolerance TEXT NOT NULL,
                usage_count INTEGER NOT NULL DEFAULT 0,
                average_score REAL NOT NULL DEFAULT 0,
                success_count INTEGER NOT NULL DEFAULT 0,
                weight REAL NOT NULL DEFAULT 1,
                memory_notes TEXT NOT NULL DEFAULT '[]',
                success_patterns TEXT NOT NULL DEFAULT '[]',
                failure_patterns TEXT NOT NULL DEFAULT '[]',
                strategy_notes TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS batch_jobs (
                job_id TEXT PRIMARY KEY,
                scenario TEXT NOT NULL,
                status TEXT NOT NULL,
                total INTEGER NOT NULL,
                completed INTEGER NOT NULL DEFAULT 0,
                accepted INTEGER NOT NULL DEFAULT 0,
                failed INTEGER NOT NULL DEFAULT 0,
                min_score REAL NOT NULL DEFAULT 0,
                payload TEXT NOT NULL DEFAULT '{}',
                conversation_ids TEXT NOT NULL DEFAULT '[]',
                error TEXT,
                created_at TEXT NOT NULL,
                started_at TEXT,
                finished_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_versions (
                version_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT,
                filters TEXT NOT NULL DEFAULT '{}',
                conversation_ids TEXT NOT NULL DEFAULT '[]',
                total INTEGER NOT NULL DEFAULT 0,
                accepted INTEGER NOT NULL DEFAULT 0,
                average_score REAL NOT NULL DEFAULT 0,
                duplicate_count INTEGER NOT NULL DEFAULT 0,
                duplicate_rate REAL NOT NULL DEFAULT 0,
                diversity_score REAL NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        _ensure_column(connection, "conversations", "scenario", "TEXT NOT NULL DEFAULT 'code_review'")
        _ensure_column(connection, "conversations", "task_input", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(connection, "conversations", "language", "TEXT")
        _ensure_column(connection, "conversations", "code_diff", "TEXT")
        _ensure_column(connection, "conversations", "review_focus", "TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(connection, "conversations", "generation_mode", "TEXT NOT NULL DEFAULT 'mock'")
        _ensure_column(connection, "conversations", "llm_provider", "TEXT")
        _ensure_column(connection, "conversations", "llm_model", "TEXT")
        _ensure_column(connection, "conversations", "llm_error", "TEXT")
        _ensure_column(connection, "conversations", "scoring_mode", "TEXT NOT NULL DEFAULT 'heuristic'")
        _ensure_column(connection, "conversations", "scoring_provider", "TEXT")
        _ensure_column(connection, "conversations", "scoring_model", "TEXT")
        _ensure_column(connection, "conversations", "scoring_error", "TEXT")
        _ensure_column(connection, "conversations", "score_feedback", "TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(connection, "conversations", "quality_report", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(connection, "conversations", "content_hash", "TEXT")
        _ensure_column(connection, "conversations", "duplicate_of", "TEXT")
        _ensure_column(connection, "conversations", "similarity_score", "REAL NOT NULL DEFAULT 0")
        _ensure_column(connection, "conversations", "diversity_report", "TEXT NOT NULL DEFAULT '{}'")
        _ensure_column(connection, "conversations", "workflow_engine", "TEXT NOT NULL DEFAULT 'legacy'")
        _ensure_column(connection, "conversations", "workflow_steps", "TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(connection, "conversations", "agent_trace", "TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(connection, "dataset_versions", "duplicate_count", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(connection, "dataset_versions", "duplicate_rate", "REAL NOT NULL DEFAULT 0")
        _ensure_column(connection, "dataset_versions", "diversity_score", "REAL NOT NULL DEFAULT 1")
        _ensure_column(connection, "personas", "success_patterns", "TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(connection, "personas", "failure_patterns", "TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(connection, "personas", "strategy_notes", "TEXT NOT NULL DEFAULT '[]'")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_scenario ON conversations(scenario)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_content_hash ON conversations(content_hash)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_personas_scenario_role ON personas(scenario, role)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_batch_jobs_created_at ON batch_jobs(created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_batch_jobs_status ON batch_jobs(status)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_dataset_versions_created_at ON dataset_versions(created_at DESC)"
        )
        seed_default_personas(connection)
        connection.commit()


def _ensure_column(connection: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    existing = {
        str(row["name"])
        for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in existing:
        connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def seed_default_personas(connection: sqlite3.Connection) -> None:
    now = _utc_now()
    for item in DEFAULT_PERSONAS:
        connection.execute(
            """
            INSERT OR IGNORE INTO personas (
                persona_id, scenario, role, name, personality, style, focus, goal,
                tolerance, usage_count, average_score, success_count, weight,
                memory_notes, success_patterns, failure_patterns, strategy_notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 1, ?, ?, ?, ?, ?, ?)
            """,
            (
                item["persona_id"],
                item["scenario"],
                item["role"],
                item["name"],
                item["personality"],
                item["style"],
                item["focus"],
                item["goal"],
                item["tolerance"],
                json.dumps(["默认 Persona，等待真实对话积累表现记忆。"], ensure_ascii=False),
                json.dumps([], ensure_ascii=False),
                json.dumps([], ensure_ascii=False),
                json.dumps([], ensure_ascii=False),
                now,
                now,
            ),
        )


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _json_list(value: object) -> list[str]:
    if value is None:
        return []
    try:
        parsed = json.loads(str(value or "[]"))
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


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
        conversation.generation_mode,
        conversation.llm_provider,
        conversation.llm_model,
        conversation.llm_error,
        conversation.scoring_mode,
        conversation.scoring_provider,
        conversation.scoring_model,
        conversation.scoring_error,
        json.dumps(conversation.score_feedback, ensure_ascii=False),
        json.dumps(conversation.quality_report.model_dump(), ensure_ascii=False),
        conversation.content_hash,
        conversation.duplicate_of,
        conversation.similarity_score,
        json.dumps(conversation.diversity_report.model_dump(), ensure_ascii=False),
        conversation.workflow_engine,
        json.dumps(conversation.workflow_steps, ensure_ascii=False),
        json.dumps(conversation.agent_trace, ensure_ascii=False),
        conversation.created_at,
    )


def row_to_conversation(row: sqlite3.Row) -> ConversationRecord:
    task_input_raw = row["task_input"] if "task_input" in row.keys() else "{}"
    scenario = row["scenario"] if "scenario" in row.keys() else row["task_type"]
    language = row["language"] if "language" in row.keys() else None
    code_diff = row["code_diff"] if "code_diff" in row.keys() else None
    review_focus_raw = row["review_focus"] if "review_focus" in row.keys() else "[]"
    generation_mode = row["generation_mode"] if "generation_mode" in row.keys() else "mock"
    llm_provider = row["llm_provider"] if "llm_provider" in row.keys() else None
    llm_model = row["llm_model"] if "llm_model" in row.keys() else None
    llm_error = row["llm_error"] if "llm_error" in row.keys() else None
    scoring_mode = row["scoring_mode"] if "scoring_mode" in row.keys() else "heuristic"
    scoring_provider = row["scoring_provider"] if "scoring_provider" in row.keys() else None
    scoring_model = row["scoring_model"] if "scoring_model" in row.keys() else None
    scoring_error = row["scoring_error"] if "scoring_error" in row.keys() else None
    score_feedback_raw = row["score_feedback"] if "score_feedback" in row.keys() else "[]"
    quality_report_raw = row["quality_report"] if "quality_report" in row.keys() else "{}"
    content_hash = row["content_hash"] if "content_hash" in row.keys() else None
    duplicate_of = row["duplicate_of"] if "duplicate_of" in row.keys() else None
    similarity_score = row["similarity_score"] if "similarity_score" in row.keys() else 0
    diversity_report_raw = row["diversity_report"] if "diversity_report" in row.keys() else "{}"
    workflow_engine = row["workflow_engine"] if "workflow_engine" in row.keys() else "legacy"
    workflow_steps_raw = row["workflow_steps"] if "workflow_steps" in row.keys() else "[]"
    agent_trace_raw = row["agent_trace"] if "agent_trace" in row.keys() else "[]"

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
        generation_mode=str(generation_mode or "mock"),
        llm_provider=str(llm_provider) if llm_provider is not None else None,
        llm_model=str(llm_model) if llm_model is not None else None,
        llm_error=str(llm_error) if llm_error is not None else None,
        scoring_mode=str(scoring_mode or "heuristic"),
        scoring_provider=str(scoring_provider) if scoring_provider is not None else None,
        scoring_model=str(scoring_model) if scoring_model is not None else None,
        scoring_error=str(scoring_error) if scoring_error is not None else None,
        score_feedback=json.loads(str(score_feedback_raw or "[]")),
        quality_report=QualityReport(**json.loads(str(quality_report_raw or "{}"))),
        content_hash=str(content_hash) if content_hash is not None else None,
        duplicate_of=str(duplicate_of) if duplicate_of is not None else None,
        similarity_score=float(similarity_score or 0),
        diversity_report=DiversityReport(**json.loads(str(diversity_report_raw or "{}"))),
        workflow_engine=str(workflow_engine or "legacy"),
        workflow_steps=json.loads(str(workflow_steps_raw or "[]")),
        agent_trace=json.loads(str(agent_trace_raw or "[]")),
        created_at=str(row["created_at"]),
    )


def row_to_persona(row: sqlite3.Row) -> PersonaRecord:
    return PersonaRecord(
        persona_id=str(row["persona_id"]),
        scenario=str(row["scenario"]),
        role=str(row["role"]),
        name=str(row["name"]),
        personality=str(row["personality"]),
        style=str(row["style"]),
        focus=str(row["focus"]),
        goal=str(row["goal"]),
        tolerance=str(row["tolerance"]),
        usage_count=int(row["usage_count"]),
        average_score=round(float(row["average_score"]), 2),
        success_count=int(row["success_count"]),
        weight=round(float(row["weight"]), 3),
        memory_notes=_json_list(row["memory_notes"]),
        success_patterns=_json_list(row["success_patterns"]),
        failure_patterns=_json_list(row["failure_patterns"]),
        strategy_notes=_json_list(row["strategy_notes"]),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
    )


def persona_record_to_agent(persona: PersonaRecord) -> Persona:
    return Persona(
        persona_id=persona.persona_id,
        agent_id=persona.persona_id,
        role=persona.role,
        name=persona.name,
        personality=persona.personality,
        style=persona.style,
        focus=persona.focus,
        goal=persona.goal,
        tolerance=persona.tolerance,
        memory_notes=persona.memory_notes,
        success_patterns=persona.success_patterns,
        failure_patterns=persona.failure_patterns,
        strategy_notes=persona.strategy_notes,
    )


def list_personas(scenario: str | None = None) -> list[PersonaRecord]:
    ensure_data_dirs()
    with open_database() as connection:
        if scenario:
            rows = connection.execute(
                """
                SELECT persona_id, scenario, role, name, personality, style, focus, goal,
                       tolerance, usage_count, average_score, success_count, weight,
                       memory_notes, success_patterns, failure_patterns, strategy_notes, created_at, updated_at
                FROM personas
                WHERE scenario = ?
                ORDER BY scenario, role, weight DESC, average_score DESC, usage_count DESC
                """,
                (scenario,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT persona_id, scenario, role, name, personality, style, focus, goal,
                       tolerance, usage_count, average_score, success_count, weight,
                       memory_notes, success_patterns, failure_patterns, strategy_notes, created_at, updated_at
                FROM personas
                ORDER BY scenario, role, weight DESC, average_score DESC, usage_count DESC
                """
            ).fetchall()
    return [row_to_persona(row) for row in rows]


def select_personas_for_scenario(
    scenario: str,
    roles: list[str],
    fallback_personas: list[Persona],
) -> list[Persona]:
    personas = list_personas(scenario=scenario)
    selected: list[Persona] = []
    fallback_by_role = {persona.role: persona for persona in fallback_personas}
    for role in roles:
        candidates = [persona for persona in personas if persona.role == role]
        if candidates:
            selected.append(persona_record_to_agent(candidates[0]))
        elif role in fallback_by_role:
            selected.append(fallback_by_role[role])
    return selected or fallback_personas


def update_persona_memory(conversation: ConversationRecord) -> None:
    ensure_data_dirs()
    final_score = conversation.scores.final_score
    success_delta = 1 if conversation.accepted else 0
    note = _build_persona_memory_note(conversation)
    now = _utc_now()
    persona_ids = [agent.persona_id for agent in conversation.agents if agent.persona_id]
    persona_roles = {agent.persona_id: agent.role for agent in conversation.agents if agent.persona_id}
    if not persona_ids:
        return

    with open_database() as connection:
        for persona_id in persona_ids:
            row = connection.execute(
                """
                SELECT usage_count, average_score, success_count, weight,
                       memory_notes, success_patterns, failure_patterns, strategy_notes
                FROM personas
                WHERE persona_id = ?
                """,
                (persona_id,),
            ).fetchone()
            if row is None:
                continue
            usage_count = int(row["usage_count"])
            average_score = float(row["average_score"])
            success_count = int(row["success_count"])
            weight = float(row["weight"])
            new_usage_count = usage_count + 1
            new_average = ((average_score * usage_count) + final_score) / new_usage_count
            new_success_count = success_count + success_delta
            next_weight = weight + (0.08 if conversation.accepted else -0.05)
            next_weight = max(0.3, min(2.5, next_weight))
            role = persona_roles.get(persona_id, "")
            memory_payload = _build_persona_memory_payload(conversation, role)
            memory_notes = _json_list(row["memory_notes"])
            memory_notes = ([note] + memory_notes)[:8]
            success_patterns = _json_list(row["success_patterns"])
            failure_patterns = _json_list(row["failure_patterns"])
            strategy_notes = _json_list(row["strategy_notes"])
            if conversation.accepted:
                success_patterns = ([memory_payload["pattern"]] + success_patterns)[:6]
            else:
                failure_patterns = ([memory_payload["pattern"]] + failure_patterns)[:6]
            strategy_notes = ([memory_payload["strategy"]] + strategy_notes)[:6]
            connection.execute(
                """
                UPDATE personas
                SET usage_count = ?,
                    average_score = ?,
                    success_count = ?,
                    weight = ?,
                    memory_notes = ?,
                    success_patterns = ?,
                    failure_patterns = ?,
                    strategy_notes = ?,
                    updated_at = ?
                WHERE persona_id = ?
                """,
                (
                    new_usage_count,
                    round(new_average, 4),
                    new_success_count,
                    round(next_weight, 4),
                    json.dumps(memory_notes, ensure_ascii=False),
                    json.dumps(success_patterns, ensure_ascii=False),
                    json.dumps(failure_patterns, ensure_ascii=False),
                    json.dumps(strategy_notes, ensure_ascii=False),
                    now,
                    persona_id,
                ),
            )
        connection.commit()


def _build_persona_memory_note(conversation: ConversationRecord) -> str:
    scenario_label = {
        "code_review": "代码审查",
        "customer_complaint": "客服投诉",
        "technical_interview": "技术面试",
    }.get(conversation.scenario, conversation.scenario)
    status = "高质量样本" if conversation.accepted else "待改进样本"
    feedback = "；".join(conversation.score_feedback[:2]) if conversation.score_feedback else "暂无 LLM 评语"
    return f"{scenario_label} / {status} / 分数 {conversation.scores.final_score:.2f}：{feedback}"


def _build_persona_memory_payload(conversation: ConversationRecord, role: str) -> dict[str, str]:
    role_messages = [message.content for message in conversation.messages if message.role == role]
    last_role_message = role_messages[-1] if role_messages else "本轮没有直接发言，需要关注路由是否合理。"
    feedback = conversation.score_feedback[0] if conversation.score_feedback else "暂无评分反馈"
    route_roles = ", ".join(
        sorted({str(item.get("role", "")).strip() for item in conversation.agent_trace if item.get("role")})
    )
    if not route_roles:
        route_roles = "当前场景"

    score_text = f"{conversation.scores.final_score:.2f}"
    pattern_prefix = "高质量经验" if conversation.accepted else "低分风险"
    strategy_prefix = "下次优先保持" if conversation.accepted else "下次优先修正"
    compact_message = _compact_text(last_role_message, 88)
    compact_feedback = _compact_text(feedback, 88)

    return {
        "pattern": f"{pattern_prefix}：{role or 'Agent'} 在 {conversation.scenario} 中参与 {route_roles} 路径；样本分 {score_text}；代表发言：{compact_message}",
        "strategy": f"{strategy_prefix}：结合评分反馈调整表达。反馈：{compact_feedback}",
    }


def _compact_text(value: str, max_length: int) -> str:
    normalized = " ".join(str(value).split())
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[:max_length]}..."


def enrich_conversation_diversity(conversation: ConversationRecord) -> ConversationRecord:
    corpus = _conversation_diversity_corpus(conversation)
    content_hash = _stable_content_hash(corpus)
    candidate_shingles = _text_shingles(corpus)

    duplicate_level = "unique"
    duplicate_of: str | None = None
    best_similarity = 0.0
    signals = [f"content_hash:{content_hash}"]

    with open_database() as connection:
        rows = connection.execute(
            """
            SELECT conversation_id, content_hash, messages, task_input
            FROM conversations
            WHERE scenario = ? AND conversation_id != ?
            ORDER BY created_at DESC
            LIMIT 500
            """,
            (conversation.scenario, conversation.conversation_id),
        ).fetchall()

    for row in rows:
        row_hash = str(row["content_hash"] or "")
        row_id = str(row["conversation_id"])
        if row_hash and row_hash == content_hash:
            duplicate_level = "exact_duplicate"
            duplicate_of = row_id
            best_similarity = 1.0
            signals.append("exact content hash match")
            break

        existing_corpus = _stored_conversation_corpus(row)
        similarity = _jaccard_similarity(candidate_shingles, _text_shingles(existing_corpus))
        if similarity > best_similarity:
            best_similarity = similarity
            duplicate_of = row_id if similarity >= 0.82 else None

    if duplicate_level != "exact_duplicate":
        if best_similarity >= 0.88:
            duplicate_level = "near_duplicate"
            signals.append("high shingle overlap")
        else:
            duplicate_level = "unique"
            duplicate_of = None
            signals.append("no strong overlap in recent same-scenario corpus")

    recommendation = {
        "exact_duplicate": "Exact duplicate detected. Exclude it from high-quality dataset exports or regenerate with a different task/persona seed.",
        "near_duplicate": "Near duplicate detected. Keep only if it adds a new conflict angle, otherwise regenerate with stronger persona or task variation.",
        "unique": "Unique enough for the current local corpus.",
    }[duplicate_level]

    similarity_score = round(best_similarity, 4)
    report = DiversityReport(
        content_hash=content_hash,
        duplicate_level=duplicate_level,
        duplicate_of=duplicate_of,
        similarity_score=similarity_score,
        uniqueness_score=round(1 - similarity_score, 4),
        recommendation=recommendation,
        signals=signals,
    )
    conversation.content_hash = content_hash
    conversation.duplicate_of = duplicate_of
    conversation.similarity_score = similarity_score
    conversation.diversity_report = report
    return conversation


def _conversation_diversity_corpus(conversation: ConversationRecord) -> str:
    parts = [
        conversation.scenario,
        json.dumps(conversation.task_input, ensure_ascii=False, sort_keys=True),
        conversation.code_diff or "",
        " ".join(conversation.review_focus),
    ]
    parts.extend(f"{message.role}: {message.content}" for message in conversation.messages)
    return "\n".join(parts)


def _stored_conversation_corpus(row: sqlite3.Row) -> str:
    try:
        messages = json.loads(str(row["messages"] or "[]"))
    except json.JSONDecodeError:
        messages = []
    try:
        task_input = json.loads(str(row["task_input"] or "{}"))
    except json.JSONDecodeError:
        task_input = {}
    parts = [json.dumps(task_input, ensure_ascii=False, sort_keys=True)]
    parts.extend(
        f"{str(item.get('role', ''))}: {str(item.get('content', ''))}"
        for item in messages
        if isinstance(item, dict)
    )
    return "\n".join(parts)


def _stable_content_hash(text: str) -> str:
    normalized = _normalize_for_similarity(text)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _normalize_for_similarity(text: str) -> str:
    lowered = str(text or "").lower()
    compact = re.sub(r"\s+", " ", lowered)
    return compact.strip()


def _text_shingles(text: str, size: int = 5) -> set[str]:
    normalized = _normalize_for_similarity(text)
    if not normalized:
        return set()
    tokens = re.findall(r"\w+", normalized)
    token_text = " ".join(tokens) if len(tokens) >= 8 else normalized
    if len(token_text) <= size:
        return {token_text}
    return {token_text[index : index + size] for index in range(len(token_text) - size + 1)}


def _jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _calculate_diversity_stats(conversations: list[ConversationRecord]) -> tuple[int, float, float]:
    total = len(conversations)
    if not total:
        return 0, 0.0, 1.0
    duplicate_count = sum(
        1
        for conversation in conversations
        if conversation.duplicate_of
        or conversation.similarity_score >= 0.88
        or conversation.diversity_report.duplicate_level in {"exact_duplicate", "near_duplicate"}
    )
    duplicate_rate = duplicate_count / total
    return duplicate_count, round(duplicate_rate, 4), round(1 - duplicate_rate, 4)


def save_conversation(conversation: ConversationRecord) -> None:
    ensure_data_dirs()
    conversation = enrich_conversation_diversity(conversation)
    with open_database() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO conversations (
                conversation_id, task_type, scenario, task_input, language, code_diff,
                review_focus, agents, messages, scores, accepted,
                generation_mode, llm_provider, llm_model, llm_error,
                scoring_mode, scoring_provider, scoring_model, scoring_error, score_feedback,
                quality_report, content_hash, duplicate_of, similarity_score, diversity_report,
                workflow_engine, workflow_steps, agent_trace,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                       review_focus, agents, messages, scores, accepted,
                       generation_mode, llm_provider, llm_model, llm_error,
                       scoring_mode, scoring_provider, scoring_model, scoring_error, score_feedback,
                       quality_report, content_hash, duplicate_of, similarity_score, diversity_report,
                       workflow_engine, workflow_steps, agent_trace,
                       created_at
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
                       review_focus, agents, messages, scores, accepted,
                       generation_mode, llm_provider, llm_model, llm_error,
                       scoring_mode, scoring_provider, scoring_model, scoring_error, score_feedback,
                       quality_report, content_hash, duplicate_of, similarity_score, diversity_report,
                       workflow_engine, workflow_steps, agent_trace,
                       created_at
                FROM conversations
                ORDER BY created_at DESC
                """
            ).fetchall()
    return [row_to_conversation(row) for row in rows]


def query_conversations(
    *,
    scenario: str | None = None,
    accepted: bool | None = None,
    min_score: float | None = None,
    max_score: float | None = None,
    q: str | None = None,
    page: int = 1,
    page_size: int = 10,
) -> tuple[list[ConversationRecord], int, int]:
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    keyword = (q or "").strip().lower()
    conversations = load_conversations(scenario=scenario)

    filtered: list[ConversationRecord] = []
    for conversation in conversations:
        if accepted is not None and conversation.accepted != accepted:
            continue
        final_score = conversation.scores.final_score
        if min_score is not None and final_score < min_score:
            continue
        if max_score is not None and final_score > max_score:
            continue
        if keyword and keyword not in _conversation_search_text(conversation):
            continue
        filtered.append(conversation)

    total = len(filtered)
    total_pages = max(1, math.ceil(total / page_size))
    start = (page - 1) * page_size
    return filtered[start : start + page_size], total, total_pages


def query_all_conversations(
    *,
    scenario: str | None = None,
    accepted: bool | None = None,
    min_score: float | None = None,
    max_score: float | None = None,
    q: str | None = None,
) -> list[ConversationRecord]:
    page = 1
    items: list[ConversationRecord] = []
    while True:
        conversations, _, total_pages = query_conversations(
            scenario=scenario,
            accepted=accepted,
            min_score=min_score,
            max_score=max_score,
            q=q,
            page=page,
            page_size=100,
        )
        items.extend(conversations)
        if page >= total_pages:
            break
        page += 1
    return items


def _conversation_search_text(conversation: ConversationRecord) -> str:
    parts = [
        conversation.conversation_id,
        conversation.task_type,
        conversation.scenario,
        conversation.language or "",
        conversation.code_diff or "",
        json.dumps(conversation.task_input, ensure_ascii=False),
        " ".join(conversation.review_focus),
        " ".join(agent.role for agent in conversation.agents),
        " ".join(agent.focus for agent in conversation.agents),
        " ".join(message.content for message in conversation.messages),
        " ".join(conversation.score_feedback),
    ]
    return "\n".join(parts).lower()


def find_conversation(conversation_id: str) -> ConversationRecord:
    ensure_data_dirs()
    with open_database() as connection:
        row = connection.execute(
            """
            SELECT conversation_id, task_type, scenario, task_input, language, code_diff,
                   review_focus, agents, messages, scores, accepted,
                   generation_mode, llm_provider, llm_model, llm_error,
                   scoring_mode, scoring_provider, scoring_model, scoring_error, score_feedback,
                   quality_report, content_hash, duplicate_of, similarity_score, diversity_report,
                   workflow_engine, workflow_steps, agent_trace,
                   created_at
            FROM conversations
            WHERE conversation_id = ?
            """,
            (conversation_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return row_to_conversation(row)


def find_conversation_silent(conversation_id: str) -> ConversationRecord | None:
    try:
        return find_conversation(conversation_id)
    except HTTPException:
        return None


def delete_conversation(conversation_id: str) -> None:
    ensure_data_dirs()
    with open_database() as connection:
        row = connection.execute(
            "SELECT conversation_id FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        connection.execute(
            "DELETE FROM conversations WHERE conversation_id = ?",
            (conversation_id,),
        )

        job_rows = connection.execute(
            """
            SELECT job_id, conversation_ids
            FROM batch_jobs
            WHERE conversation_ids LIKE ?
            """,
            (f"%{conversation_id}%",),
        ).fetchall()
        for job_row in job_rows:
            conversation_ids = [
                item for item in _json_list(job_row["conversation_ids"]) if item != conversation_id
            ]
            connection.execute(
                "UPDATE batch_jobs SET conversation_ids = ? WHERE job_id = ?",
                (json.dumps(conversation_ids, ensure_ascii=False), job_row["job_id"]),
            )

        version_rows = connection.execute(
            """
            SELECT version_id, conversation_ids
            FROM dataset_versions
            WHERE conversation_ids LIKE ?
            """,
            (f"%{conversation_id}%",),
        ).fetchall()
        for version_row in version_rows:
            conversation_ids = [
                item for item in _json_list(version_row["conversation_ids"]) if item != conversation_id
            ]
            conversations = [find_conversation_silent(item) for item in conversation_ids]
            conversations = [item for item in conversations if item is not None]
            total = len(conversations)
            accepted_count = sum(1 for item in conversations if item.accepted)
            average_score = (
                sum(item.scores.final_score for item in conversations) / total if total else 0
            )
            duplicate_count, duplicate_rate, diversity_score = _calculate_diversity_stats(conversations)
            connection.execute(
                """
                UPDATE dataset_versions
                SET conversation_ids = ?, total = ?, accepted = ?, average_score = ?,
                    duplicate_count = ?, duplicate_rate = ?, diversity_score = ?
                WHERE version_id = ?
                """,
                (
                    json.dumps([item.conversation_id for item in conversations], ensure_ascii=False),
                    total,
                    accepted_count,
                    round(average_score, 4),
                    duplicate_count,
                    duplicate_rate,
                    diversity_score,
                    version_row["version_id"],
                ),
            )

        connection.commit()


def save_batch_job(job: BatchJobRecord) -> None:
    ensure_data_dirs()
    with open_database() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO batch_jobs (
                job_id, scenario, status, total, completed, accepted, failed,
                min_score, payload, conversation_ids, error,
                created_at, started_at, finished_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.job_id,
                job.scenario,
                job.status,
                job.total,
                job.completed,
                job.accepted,
                job.failed,
                job.min_score,
                json.dumps(job.payload, ensure_ascii=False),
                json.dumps(job.conversation_ids, ensure_ascii=False),
                job.error,
                job.created_at,
                job.started_at,
                job.finished_at,
            ),
        )
        connection.commit()


def update_batch_job(job_id: str, **updates: object) -> BatchJobRecord:
    ensure_data_dirs()
    if not updates:
        return find_batch_job(job_id)

    allowed = {
        "status",
        "completed",
        "accepted",
        "failed",
        "conversation_ids",
        "error",
        "started_at",
        "finished_at",
    }
    assignments: list[str] = []
    values: list[object] = []
    for key, value in updates.items():
        if key not in allowed:
            continue
        assignments.append(f"{key} = ?")
        if key == "conversation_ids":
            values.append(json.dumps(value or [], ensure_ascii=False))
        else:
            values.append(value)

    if not assignments:
        return find_batch_job(job_id)

    values.append(job_id)
    with open_database() as connection:
        connection.execute(
            f"UPDATE batch_jobs SET {', '.join(assignments)} WHERE job_id = ?",
            values,
        )
        connection.commit()
    return find_batch_job(job_id)


def list_batch_jobs(limit: int = 20) -> list[BatchJobRecord]:
    ensure_data_dirs()
    limit = max(1, min(limit, 100))
    with open_database() as connection:
        rows = connection.execute(
            """
            SELECT job_id, scenario, status, total, completed, accepted, failed,
                   min_score, payload, conversation_ids, error,
                   created_at, started_at, finished_at
            FROM batch_jobs
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [row_to_batch_job(row) for row in rows]


def find_batch_job(job_id: str) -> BatchJobRecord:
    ensure_data_dirs()
    with open_database() as connection:
        row = connection.execute(
            """
            SELECT job_id, scenario, status, total, completed, accepted, failed,
                   min_score, payload, conversation_ids, error,
                   created_at, started_at, finished_at
            FROM batch_jobs
            WHERE job_id = ?
            """,
            (job_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Batch job not found")
    return row_to_batch_job(row)


def row_to_batch_job(row: sqlite3.Row) -> BatchJobRecord:
    return BatchJobRecord(
        job_id=str(row["job_id"]),
        scenario=str(row["scenario"]),
        status=str(row["status"]),
        total=int(row["total"]),
        completed=int(row["completed"]),
        accepted=int(row["accepted"]),
        failed=int(row["failed"]),
        min_score=float(row["min_score"]),
        payload=json.loads(str(row["payload"] or "{}")),
        conversation_ids=_json_list(row["conversation_ids"]),
        error=str(row["error"]) if row["error"] is not None else None,
        created_at=str(row["created_at"]),
        started_at=str(row["started_at"]) if row["started_at"] is not None else None,
        finished_at=str(row["finished_at"]) if row["finished_at"] is not None else None,
    )


def create_dataset_version(
    *,
    name: str,
    description: str | None,
    filters: dict,
    conversations: list[ConversationRecord],
) -> DatasetVersionRecord:
    ensure_data_dirs()
    version_id = f"ds_{uuid.uuid4().hex[:12]}"
    conversation_ids = [conversation.conversation_id for conversation in conversations]
    total = len(conversations)
    accepted_count = sum(1 for conversation in conversations if conversation.accepted)
    average_score = (
        sum(conversation.scores.final_score for conversation in conversations) / total if total else 0
    )
    duplicate_count, duplicate_rate, diversity_score = _calculate_diversity_stats(conversations)
    record = DatasetVersionRecord(
        version_id=version_id,
        name=name,
        description=description,
        filters=filters,
        conversation_ids=conversation_ids,
        total=total,
        accepted=accepted_count,
        average_score=round(average_score, 4),
        duplicate_count=duplicate_count,
        duplicate_rate=duplicate_rate,
        diversity_score=diversity_score,
        created_at=_utc_now(),
    )

    with open_database() as connection:
        connection.execute(
            """
            INSERT INTO dataset_versions (
                version_id, name, description, filters, conversation_ids,
                total, accepted, average_score, duplicate_count, duplicate_rate,
                diversity_score, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.version_id,
                record.name,
                record.description,
                json.dumps(record.filters, ensure_ascii=False),
                json.dumps(record.conversation_ids, ensure_ascii=False),
                record.total,
                record.accepted,
                record.average_score,
                record.duplicate_count,
                record.duplicate_rate,
                record.diversity_score,
                record.created_at,
            ),
        )
        connection.commit()
    return record


def list_dataset_versions(limit: int = 20) -> list[DatasetVersionRecord]:
    ensure_data_dirs()
    limit = max(1, min(limit, 100))
    with open_database() as connection:
        rows = connection.execute(
            """
            SELECT version_id, name, description, filters, conversation_ids,
                   total, accepted, average_score, duplicate_count, duplicate_rate,
                   diversity_score, created_at
            FROM dataset_versions
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [row_to_dataset_version(row) for row in rows]


def find_dataset_version(version_id: str) -> DatasetVersionRecord:
    ensure_data_dirs()
    with open_database() as connection:
        row = connection.execute(
            """
            SELECT version_id, name, description, filters, conversation_ids,
                   total, accepted, average_score, duplicate_count, duplicate_rate,
                   diversity_score, created_at
            FROM dataset_versions
            WHERE version_id = ?
            """,
            (version_id,),
        ).fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail="Dataset version not found")
    return row_to_dataset_version(row)


def load_dataset_version_conversations(version_id: str) -> list[ConversationRecord]:
    version = find_dataset_version(version_id)
    conversations: list[ConversationRecord] = []
    for conversation_id in version.conversation_ids:
        conversation = find_conversation_silent(conversation_id)
        if conversation is not None:
            conversations.append(conversation)
    return conversations


def delete_dataset_version(version_id: str) -> None:
    ensure_data_dirs()
    with open_database() as connection:
        row = connection.execute(
            "SELECT version_id FROM dataset_versions WHERE version_id = ?",
            (version_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Dataset version not found")
        connection.execute("DELETE FROM dataset_versions WHERE version_id = ?", (version_id,))
        connection.commit()


def row_to_dataset_version(row: sqlite3.Row) -> DatasetVersionRecord:
    return DatasetVersionRecord(
        version_id=str(row["version_id"]),
        name=str(row["name"]),
        description=str(row["description"]) if row["description"] is not None else None,
        filters=json.loads(str(row["filters"] or "{}")),
        conversation_ids=_json_list(row["conversation_ids"]),
        total=int(row["total"]),
        accepted=int(row["accepted"]),
        average_score=round(float(row["average_score"]), 4),
        duplicate_count=int(row["duplicate_count"]) if "duplicate_count" in row.keys() else 0,
        duplicate_rate=round(float(row["duplicate_rate"]), 4) if "duplicate_rate" in row.keys() else 0,
        diversity_score=round(float(row["diversity_score"]), 4) if "diversity_score" in row.keys() else 1,
        created_at=str(row["created_at"]),
    )
