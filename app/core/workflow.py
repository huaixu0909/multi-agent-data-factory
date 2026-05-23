from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.agents import AgentRunner
from app.core.models import Message, Persona, QualityScores
from app.core.scoring import QualityScoringResult, score_conversation_quality


END_ROUTE = "__quality_score__"


class SimulationWorkflowState(TypedDict, total=False):
    scenario: str
    scenario_instructions: str
    task_input: dict[str, Any]
    agents: list[Persona]
    issue_hints: list[dict[str, Any]]
    max_turns: int
    mock_messages: list[Message]
    messages: list[Message]
    next_role: str
    route_reason: str
    generation_mode: str
    llm_provider: str | None
    llm_model: str | None
    llm_error: str | None
    llm_success_count: int
    mock_success_count: int
    scoring_result: QualityScoringResult
    workflow_steps: list[str]
    agent_trace: list[dict[str, Any]]


@dataclass
class SimulationWorkflowResult:
    messages: list[Message]
    scores: QualityScores
    accepted: bool
    generation_mode: str
    llm_provider: str | None
    llm_model: str | None
    llm_error: str | None
    scoring_mode: str
    scoring_provider: str | None
    scoring_model: str | None
    scoring_error: str | None
    score_feedback: list[str]
    workflow_engine: str
    workflow_steps: list[str]
    agent_trace: list[dict[str, Any]]


