import json
import math
import sqlite3

from fastapi import HTTPException

from app.core.config import DATA_DIR, DATABASE_FILE
from app.core.models import ConversationRecord, Message, Persona, PersonaRecord, QualityScores


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
                generation_mode TEXT NOT NULL DEFAULT 'mock',
                llm_provider TEXT,
                llm_model TEXT,
                llm_error TEXT,
                scoring_mode TEXT NOT NULL DEFAULT 'heuristic',
                scoring_provider TEXT,
                scoring_model TEXT,
                scoring_error TEXT,
                score_feedback TEXT NOT NULL DEFAULT '[]',
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
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
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
        _ensure_column(connection, "conversations", "workflow_engine", "TEXT NOT NULL DEFAULT 'legacy'")
        _ensure_column(connection, "conversations", "workflow_steps", "TEXT NOT NULL DEFAULT '[]'")
        _ensure_column(connection, "conversations", "agent_trace", "TEXT NOT NULL DEFAULT '[]'")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at DESC)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_conversations_scenario ON conversations(scenario)"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_personas_scenario_role ON personas(scenario, role)"
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
                memory_notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 1, ?, ?, ?)
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
                now,
                now,
            ),
        )


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


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
        memory_notes=json.loads(str(row["memory_notes"] or "[]")),
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
    )


def list_personas(scenario: str | None = None) -> list[PersonaRecord]:
    ensure_data_dirs()
    with open_database() as connection:
        if scenario:
            rows = connection.execute(
                """
                SELECT persona_id, scenario, role, name, personality, style, focus, goal,
                       tolerance, usage_count, average_score, success_count, weight,
                       memory_notes, created_at, updated_at
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
                       memory_notes, created_at, updated_at
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
    if not persona_ids:
        return

    with open_database() as connection:
        for persona_id in persona_ids:
            row = connection.execute(
                """
                SELECT usage_count, average_score, success_count, weight, memory_notes
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
            memory_notes = json.loads(str(row["memory_notes"] or "[]"))
            memory_notes = ([note] + memory_notes)[:8]
            connection.execute(
                """
                UPDATE personas
                SET usage_count = ?,
                    average_score = ?,
                    success_count = ?,
                    weight = ?,
                    memory_notes = ?,
                    updated_at = ?
                WHERE persona_id = ?
                """,
                (
                    new_usage_count,
                    round(new_average, 4),
                    new_success_count,
                    round(next_weight, 4),
                    json.dumps(memory_notes, ensure_ascii=False),
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


def save_conversation(conversation: ConversationRecord) -> None:
    ensure_data_dirs()
    with open_database() as connection:
        connection.execute(
            """
            INSERT OR REPLACE INTO conversations (
                conversation_id, task_type, scenario, task_input, language, code_diff,
                review_focus, agents, messages, scores, accepted,
                generation_mode, llm_provider, llm_model, llm_error,
                scoring_mode, scoring_provider, scoring_model, scoring_error, score_feedback,
                workflow_engine, workflow_steps, agent_trace,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
