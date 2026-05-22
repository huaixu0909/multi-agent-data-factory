import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.core.database import select_personas_for_scenario
from app.core.llm import LLMGenerationResult, build_deepseek_client
from app.core.models import ConversationRecord, Message, Persona, QualityScores
from app.core.scenario import Scenario
from app.core.workflow import run_langgraph_simulation


class CodeReviewSimulationRequest(BaseModel):
    language: str = Field(default="python", max_length=40)
    code_diff: str = Field(..., min_length=1, max_length=12000)
    review_focus: list[str] = Field(default_factory=lambda: ["bug", "security", "performance"])
    max_turns: int = Field(default=8, ge=6, le=12)


class CodeIssue(BaseModel):
    issue_type: str
    severity: Literal["low", "medium", "high"]
    evidence: str
    suggestion: str


class CodeReviewScenario(Scenario[CodeReviewSimulationRequest]):
    name = "code_review"
    title = "Code Review 数据合成"
    description = "模拟 Developer、Reviewer、Challenger、Judge 的中文代码审查讨论。"
    status = "v0.4 / LLM Judge"
    endpoint = "/api/simulations/code-review"
    agent_roles = ["Developer", "Reviewer", "Challenger", "Judge"]

    def simulate(self, request: CodeReviewSimulationRequest) -> ConversationRecord:
        agents = self.generate_personas(request.review_focus)
        issues = self.detect_code_issues(request.code_diff, request.language)
        task_input = request.model_dump()
        mock_messages = self.generate_messages(agents, issues, request.max_turns)
        workflow_result = run_langgraph_simulation(
            scenario=self.name,
            scenario_instructions=self.agent_node_instructions(),
            task_input=task_input,
            agents=agents,
            issue_hints=[issue.model_dump() for issue in issues],
            max_turns=request.max_turns,
            mock_messages=mock_messages,
        )
        return ConversationRecord(
            conversation_id=f"conv_{uuid.uuid4().hex[:12]}",
            task_type=self.name,
            scenario=self.name,
            language=request.language,
            code_diff=request.code_diff,
            review_focus=request.review_focus,
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
            "这是 Code Review 数据合成场景。每个 Agent 节点只能生成自己这一轮的一条中文发言。"
            "Developer 解释实现与取舍；Reviewer 必须引用 diff 或风险证据；"
            "Challenger 制造有价值的技术反驳；Judge 最后给出可执行结论。"
        )

    def generate_personas(self, review_focus: list[str]) -> list[Persona]:
        focus_text = ", ".join(review_focus) if review_focus else "code quality"
        return select_personas_for_scenario(
            self.name,
            self.agent_roles,
            [
            Persona(
                agent_id="agent_developer",
                role="Developer",
                personality="务实、略带防守",
                style="解释实现意图，但愿意接受证据充分的修改建议",
                focus="交付速度、改动范围、实现成本",
                goal="说明为什么这样改，并尽量让评审通过",
                tolerance="中",
            ),
            Persona(
                agent_id="agent_reviewer",
                role="Reviewer",
                personality="严格、证据导向",
                style="直接指出风险，并要求可执行的修复方案",
                focus=focus_text,
                goal="识别具体代码风险，推动补测试和安全修复",
                tolerance="低",
            ),
            Persona(
                agent_id="agent_challenger",
                role="Challenger",
                personality="怀疑主义、喜欢追问边界",
                style="反驳过于轻松的结论，提出替代方案",
                focus="边界条件、长期维护成本、架构取舍",
                goal="制造有价值的技术冲突，提升讨论深度",
                tolerance="低",
            ),
            Persona(
                agent_id="agent_judge",
                role="Judge",
                personality="平衡、标准清晰",
                style="根据证据总结争议点和最终结论",
                focus="训练数据质量、结论可执行性、讨论一致性",
                goal="总结讨论并给出是否通过评审的判断",
                tolerance="高",
            ),
            ],
        )

    def detect_code_issues(self, code_diff: str, language: str) -> list[CodeIssue]:
        lower = code_diff.lower()
        issues: list[CodeIssue] = []

        patterns: list[tuple[str, Literal["low", "medium", "high"], list[str], str]] = [
            (
                "security",
                "high",
                ["select ", " where ", "f\"", "format(", "%"],
                "可能存在 SQL 注入或不安全的查询拼接，建议改为参数化查询。",
            ),
            (
                "security",
                "high",
                ["eval(", "exec("],
                "动态执行代码可能演变为远程代码执行风险，应移除 eval/exec 或进行严格沙箱隔离。",
            ),
            (
                "secret",
                "high",
                ["api_key", "password", "secret", "token"],
                "疑似硬编码敏感信息，应迁移到环境变量或密钥管理服务。",
            ),
            (
                "reliability",
                "medium",
                ["except:", "except exception"],
                "宽泛异常捕获会隐藏真实故障，应捕获具体异常并记录上下文。",
            ),
            (
                "observability",
                "low",
                ["print("],
                "调试 print 不适合作为生产日志，应改为带上下文的结构化日志。",
            ),
            (
                "performance",
                "medium",
                ["for ", "query(", "select "],
                "循环内数据库调用可能造成 N+1 查询，建议批量加载或预取。",
            ),
            (
                "testing",
                "medium",
                ["def ", "class ", "return "],
                "该 diff 有功能逻辑变化，但没有看到测试更新，应补充回归测试。",
            ),
        ]

        for issue_type, severity, tokens, suggestion in patterns:
            if all(token in lower for token in tokens[:2]) or any(token in lower for token in tokens[2:]):
                evidence = next(
                    (
                        line.strip()
                        for line in code_diff.splitlines()
                        if any(token in line.lower() for token in tokens)
                    ),
                    "",
                )
                issues.append(
                    CodeIssue(
                        issue_type=issue_type,
                        severity=severity,
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
                    suggestion="建议评审重点关注命名、边界条件、测试覆盖和回滚行为。",
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

    def build_message(self, turn: int, agent: Persona, content: str) -> Message:
        return Message(turn=turn, agent_id=agent.agent_id, role=agent.role, content=content)

    def generate_llm_messages(
        self,
        request: CodeReviewSimulationRequest,
        agents: list[Persona],
        issues: list[CodeIssue],
    ) -> LLMGenerationResult:
        client = build_deepseek_client()
        system_prompt = (
            "你是一名资深 AI 数据合成工程师，负责生成中文 Code Review 多 Agent 训练数据。"
            "你必须只输出 JSON 对象，不要输出 Markdown，不要输出解释。"
            "对话要自然、具体、有真实技术冲突，不能泛泛而谈。"
        )
        user_prompt = self.build_llm_prompt(request, agents, issues)
        return client.chat_json(system_prompt, user_prompt)

    def build_llm_prompt(
        self,
        request: CodeReviewSimulationRequest,
        agents: list[Persona],
        issues: list[CodeIssue],
    ) -> str:
        personas = "\n".join(
            f"- {agent.role}: 性格={agent.personality}; 风格={agent.style}; 目标={agent.goal}; 关注={agent.focus}"
            for agent in agents
        )
        issue_hints = "\n".join(
            f"- {issue.severity} / {issue.issue_type}: 证据 `{issue.evidence}`；建议：{issue.suggestion}"
            for issue in issues
        )
        return f"""
请基于下面信息生成一段中文 Code Review 多 Agent 对话数据。

硬性要求：
1. 输出 JSON，格式必须是：{{"messages":[{{"role":"Developer","content":"..."}}]}}。
2. role 只能使用 Developer、Reviewer、Challenger、Judge。
3. messages 数量必须是 {request.max_turns} 条。
4. content 必须是中文，允许保留代码变量名、函数名、SQL 片段。
5. Reviewer 必须引用 diff 中的具体证据。
6. Challenger 必须提出反驳或替代方案，制造真实技术冲突。
7. Developer 必须有解释、让步或修复承诺。
8. Judge 必须在最后一轮给出结论：通过、请求修改，或需要补充信息。
9. 不要编造 diff 中完全不存在的业务背景。

Agent Persona：
{personas}

识别到的问题线索：
{issue_hints}

语言：{request.language}
Review Focus：{", ".join(request.review_focus)}

代码 diff：
```diff
{request.code_diff}
```
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
            raise RuntimeError("LLM response did not contain enough valid role messages")

        return normalized

    def generate_messages(
        self,
        agents: list[Persona],
        issues: list[CodeIssue],
        max_turns: int,
    ) -> list[Message]:
        developer, reviewer, challenger, judge = agents
        primary = issues[0]
        secondary = issues[1] if len(issues) > 1 else issues[0]
        messages = [
            self.build_message(
                1,
                developer,
                "我提交这个 diff 是为了尽快打通功能链路，改动范围刻意压得比较小，避免牵连其他模块。",
            ),
            self.build_message(
                2,
                reviewer,
                f"我看到一个 {primary.severity} 级别的 {primary.issue_type} 风险。证据是：`{primary.evidence}`。{primary.suggestion}",
            ),
            self.build_message(
                3,
                developer,
                "这个担心有道理，不过当前输入来自内部链路。我选择较小改动主要是因为发布时间比较紧。",
            ),
            self.build_message(
                4,
                challenger,
                "内部输入不能当作稳定的安全边界。这个路径后续一旦被复用，风险会变得很隐蔽，应该从设计上修掉，而不是依赖调用方自觉。",
            ),
            self.build_message(
                5,
                reviewer,
                f"还有一个 {secondary.issue_type} 问题：`{secondary.evidence}`。在通过评审前，至少需要补一个测试，或者换成更安全的实现。",
            ),
            self.build_message(
                6,
                developer,
                "我可以把这块改成更安全的实现，并补一个回归测试。但我希望修复范围只覆盖这个风险路径，暂时不扩大重构。",
            ),
            self.build_message(
                7,
                challenger,
                "窄范围修复可以接受，但测试必须能证明风险场景。否则这次讨论就会变成风格争论，训练价值也会下降。",
            ),
            self.build_message(
                8,
                judge,
                "结论：请求修改。当前讨论包含具体风险、diff 证据、反驳观点和可执行修复方案，适合作为 Code Review 训练数据。",
            ),
        ]

        if max_turns >= 10:
            messages.insert(
                6,
                self.build_message(
                    7,
                    reviewer,
                    "请把失败模式写进测试名称里，让后续维护者能理解为什么这里必须走更安全的实现。",
                ),
            )
            messages.insert(
                7,
                self.build_message(
                    8,
                    developer,
                    "同意。我会补充更明确的测试名称，并把实现限制在当前函数内，避免扩大影响面。",
                ),
            )

        return [
            Message(turn=index + 1, agent_id=item.agent_id, role=item.role, content=item.content)
            for index, item in enumerate(messages[:max_turns])
        ]

    def score_conversation(self, messages: list[Message], issues: list[CodeIssue]) -> QualityScores:
        role_count = len({message.role for message in messages})
        conflict_signals = sum(
            1
            for item in messages
            if any(
                token in item.content.lower()
                for token in [
                    "risk",
                    "concern",
                    "not",
                    "should",
                    "otherwise",
                    "风险",
                    "担心",
                    "不能",
                    "应该",
                    "否则",
                    "问题",
                    "反驳",
                ]
            )
        )
        evidence_count = sum(1 for item in messages if "`" in item.content or "证据" in item.content or "Evidence:" in item.content)
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


code_review_scenario = CodeReviewScenario()