def run_langgraph_simulation(
    *,
    scenario: str,
    scenario_instructions: str,
    task_input: dict[str, Any],
    agents: list[Persona],
    issue_hints: list[dict[str, Any]],
    max_turns: int,
    mock_messages: list[Message],
) -> SimulationWorkflowResult:
    agent_runner = AgentRunner()
    graph = StateGraph(SimulationWorkflowState)
    role_to_node = {agent.role: _role_node_name(agent.role) for agent in agents}

    def select_personas_node(state: SimulationWorkflowState) -> SimulationWorkflowState:
        return {
            **state,
            "workflow_steps": [*state.get("workflow_steps", []), "select_personas"],
        }

    def detect_signals_node(state: SimulationWorkflowState) -> SimulationWorkflowState:
        return {
            **state,
            "workflow_steps": [*state.get("workflow_steps", []), "detect_signals"],
        }

    def router_node(state: SimulationWorkflowState) -> SimulationWorkflowState:
        next_role, reason = _decide_next_role(state)
        step = "route_to_quality_score" if next_role == END_ROUTE else f"route_to_{_safe_name(next_role)}"
        return {
            **state,
            "next_role": next_role,
            "route_reason": reason,
            "workflow_steps": [*state.get("workflow_steps", []), step],
        }

    def router_edge(state: SimulationWorkflowState) -> str:
        next_role = state.get("next_role", END_ROUTE)
        if next_role == END_ROUTE:
            return "quality_score"
        return role_to_node.get(next_role, "quality_score")

    def make_agent_node(role: str):
        def agent_node(state: SimulationWorkflowState) -> SimulationWorkflowState:
            messages = list(state.get("messages", []))
            agent = _find_agent(state["agents"], role)
            turn_number = len(messages) + 1
            node_name = _agent_step_name(turn_number, role)
            trace_mode = "llm"
            error_text: str | None = None
            provider = state.get("llm_provider")
            model = state.get("llm_model")

            try:
                result = agent_runner.run_turn(
                    scenario=state["scenario"],
                    scenario_instructions=state["scenario_instructions"],
                    task_input=state["task_input"],
                    issue_hints=state["issue_hints"],
                    agent=agent,
                    messages=messages,
                    turn_number=turn_number,
                    max_turns=state["max_turns"],
                )
                content = result.content
                provider = result.provider
                model = result.model
                llm_success_count = state.get("llm_success_count", 0) + 1
                mock_success_count = state.get("mock_success_count", 0)
            except Exception as error:
                content = _fallback_content_for_role(state, role)
                trace_mode = "mock"
                error_text = str(error)[:500]
                llm_success_count = state.get("llm_success_count", 0)
                mock_success_count = state.get("mock_success_count", 0) + 1

            message = Message(
                turn=turn_number,
                agent_id=agent.agent_id,
                role=agent.role,
                content=content,
            )
            messages.append(message)

            llm_error = state.get("llm_error")
            if error_text and not llm_error:
                llm_error = error_text

            return {
                **state,
                "messages": messages,
                "llm_provider": provider,
                "llm_model": model,
                "llm_error": llm_error,
                "llm_success_count": llm_success_count,
                "mock_success_count": mock_success_count,
                "workflow_steps": [*state.get("workflow_steps", []), node_name],
                "agent_trace": [
                    *state.get("agent_trace", []),
                    {
                        "node": node_name,
                        "turn": message.turn,
                        "role": agent.role,
                        "agent_id": agent.agent_id,
                        "persona_id": agent.persona_id,
                        "mode": trace_mode,
                        "route_reason": state.get("route_reason", ""),
                        "memory_context_count": _memory_count(agent),
                        "error": error_text,
                    },
                ],
            }

        return agent_node

    def quality_score_node(state: SimulationWorkflowState) -> SimulationWorkflowState:
        scoring_result = score_conversation_quality(
            scenario=state["scenario"],
            task_input=state["task_input"],
            agents=state["agents"],
            messages=state["messages"],
            issue_hints=state["issue_hints"],
        )
        return {
            **state,
            "scoring_result": scoring_result,
            "generation_mode": _resolve_generation_mode(state),
            "workflow_steps": [*state.get("workflow_steps", []), "quality_score"],
        }

    graph.add_node("select_personas", select_personas_node)
    graph.add_node("detect_signals", detect_signals_node)
    graph.add_node("router", router_node)
    graph.add_node("quality_score", quality_score_node)

    for role, node_name in role_to_node.items():
        graph.add_node(node_name, make_agent_node(role))
        graph.add_edge(node_name, "router")

    graph.add_edge(START, "select_personas")
    graph.add_edge("select_personas", "detect_signals")
    graph.add_edge("detect_signals", "router")
    graph.add_conditional_edges(
        "router",
        router_edge,
        {**{node_name: node_name for node_name in role_to_node.values()}, "quality_score": "quality_score"},
    )
    graph.add_edge("quality_score", END)

    initial_state: SimulationWorkflowState = {
        "scenario": scenario,
        "scenario_instructions": scenario_instructions,
        "task_input": task_input,
        "agents": agents,
        "issue_hints": issue_hints,
        "max_turns": max_turns,
        "mock_messages": mock_messages[:max_turns],
        "messages": [],
        "workflow_steps": [],
        "agent_trace": [],
        "llm_success_count": 0,
        "mock_success_count": 0,
    }
    final_state = graph.compile().invoke(initial_state)
    scoring_result = final_state["scoring_result"]
    scores = scoring_result.scores

    return SimulationWorkflowResult(
        messages=final_state["messages"],
        scores=scores,
        accepted=scores.final_score >= 7.0,
        generation_mode=final_state.get("generation_mode", "langgraph_routed_mock"),
        llm_provider=final_state.get("llm_provider"),
        llm_model=final_state.get("llm_model"),
        llm_error=final_state.get("llm_error"),
        scoring_mode=scoring_result.mode,
        scoring_provider=scoring_result.provider,
        scoring_model=scoring_result.model,
        scoring_error=scoring_result.error,
        score_feedback=scoring_result.feedback or [],
        workflow_engine="langgraph_memory_agents",
        workflow_steps=final_state.get("workflow_steps", []),
        agent_trace=final_state.get("agent_trace", []),
    )


