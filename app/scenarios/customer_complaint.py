import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.core.database import select_personas_for_scenario
from app.core.llm import LLMGenerationResult, build_deepseek_client
from app.core.models import ConversationRecord, Message, Persona
from app.core.scenario import Scenario
from app.core.workflow import run_langgraph_simulation


EmotionLevel = Literal["low", "medium", "high", "extreme"]


class CustomerComplaintSimulationRequest(BaseModel):
    industry: str = Field(default="电商", max_length=80)
    complaint_type: str = Field(default="退款纠纷", max_length=120)
    customer_profile: str = Field(default="老用户，最近一次订单体验很差", max_length=500)
    complaint_detail: str = Field(..., min_length=1, max_length=8000)
    company_policy: str = Field(
        default="支持在符合规则时退款；涉及高额赔付时需要升级主管审核；客服必须避免承诺超出政策范围的补偿。",
        max_length=1200,
    )
    emotion_level: EmotionLevel = "high"
    max_turns: int = Field(default=8, ge=6, le=12)


class ComplaintSignal(BaseModel):
    issue_type: str
    severity: Literal["low", "medium", "high"]
    evidence: str
    suggestion: str


class CustomerComplaintScenario(Scenario[CustomerComplaintSimulationRequest]):
    name = "customer_complaint"
    title = "客服投诉对话数据合成"
    description = "模拟用户投诉、情绪升级、客服安抚、合规审核和升级处理。"
    status = "v0.5 / Customer Support"
    endpoint = "/api/simulations/customer-complaint"
    agent_roles = ["Customer", "SupportAgent", "ComplianceReviewer", "EscalationManager"]

    def simulate(self, request: CustomerComplaintSimulationRequest) -> ConversationRecord:
        agents = self.generate_personas(request)
        signals = self.detect_complaint_signals(request)
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
            "这是客服投诉数据合成场景。每个 Agent 节点只能生成自己这一轮的一条中文发言。"
            "Customer 表达真实诉求与情绪变化；SupportAgent 先共情再澄清事实；"
            "ComplianceReviewer 约束政策边界；EscalationManager 给出升级路径和闭环动作。"
        )

    def generate_personas(self, request: CustomerComplaintSimulationRequest) -> list[Persona]:
        return select_personas_for_scenario(
            self.name,
            self.agent_roles,
            [
            Persona(
                agent_id="agent_customer",
                role="Customer",
                personality="情绪化、强烈要求解释",
                style="表达不满，反复追问责任和补偿",
                focus=f"{request.complaint_type}、时间成本、被尊重感",
                goal="获得明确解释、合理补偿和可执行解决方案",
                tolerance=self.emotion_to_tolerance(request.emotion_level),
            ),
            Persona(
                agent_id="agent_support",
                role="SupportAgent",
                personality="耐心、克制、以解决问题为导向",
                style="先共情，再澄清事实，逐步给出方案",
                focus="安抚情绪、确认事实、控制承诺边界",
                goal="在政策范围内解决投诉并降低升级风险",
                tolerance="高",
            ),
            Persona(
                agent_id="agent_compliance",
                role="ComplianceReviewer",
                personality="谨慎、合规优先",
                style="提醒不能过度承诺，要求话术准确",
                focus="合规边界、赔付承诺、敏感措辞",
                goal="避免客服给出违反政策或不可兑现的承诺",
                tolerance="中",
            ),
            Persona(
                agent_id="agent_escalation",
                role="EscalationManager",
                personality="务实、重视最终闭环",
                style="在冲突升级时给出决策和后续动作",
                focus="升级处理、补偿审批、客户留存",
                goal="形成最终处理结论，并明确下一步负责人和时限",
                tolerance="中",
            ),
            ],
        )

    def detect_complaint_signals(
        self,
        request: CustomerComplaintSimulationRequest,
    ) -> list[ComplaintSignal]:
        detail = request.complaint_detail
        signals: list[ComplaintSignal] = [
            ComplaintSignal(
                issue_type="emotion",
                severity="high" if request.emotion_level in ["high", "extreme"] else "medium",
                evidence=request.emotion_level,
                suggestion="客服需要先共情和确认诉求，再进入解释与方案阶段。",
            ),
            ComplaintSignal(
                issue_type="policy_boundary",
                severity="medium",
                evidence=request.company_policy[:220],
                suggestion="所有补偿和承诺都必须落在企业政策范围内，超出范围需要升级。",
            ),
        ]

        if any(token in detail for token in ["退款", "赔偿", "补偿", "退钱"]):
            signals.append(
                ComplaintSignal(
                    issue_type="compensation",
                    severity="high",
                    evidence=next((line.strip() for line in detail.splitlines() if line.strip()), detail[:220]),
                    suggestion="需要明确补偿条件、审批边界和处理时限。",
                )
            )
        if any(token in detail for token in ["投诉", "曝光", "差评", "监管", "12315"]):
            signals.append(
                ComplaintSignal(
                    issue_type="escalation_risk",
                    severity="high",
                    evidence=detail[:220],
                    suggestion="需要升级处理，并保持沟通记录完整。",
                )
            )
        if any(token in detail for token in ["隐私", "手机号", "地址", "身份证"]):
            signals.append(
                ComplaintSignal(
                    issue_type="privacy",
                    severity="high",
                    evidence=detail[:220],
                    suggestion="不得复述或泄露敏感个人信息，应使用脱敏表达。",
                )
            )

        return signals[:5]

    def generate_llm_messages(
        self,
        request: CustomerComplaintSimulationRequest,
        agents: list[Persona],
        signals: list[ComplaintSignal],
    ) -> LLMGenerationResult:
        client = build_deepseek_client()
        system_prompt = (
            "你是一名资深 AI 数据合成工程师，负责生成中文客服投诉多 Agent 训练数据。"
            "你必须只输出 JSON 对象，不要输出 Markdown，不要输出解释。"
            "对话要自然、克制、有真实情绪变化和合规边界，不能泛泛而谈。"
        )
        user_prompt = self.build_llm_prompt(request, agents, signals)
        return client.chat_json(system_prompt, user_prompt)

    def build_llm_prompt(
        self,
        request: CustomerComplaintSimulationRequest,
        agents: list[Persona],
        signals: list[ComplaintSignal],
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
请基于下面信息生成一段中文客服投诉多 Agent 对话数据。

硬性要求：
1. 输出 JSON，格式必须是：{{"messages":[{{"role":"Customer","content":"..."}}]}}。
2. role 只能使用 Customer、SupportAgent、ComplianceReviewer、EscalationManager。
3. messages 数量必须是 {request.max_turns} 条。
4. content 必须是中文，语气要像真实客服沟通。
5. Customer 要体现情绪变化和真实诉求，但不能包含人身攻击。
6. SupportAgent 必须先共情，再澄清事实，最后提出下一步。
7. ComplianceReviewer 必须提醒政策边界或风险话术。
8. EscalationManager 必须给出可执行结论、时限或升级路径。
9. 不要承诺超出企业政策的赔偿，不要编造系统里没有的信息。

行业：{request.industry}
投诉类型：{request.complaint_type}
客户画像：{request.customer_profile}
情绪强度：{request.emotion_level}
企业政策：{request.company_policy}

Agent Persona：
{personas}

问题线索：
{signal_text}

投诉详情：
{request.complaint_detail}
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
            raise RuntimeError("LLM response did not contain enough valid customer complaint messages")

        return normalized

    def generate_messages(
        self,
        request: CustomerComplaintSimulationRequest,
        agents: list[Persona],
        signals: list[ComplaintSignal],
    ) -> list[Message]:
        customer, support, compliance, escalation = agents
        primary = signals[0]
        secondary = signals[1] if len(signals) > 1 else signals[0]
        messages = [
            self.build_message(
                1,
                customer,
                f"我这次真的很不满意。{request.complaint_detail[:120]}。我现在就想知道你们怎么处理。",
            ),
            self.build_message(
                2,
                support,
                f"非常抱歉让您有这样的体验。我先确认一下：您的核心诉求是围绕「{request.complaint_type}」，希望得到明确解释和处理方案，对吗？",
            ),
            self.build_message(
                3,
                customer,
                "是的，但我不想再听模板话术。如果今天没有明确结果，我会继续投诉。",
            ),
            self.build_message(
                4,
                compliance,
                f"这里需要注意合规边界：{secondary.suggestion} 客服可以说明处理路径，但不能直接承诺超出政策的赔偿。",
            ),
            self.build_message(
                5,
                support,
                f"我理解您的着急。根据当前政策，我可以先为您登记升级，并在核实后给出处理结果。当前需要重点核实：{primary.suggestion}",
            ),
            self.build_message(
                6,
                customer,
                "可以升级，但我需要一个具体时间，不要让我一直等。",
            ),
            self.build_message(
                7,
                escalation,
                "我来接手升级。我们会在 24 小时内完成核实，并通过站内消息或电话同步结果；如符合政策，会同步提交退款或补偿审批。",
            ),
            self.build_message(
                8,
                support,
                "我会把本次沟通记录、您的诉求和升级时限一起备注。今天先给您升级编号，后续按这个编号追踪处理进度。",
            ),
        ]

        if request.max_turns >= 10:
            messages.insert(
                7,
                self.build_message(
                    8,
                    compliance,
                    "补充提醒：后续沟通不要展示完整手机号、地址等敏感信息，内部记录也应使用脱敏方式。",
                ),
            )
            messages.insert(
                8,
                self.build_message(
                    9,
                    customer,
                    "可以，但你们这次必须按承诺时间反馈。我已经等过太久了。",
                ),
            )

        return [
            Message(turn=index + 1, agent_id=item.agent_id, role=item.role, content=item.content)
            for index, item in enumerate(messages[: request.max_turns])
        ]

    def build_message(self, turn: int, agent: Persona, content: str) -> Message:
        return Message(turn=turn, agent_id=agent.agent_id, role=agent.role, content=content)

    def emotion_to_tolerance(self, emotion_level: EmotionLevel) -> str:
        return {
            "low": "高",
            "medium": "中",
            "high": "低",
            "extreme": "极低",
        }[emotion_level]


customer_complaint_scenario = CustomerComplaintScenario()
