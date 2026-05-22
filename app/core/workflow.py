from dataclasses import dataclass
from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from app.core.agents import AgentRunner
from app.core.models import Message, Persona, QualityScores
from app.core.scoring import QualityScoringResult, score_conversation_quality


class SimulationWorkflowState(TypedDict, total=False):
    scenario: str
    scenario_instructions: str
    task_input: dict[str, Any]
    agents: list[Persona]
    issue_hints: list[dict[str, Any]]
    max_turns: int
    turn_roles: list[str]
    mock_messages: list[Message]
    messages: list[Message]
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
    turn_roles = [message.role for message in mock_messages[:max_turns]]

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

    def make_agent_turn_node(turn_index: int, role: str):
        def agent_turn_node(state: SimulationWorkflowState) -> SimulationWorkflowState:
            node_name = _agent_node_name(turn_index, role)
            messages = list(state.get("messages", []))
            agent = _find_agent(state["agents"], role)
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
                    turn_number=turn_index + 1,
                    max_turns=state["max_turns"],
                )
                content = result.content
                provider = result.provider
                model = result.model
                llm_success_count = state.get("llm_success_count", 0) + 1
                mock_success_count = state.get("mock_success_count", 0)
            except Exception as error:
                fallback = state["mock_messages"][turn_index]
                content = fallback.content
                trace_mode = "mock"
                error_text = str(error)[:500]
                llm_success_count = state.get("llm_success_count", 0)
                mock_success_count = state.get("mock_success_count", 0) + 1

            message = Message(
                turn=len(messages) + 1,
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
                        "error": error_text,
                    },
                ],
            }

        return agent_turn_node

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
    graph.add_node("quality_score", quality_score_node)
    graph.add_edge(START, "select_personas")
    graph.add_edge("select_personas", "detect_signals")

    previous = "detect_signals"
    for turn_index, role in enumerate(turn_roles):
        node_name = _agent_node_name(turn_index, role)
        graph.add_node(node_name, make_agent_turn_node(turn_index, role))
        graph.add_edge(previous, node_name)
        previous = node_name

    graph.add_edge(previous, "quality_score")
    graph.add_edge("quality_score", END)

    initial_state: SimulationWorkflowState = {
        "scenario": scenario,
        "scenario_instructions": scenario_instructions,
        "task_input": task_input,
        "agents": agents,
        "issue_hints": issue_hints,
        "max_turns": max_turns,
        "turn_roles": turn_roles,
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
        generation_mode=final_state.get("generation_mode", "langgraph_agent_mock"),
        llm_provider=final_state.get("llm_provider"),
        llm_model=final_state.get("llm_model"),
        llm_error=final_state.get("llm_error"),
        scoring_mode=scoring_result.mode,
        scoring_provider=scoring_result.provider,
        scoring_model=scoring_result.model,
        scoring_error=scoring_result.error,
        score_feedback=scoring_result.feedback or [],
        workflow_engine="langgraph_agent_nodes",
        workflow_steps=final_state.get("workflow_steps", []),
        agent_trace=final_state.get("agent_trace", []),
    )


def _find_agent(agents: list[Persona], role: str) -> Persona:
    for agent in agents:
        if agent.role == role:
            return agent
    raise RuntimeError(f"No agent found for role: {role}")


def _agent_node_name(turn_index: int, role: str) -> str:
    safe_role = "".join(char.lower() if char.isalnum() else "_" for char in role).strip("_")
    return f"agent_turn_{turn_index + 1:02d}_{safe_role}"


def _resolve_generation_mode(state: SimulationWorkflowState) -> str:
    llm_count = state.get("llm_success_count", 0)
    mock_count = state.get("mock_success_count", 0)
    if llm_count > 0 and mock_count == 0:
        return "langgraph_agent_llm"
    if llm_count > 0 and mock_count > 0:
        return "langgraph_agent_mixed"
    return "langgraph_agent_mock"