def _decide_next_role(state: SimulationWorkflowState) -> tuple[str, str]:
    messages = state.get("messages", [])
    max_turns = state["max_turns"]
    roles = [agent.role for agent in state["agents"]]
    scenario = state["scenario"]

    if len(messages) >= max_turns:
        return END_ROUTE, "已达到最大轮数，进入质量评分。"

    if not messages:
        return _first_available_role(scenario, roles), "对话开始，选择场景起始 Agent。"

    last_role = messages[-1].role
    if scenario == "code_review":
        return _route_code_review(messages, roles, state["issue_hints"], max_turns, last_role)
    if scenario == "customer_complaint":
        return _route_customer_complaint(messages, roles, state["issue_hints"], max_turns, last_role)
    if scenario == "technical_interview":
        return _route_technical_interview(messages, roles, state["issue_hints"], max_turns, last_role)

    return _fallback_route(messages, roles, max_turns)


def _route_code_review(
    messages: list[Message],
    roles: list[str],
    issue_hints: list[dict[str, Any]],
    max_turns: int,
    last_role: str,
) -> tuple[str, str]:
    high_risk = _has_high_risk(issue_hints)
    reviewer_count = _role_count(messages, "Reviewer")
    developer_count = _role_count(messages, "Developer")
    challenger_count = _role_count(messages, "Challenger")

    if last_role == "Judge" and len(messages) >= 4:
        return END_ROUTE, "裁判已经给出结论，对话满足结束条件。"
    if last_role == "Developer" and reviewer_count == 0:
        return _ensure_role("Reviewer", roles), "开发者完成初始说明，进入代码审查。"
    if last_role == "Reviewer" and high_risk and challenger_count == 0 and len(messages) + 1 < max_turns:
        return _ensure_role("Challenger", roles), "检测到高危线索，引入挑战者制造技术反驳。"
    if last_role == "Reviewer" and developer_count < 2 and len(messages) + 1 < max_turns:
        return _ensure_role("Developer", roles), "审查者提出问题，开发者需要回应或承诺修复。"
    if last_role == "Challenger" and len(messages) + 1 < max_turns:
        return _ensure_role("Developer", roles), "挑战者提出反驳，开发者需要回应取舍。"
    if last_role == "Developer" and reviewer_count < 2 and len(messages) + 1 < max_turns:
        return _ensure_role("Reviewer", roles), "开发者回应后，审查者继续确认修复边界。"
    return _ensure_role("Judge", roles), "争议与修复信息已经足够，交给裁判总结。"


def _route_customer_complaint(
    messages: list[Message],
    roles: list[str],
    issue_hints: list[dict[str, Any]],
    max_turns: int,
    last_role: str,
) -> tuple[str, str]:
    compliance_needed = _has_issue_type(issue_hints, {"compensation", "privacy", "policy_boundary"})
    escalation_needed = _has_issue_type(issue_hints, {"escalation_risk", "compensation"}) or _has_high_risk(issue_hints)
    compliance_count = _role_count(messages, "ComplianceReviewer")
    escalation_count = _role_count(messages, "EscalationManager")
    customer_count = _role_count(messages, "Customer")

    if last_role == "SupportAgent" and len(messages) >= 4 and (compliance_count or not compliance_needed):
        return END_ROUTE, "客服已经给出处理方案，当前投诉链路可以收束。"
    if last_role == "Customer":
        return _ensure_role("SupportAgent", roles), "客户表达诉求后，客服需要先共情并澄清事实。"
    if last_role == "SupportAgent" and compliance_needed and compliance_count == 0 and len(messages) + 1 < max_turns:
        return _ensure_role("ComplianceReviewer", roles), "涉及赔付、隐私或政策边界，需要合规审核。"
    if last_role in {"SupportAgent", "ComplianceReviewer"} and escalation_needed and escalation_count == 0 and len(messages) + 1 < max_turns:
        return _ensure_role("EscalationManager", roles), "投诉存在升级风险，需要主管给出闭环路径。"
    if last_role == "ComplianceReviewer":
        return _ensure_role("SupportAgent", roles), "合规边界已明确，客服需要转化为用户可理解的方案。"
    if last_role == "EscalationManager" and len(messages) + 1 < max_turns:
        return _ensure_role("SupportAgent", roles), "主管给出决策后，客服需要收尾并同步给客户。"
    if customer_count < 2 and len(messages) + 1 < max_turns:
        return _ensure_role("Customer", roles), "需要客户对方案继续反馈，观察情绪变化。"
    return END_ROUTE, "投诉处理已有明确方案，进入质量评分。"


