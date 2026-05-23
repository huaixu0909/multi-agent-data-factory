import json
from dataclasses import dataclass
from typing import Any

from app.core.llm import DeepSeekClient, build_deepseek_client
from app.core.models import Message, Persona


@dataclass
class AgentTurnResult:
    content: str
    provider: str
    model: str


class AgentRunner:
    """Runs one independent Agent for exactly one conversation turn."""

    def __init__(self) -> None:
        self.client: DeepSeekClient = build_deepseek_client()

    def run_turn(
        self,
        *,
        scenario: str,
        scenario_instructions: str,
        task_input: dict[str, Any],
        issue_hints: list[dict[str, Any]],
        agent: Persona,
        messages: list[Message],
        turn_number: int,
        max_turns: int,
    ) -> AgentTurnResult:
        parsed = self.client.chat_object(
            self._build_system_prompt(agent),
            self._build_user_prompt(
                scenario=scenario,
                scenario_instructions=scenario_instructions,
                task_input=task_input,
                issue_hints=issue_hints,
                agent=agent,
                messages=messages,
                turn_number=turn_number,
                max_turns=max_turns,
            ),
            temperature=0.65,
        )
        content = str(parsed.get("content", "")).strip()
        if not content:
            raise RuntimeError("Agent response missing content")
        return AgentTurnResult(
            content=content,
            provider=self.client.provider,
            model=self.client.model,
        )

    def _build_system_prompt(self, agent: Persona) -> str:
        return f"""
你是一个独立运行的多 Agent 节点。
你只能扮演当前 Agent：{agent.role}。
你不能替其他角色发言，不能生成多轮对话，不能输出 Markdown。
你必须只输出 JSON 对象，格式为：{{"content":"你这一轮的中文发言"}}。
发言要符合你的 Persona、目标和容忍度，并且要承接已有对话历史。
""".strip()

    def _format_agent_memory(self, agent: Persona) -> str:
        sections = [
            ("最近样本记忆", agent.memory_notes[:3]),
            ("成功经验", agent.success_patterns[:3]),
            ("失败教训", agent.failure_patterns[:3]),
            ("策略建议", agent.strategy_notes[:3]),
        ]
        lines: list[str] = []
        for title, items in sections:
            if not items:
                lines.append(f"- {title}: 暂无")
                continue
            lines.append(f"- {title}:")
            for item in items:
                lines.append(f"  - {item}")
        return "\n".join(lines)

    def _build_user_prompt(
        self,
        *,
        scenario: str,
        scenario_instructions: str,
        task_input: dict[str, Any],
        issue_hints: list[dict[str, Any]],
        agent: Persona,
        messages: list[Message],
        turn_number: int,
        max_turns: int,
    ) -> str:
        history = "\n".join(
            f"{message.turn}. {message.role}: {message.content}" for message in messages
        )
        if not history:
            history = "当前还没有历史发言，你是本轮第一个发言的 Agent。"

        return f"""
场景：{scenario}
场景规则：
{scenario_instructions}

当前 Agent Persona：
- role: {agent.role}
- name: {agent.name or agent.role}
- personality: {agent.personality}
- style: {agent.style}
- focus: {agent.focus}
- goal: {agent.goal}
- tolerance: {agent.tolerance}

Agent 长期记忆（必须参考，但不要逐字复述）：
{self._format_agent_memory(agent)}

任务输入：
{json.dumps(task_input, ensure_ascii=False, indent=2)}

场景线索：
{json.dumps(issue_hints, ensure_ascii=False, indent=2)}

已有对话历史：
{history}

现在是第 {turn_number} / {max_turns} 轮。
请只生成 {agent.role} 这一轮的一条中文发言。
""".strip()
 
