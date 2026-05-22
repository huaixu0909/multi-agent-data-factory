import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.core.database import select_personas_for_scenario
from app.core.llm import LLMGenerationResult, build_deepseek_client
from app.core.models import ConversationRecord, Message, Persona
from app.core.scenario import Scenario
from app.core.workflow import run_langgraph_simulation


InterviewDifficulty = Literal["low", "medium", "high"]


class TechnicalInterviewSimulationRequest(BaseModel):
    target_role: str = Field(default="AI 工程师", max_length=120)
    candidate_level: str = Field(default="中级", max_length=80)
    topic: str = Field(default="RAG", max_length=120)
    difficulty: InterviewDifficulty = "medium"
    candidate_profile: str = Field(
        default="候选人有 Python 和 FastAPI 项目经验，做过一个本地 RAG Demo，但缺少生产级系统经验。",
        max_length=1200,
    )
    interview_context: str = Field(
        default="希望考察候选人对技术原理、工程落地、边界条件和问题排查的理解。",
        max_length=1200,
    )
    max_turns: int = Field(default=8, ge=6, le=12)


class InterviewSignal(BaseModel):
    issue_type: str
    severity: Literal["low", "medium", "high"]
    evidence: str
    suggestion: str


class TechnicalInterviewScenario(Scenario[TechnicalInterviewSimulationRequest]):
    name = "technical_interview"
    title = "技术面试数据合成"
    description = "模拟面试官提问、候选人回答、深度追问和能力评分。"
    status = "v0.6 / Technical Interview"
    endpoint = "/api/simulations/technical-interview"
    agent_roles = ["Interviewer", "Candidate", "FollowupInterviewer", "Evaluator"]

    def simulate(self, request: TechnicalInterviewSimulationRequest) -> ConversationRecord:
        agents = self.generate_personas(request)
        signals = self.detect_interview_signals(request)
        task_input = request.model_dump()
        mock_messages = self.generate_messages(request, agents, signals)
        workflow_result = run_langgraph_simulation(
            scenario=self.name,
            scenario_instructions=self.agent_node_instructions(),
            task_input=task_input,
            agents=agents,
            issue_hints=[signal.model_dump() for signal in signals],
            max_turns=request.max_turns,
            mock_messages=mock_messages,
        )

        return ConversationRecord(
            conversation_id=f"conv_{uuid.uuid4().hex[:12]}",
            task_type=self.name,
            scenario=self.name,
            task_input=task_input,
            agents=agents,
            messages=workflow_result.messages,
            scores=workflow_result.scores,
            accepted=workflow_result.accepted,
            generation_mode=workflow_result.generation_mode,
            llm_provider=workflow_result.llm_provider,
            llm_model=workflow_result.llm_model,
            llm_error=workflow_result.llm_error,
            scoring_mode=workflow_result.scoring_mode,
            scoring_provider=workflow_result.scoring_provider,
            scoring_model=workflow_result.scoring_model,
            scoring_error=workflow_result.scoring_error,
            score_feedback=workflow_result.score_feedback,
            workflow_engine=workflow_result.workflow_engine,
            workflow_steps=workflow_result.workflow_steps,
            agent_trace=workflow_result.agent_trace,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def agent_node_instructions(self) -> str:
        return (
            "这是技术面试数据合成场景。每个 Agent 节点只能生成自己这一轮的一条中文发言。"
            "Interviewer 提出结构化问题；Candidate 结合经验回答且保留真实边界；"
            "FollowupInterviewer 追问失败场景、边界条件和工程细节；Evaluator 给出能力评估。"
        )

    def generate_personas(self, request: TechnicalInterviewSimulationRequest) -> list[Persona]:
        return select_personas_for_scenario(
            self.name,
            self.agent_roles,
            [
            Persona(
                agent_id="agent_interviewer",
                role="Interviewer",
                personality="结构化、目标明确",
                style="先问核心概念，再要求候选人结合项目经验说明",
                focus=f"{request.topic} 原理、工程落地、岗位匹配度",
                goal="判断候选人是否具备目标岗位所需的技术理解",
                tolerance="中",
            ),
            Persona(
                agent_id="agent_candidate",
                role="Candidate",
                personality="认真、略有紧张",
                style="先给出自己的理解，再用项目经历补充说明",
                focus="展示经验、解释取舍、暴露真实认知边界",
                goal="尽量完整回答问题，并体现可成长性",
                tolerance="中",
            ),
            Persona(
                agent_id="agent_followup",
                role="FollowupInterviewer",
                personality="犀利、喜欢追问细节",
                style="抓住模糊回答继续追问边界条件和失败场景",
                focus="深度追问、反例、生产问题排查",
                goal="识别候选人是否只是会背概念，还是理解底层机制",
                tolerance="低",
            ),
            Persona(
                agent_id="agent_evaluator",
                role="Evaluator",
                personality="客观、标准化",
                style="基于回答质量给出分项评价和改进建议",
                focus="能力评分、知识缺口、训练价值",
                goal="总结候选人的优势、短板和是否进入下一轮",
                tolerance="高",
            ),
            ],
        )

    def detect_interview_signals(
        self,
        request: TechnicalInterviewSimulationRequest,
    ) -> list[InterviewSignal]:
        signals = [
            InterviewSignal(
                issue_type="topic_depth",
                severity="high" if request.difficulty == "high" else "medium",
                evidence=request.topic,
                suggestion="面试对话需要覆盖概念解释、工程落地、边界条件和失败排查。",
            ),
            InterviewSignal(
                issue_type="candidate_level",
                severity="medium",
                evidence=request.candidate_level,
                suggestion="问题难度和追问深度应与候选人级别匹配。",
            ),
            InterviewSignal(
                issue_type="profile_gap",
                severity="medium",
                evidence=request.candidate_profile[:220],
                suggestion="追问应围绕候选人背景中的真实经验和缺口展开。",
            ),
        ]

        text = f"{request.topic} {request.interview_context} {request.candidate_profile}".lower()
        if any(token in text for token in ["rag", "检索", "向量", "embedding", "知识库"]):
            signals.append(
                InterviewSignal(
                    issue_type="rag_reasoning",
                    severity="high",
                    evidence=request.topic,
                    suggestion="需要追问 chunking、召回、重排、相似度阈值和幻觉控制。",
                )
            )
        if any(token in text for token in ["agent", "langgraph", "工作流", "多 agent"]):
            signals.append(
                InterviewSignal(
                    issue_type="agent_workflow",
                    severity="high",
                    evidence=request.topic,
                    suggestion="需要追问状态管理、工具调用、失败恢复和多轮记忆。",
                )
            )

        return signals[:5]

    def generate_llm_messages(
        self,
        request: TechnicalInterviewSimulationRequest,
        agents: list[Persona],
        signals: list[InterviewSignal],
    ) -> LLMGenerationResult:
        client = build_deepseek_client()
        system_prompt = (
            "你是一名资深 AI 数据合成工程师，负责生成中文技术面试多 Agent 训练数据。"
            "你必须只输出 JSON 对象，不要输出 Markdown，不要输出解释。"
            "对话要像真实技术面试，既有候选人回答，也有追问、暴露短板和评估结论。"
        )
        user_prompt = self.build_llm_prompt(request, agents, signals)
        return client.chat_json(system_prompt, user_prompt)

    def build_llm_prompt(
        self,
        request: TechnicalInterviewSimulationRequest,
        agents: list[Persona],
        signals: list[InterviewSignal],
    ) -> str:
        personas = "\n".join(
            f"- {agent.role}: 性格={agent.personality}; 风格={agent.style}; 目标={agent.goal}; 关注={agent.focus}"
            for agent in agents
        )
        signal_text = "\n".join(
            f"- {signal.severity} / {signal.issue_type}: 证据 `{signal.evidence}`；建议：{signal.suggestion}"
            for signal in signals
        )
        return f"""
请基于下面信息生成一段中文技术面试多 Agent 对话数据。

硬性要求：
1. 输出 JSON，格式必须是：{{"messages":[{{"role":"Interviewer","content":"..."}}]}}。
2. role 只能使用 Interviewer、Candidate、FollowupInterviewer、Evaluator。
3. messages 数量必须是 {request.max_turns} 条。
4. content 必须是中文，允许保留技术名词、英文缩写和代码/架构术语。
5. Interviewer 必须提出和岗位、主题相关的核心问题。
6. Candidate 必须回答具体内容，不能只说“我了解”。
7. FollowupInterviewer 必须追问边界、失败场景或工程细节。
8. Evaluator 必须在最后一轮给出能力评价、短板和下一步建议。
9. 不要把候选人写成全知全能，要保留真实认知边界。

目标岗位：{request.target_role}
候选人级别：{request.candidate_level}
主题：{request.topic}
难度：{request.difficulty}
候选人背景：{request.candidate_profile}
面试上下文：{request.interview_context}

Agent Persona：
{personas}

面试线索：
{signal_text}
""".strip()

    def normalize_llm_messages(
        self,
        raw_messages: list[dict[str, str]],
        agents: list[Persona],
        max_turns: int,
    ) -> list[Message]:
        agents_by_role = {agent.role: agent for agent in agents}
        normalized: list[Message] = []
        for item in raw_messages:
            role = item.get("role", "").strip()
            content = item.get("content", "").strip()
            agent = agents_by_role.get(role)
            if agent is None or not content:
                continue
            normalized.append(self.build_message(len(normalized) + 1, agent, content))
            if len(normalized) >= max_turns:
                break

        if len(normalized) < max_turns:
            raise RuntimeError("LLM response did not contain enough valid technical interview messages")

        return normalized

    def generate_messages(
        self,
        request: TechnicalInterviewSimulationRequest,
        agents: list[Persona],
        signals: list[InterviewSignal],
    ) -> list[Message]:
        interviewer, candidate, followup, evaluator = agents
        primary = signals[0]
        messages = [
            self.build_message(
                1,
                interviewer,
                f"我们今天主要围绕 {request.topic} 来聊。请你先用自己的话说明，它在 {request.target_role} 工作中解决什么问题？",
            ),
            self.build_message(
                2,
                candidate,
                f"我的理解是，{request.topic} 主要用于把模型能力和业务知识或工具流程结合起来。我在项目里做过相关 Demo，但生产级经验还不算深。",
            ),
            self.build_message(
                3,
                followup,
                f"你刚才说得比较概括。请具体说明一个失败场景，比如召回不准、上下文过长或结果不稳定时，你会怎么排查？",
            ),
            self.build_message(
                4,
                candidate,
                "我会先看输入数据和中间结果，比如检索结果是否相关、参数是否合理，再看 prompt 是否限制了回答范围。如果是线上问题，还需要记录请求链路和日志。",
            ),
            self.build_message(
                5,
                interviewer,
                f"结合你的背景：{request.candidate_profile[:120]}。如果让你把 Demo 升级到团队可用，你会优先补哪些能力？",
            ),
            self.build_message(
                6,
                candidate,
                "我会先补数据持久化、接口错误处理、评估指标和基本监控。然后再考虑更复杂的工作流，比如异步任务和多轮状态管理。",
            ),
            self.build_message(
                7,
                followup,
                f"这里我继续追问：{primary.suggestion} 你能说出一个具体指标或验收标准吗？",
            ),
            self.build_message(
                8,
                evaluator,
                f"评价：候选人对 {request.topic} 有实践经验，能说出基本排查路径，但在生产级指标、系统边界和失败恢复上还需要更具体。建议进入下一轮时重点考察工程化深度。",
            ),
        ]

        if request.max_turns >= 10:
            messages.insert(
                7,
                self.build_message(
                    8,
                    candidate,
                    "可以，比如检索场景我会看命中率、回答引用准确率、无资料时拒答率，以及端到端响应时间。",
                ),
            )
            messages.insert(
                8,
                self.build_message(
                    9,
                    interviewer,
                    "这个回答更具体了。那如果指标之间冲突，比如准确率提升但延迟变高，你会如何取舍？",
                ),
            )

        return [
            Message(turn=index + 1, agent_id=item.agent_id, role=item.role, content=item.content)
            for index, item in enumerate(messages[: request.max_turns])
        ]

    def build_message(self, turn: int, agent: Persona, content: str) -> Message:
        return Message(turn=turn, agent_id=agent.agent_id, role=agent.role, content=content)


technical_interview_scenario = TechnicalInterviewScenario()