def _route_technical_interview(
    messages: list[Message],
    roles: list[str],
    issue_hints: list[dict[str, Any]],
    max_turns: int,
    last_role: str,
) -> tuple[str, str]:
    needs_followup = _has_issue_type(issue_hints, {"rag_reasoning", "agent_workflow", "profile_gap"})
    followup_count = _role_count(messages, "FollowupInterviewer")
    candidate_count = _role_count(messages, "Candidate")

    if last_role == "Evaluator" and len(messages) >= 4:
        return END_ROUTE, "评估官已经给出结论，面试样本可以结束。"
    if last_role in {"Interviewer", "FollowupInterviewer"}:
        return _ensure_role("Candidate", roles), "面试官提出问题后，候选人需要作答。"
    if last_role == "Candidate" and needs_followup and followup_count < 2 and len(messages) + 1 < max_turns:
        return _ensure_role("FollowupInterviewer", roles), "候选人回答需要继续追问边界和工程细节。"
    if last_role == "Candidate" and candidate_count < 2 and len(messages) + 2 < max_turns:
        return _ensure_role("Interviewer", roles), "需要补充一个结构化问题验证理解深度。"
    return _ensure_role("Evaluator", roles), "候选人回答信息已经足够，进入能力评估。"


def _fallback_route(messages: list[Message], roles: list[str], max_turns: int) -> tuple[str, str]:
    if len(messages) >= max_turns:
        return END_ROUTE, "达到最大轮数。"
    return roles[len(messages) % len(roles)], "未知场景，使用角色轮转兜底。"


def _fallback_content_for_role(state: SimulationWorkflowState, role: str) -> str:
    prior_role_count = _role_count(state.get("messages", []), role)
    candidates = [message for message in state["mock_messages"] if message.role == role]
    if candidates:
        index = min(prior_role_count, len(candidates) - 1)
        return candidates[index].content
    return f"{role} 根据当前上下文给出补充意见，并推动对话继续向可评估结论收束。"


def _first_available_role(scenario: str, roles: list[str]) -> str:
    preferred = {
        "code_review": "Developer",
        "customer_complaint": "Customer",
        "technical_interview": "Interviewer",
    }.get(scenario)
    if preferred in roles:
        return preferred
    return roles[0]


def _ensure_role(role: str, roles: list[str]) -> str:
    return role if role in roles else roles[0]


def _has_high_risk(issue_hints: list[dict[str, Any]]) -> bool:
    return any(str(item.get("severity", "")).lower() == "high" for item in issue_hints)


def _has_issue_type(issue_hints: list[dict[str, Any]], issue_types: set[str]) -> bool:
    return any(str(item.get("issue_type", "")).lower() in issue_types for item in issue_hints)


def _role_count(messages: list[Message], role: str) -> int:
    return sum(1 for message in messages if message.role == role)


def _find_agent(agents: list[Persona], role: str) -> Persona:
    for agent in agents:
        if agent.role == role:
            return agent
    raise RuntimeError(f"No agent found for role: {role}")


def _role_node_name(role: str) -> str:
    return f"agent_node_{_safe_name(role)}"


def _agent_step_name(turn_number: int, role: str) -> str:
    return f"agent_turn_{turn_number:02d}_{_safe_name(role)}"


def _safe_name(value: str) -> str:
    return "".join(char.lower() if char.isalnum() else "_" for char in value).strip("_")


def _resolve_generation_mode(state: SimulationWorkflowState) -> str:
    llm_count = state.get("llm_success_count", 0)
    mock_count = state.get("mock_success_count", 0)
    if llm_count > 0 and mock_count == 0:
        return "langgraph_routed_llm"
    if llm_count > 0 and mock_count > 0:
        return "langgraph_routed_mixed"
    return "langgraph_routed_mock"


def _memory_count(agent: Persona) -> int:
    return (
        len(agent.memory_notes)
        + len(agent.success_patterns)
        + len(agent.failure_patterns)
        + len(agent.strategy_notes)
    )
