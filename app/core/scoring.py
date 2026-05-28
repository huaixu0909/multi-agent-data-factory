import json
import logging
from dataclasses import dataclass
from typing import Any

from app.core.llm import build_deepseek_client
from app.core.models import Message, Persona, QualityReport, QualityScores

logger = logging.getLogger(__name__)


@dataclass
class QualityScoringResult:
    scores: QualityScores
    mode: str
    provider: str | None = None
    model: str | None = None
    error: str | None = None
    feedback: list[str] | None = None
    report: QualityReport | None = None


def score_conversation_quality(
    *,
    scenario: str,
    task_input: dict[str, Any],
    agents: list[Persona],
    messages: list[Message],
    issue_hints: list[dict[str, Any]],
) -> QualityScoringResult:
    heuristic_scores = heuristic_score_conversation(messages, issue_hints)
    heuristic_report = build_quality_report(
        scores=heuristic_scores,
        scenario=scenario,
        messages=messages,
        issue_hints=issue_hints,
        feedback=[],
        llm_judge_available=False,
    )
    try:
        return llm_score_conversation(
            scenario=scenario,
            task_input=task_input,
            agents=agents,
            messages=messages,
            issue_hints=issue_hints,
            heuristic_scores=heuristic_scores,
        )
    except Exception as error:
        logger.warning("LLM judge failed; using heuristic scoring", exc_info=True)
        return QualityScoringResult(
            scores=heuristic_scores,
            mode="heuristic_multi_judge",
            error=str(error)[:500],
            feedback=[
                "使用规则评分器完成评估。",
                "LLM-as-a-Judge 未启用或调用失败，已自动回退。",
            ],
            report=heuristic_report,
        )


def heuristic_score_conversation(
    messages: list[Message],
    issue_hints: list[dict[str, Any]],
) -> QualityScores:
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
                "替代",
            ]
        )
    )
    evidence_count = sum(
        1
        for item in messages
        if "`" in item.content or "证据" in item.content or "Evidence:" in item.content
    )
    high_severity = sum(1 for issue in issue_hints if issue.get("severity") == "high")

    realism = min(10.0, 6.2 + len(messages) * 0.18 + role_count * 0.35)
    difficulty = min(10.0, 5.8 + len(issue_hints) * 0.55 + high_severity * 0.45)
    diversity = min(10.0, 5.5 + role_count * 0.8)
    consistency = min(10.0, 7.2 + evidence_count * 0.25)
    conflict = min(10.0, 5.0 + conflict_signals * 0.45)
    training_value = min(10.0, 6.0 + evidence_count * 0.4 + len(issue_hints) * 0.35)
    safety = 9.0
    return build_quality_scores(
        realism=realism,
        difficulty=difficulty,
        diversity=diversity,
        consistency=consistency,
        conflict=conflict,
        training_value=training_value,
        safety=safety,
    )


def llm_score_conversation(
    *,
    scenario: str,
    task_input: dict[str, Any],
    agents: list[Persona],
    messages: list[Message],
    issue_hints: list[dict[str, Any]],
    heuristic_scores: QualityScores,
) -> QualityScoringResult:
    client = build_deepseek_client()
    system_prompt = (
        "你是一名严格的 LLM-as-a-Judge 数据质量评估器。"
        "你负责评估多 Agent 合成对话是否适合作为训练数据。"
        "你必须只输出 JSON 对象，不要输出 Markdown。"
    )
    user_prompt = build_judge_prompt(
        scenario=scenario,
        task_input=task_input,
        agents=agents,
        messages=messages,
        issue_hints=issue_hints,
        heuristic_scores=heuristic_scores,
    )
    parsed = client.chat_object(system_prompt, user_prompt, temperature=0.2)
    scores = parse_llm_scores(parsed)
    feedback = parsed.get("feedback", [])
    if not isinstance(feedback, list):
        feedback = [str(feedback)]

    return QualityScoringResult(
        scores=scores,
        mode="enhanced_multi_judge",
        provider=client.provider,
        model=client.model,
        feedback=[str(item).strip() for item in feedback if str(item).strip()][:5],
        report=build_quality_report(
            scores=scores,
            scenario=scenario,
            messages=messages,
            issue_hints=issue_hints,
            feedback=[str(item).strip() for item in feedback if str(item).strip()][:5],
            llm_judge_available=True,
        ),
    )


def build_judge_prompt(
    *,
    scenario: str,
    task_input: dict[str, Any],
    agents: list[Persona],
    messages: list[Message],
    issue_hints: list[dict[str, Any]],
    heuristic_scores: QualityScores,
) -> str:
    agent_text = "\n".join(
        f"- {agent.role}: 性格={agent.personality}; 目标={agent.goal}; 关注={agent.focus}"
        for agent in agents
    )
    message_text = "\n".join(
        f"{message.turn}. [{message.role}] {message.content}" for message in messages
    )
    return f"""
请评估下面这条多 Agent 合成对话的训练数据质量。

评分维度必须是 0 到 10 分：
- realism：是否像真实团队讨论
- difficulty：是否包含推理难度、技术深度
- diversity：角色观点是否多样
- consistency：上下文是否一致，是否自相矛盾
- conflict：是否有真实冲突、追问和反驳
- training_value：是否适合训练该场景对应的业务 Agent
- safety：是否避免泄露、攻击、违法或不可控内容
- final_score：综合分

请输出 JSON：
{{
  "scores": {{
    "realism": 0,
    "difficulty": 0,
    "diversity": 0,
    "consistency": 0,
    "conflict": 0,
    "training_value": 0,
    "safety": 0,
    "final_score": 0
  }},
  "feedback": ["中文评语1", "中文评语2"]
}}

要求：
1. 不要因为文本是 AI 生成就自动给高分。
2. 如果对话没有引用任务输入或问题线索中的关键信息，consistency 和 training_value 应降低。
3. 如果角色说话风格没有差异，diversity 应降低。
4. 如果冲突只是口号，没有技术细节，conflict 应降低。
5. feedback 必须指出最重要的优点和风险。

场景：{scenario}
任务输入：
{json.dumps(task_input, ensure_ascii=False)}

识别到的问题线索：
{json.dumps(issue_hints, ensure_ascii=False)}

规则评分参考：
{json.dumps(heuristic_scores.model_dump(), ensure_ascii=False)}

Agent：
{agent_text}

对话：
{message_text}
""".strip()


def parse_llm_scores(parsed: dict[str, Any]) -> QualityScores:
    raw_scores = parsed.get("scores")
    if not isinstance(raw_scores, dict):
        raise RuntimeError("LLM judge response missing scores object")

    values = {
        key: clamp_score(float(raw_scores[key]))
        for key in [
            "realism",
            "difficulty",
            "diversity",
            "consistency",
            "conflict",
            "training_value",
            "safety",
        ]
    }
    final_score = raw_scores.get("final_score")
    if final_score is None:
        return build_quality_scores(**values)

    return QualityScores(
        **{key: round(value, 2) for key, value in values.items()},
        final_score=round(clamp_score(float(final_score)), 2),
    )


def build_quality_scores(
    *,
    realism: float,
    difficulty: float,
    diversity: float,
    consistency: float,
    conflict: float,
    training_value: float,
    safety: float,
) -> QualityScores:
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
        realism=round(clamp_score(realism), 2),
        difficulty=round(clamp_score(difficulty), 2),
        diversity=round(clamp_score(diversity), 2),
        consistency=round(clamp_score(consistency), 2),
        conflict=round(clamp_score(conflict), 2),
        training_value=round(clamp_score(training_value), 2),
        safety=round(clamp_score(safety), 2),
        final_score=round(clamp_score(final_score), 2),
    )


def build_quality_report(
    *,
    scores: QualityScores,
    scenario: str,
    messages: list[Message],
    issue_hints: list[dict[str, Any]],
    feedback: list[str],
    llm_judge_available: bool,
) -> QualityReport:
    diagnostics = build_dimension_diagnostics(scores)
    weaknesses = [
        item["reason"]
        for item in diagnostics
        if float(item["score"]) < 7.0
    ][:5]
    strengths = [
        item["reason"]
        for item in diagnostics
        if float(item["score"]) >= 8.0
    ][:5]
    rejection_reasons = build_rejection_reasons(scores, messages, issue_hints, weaknesses)
    improvement_actions = build_improvement_actions(diagnostics, scenario, issue_hints)
    votes = build_judge_votes(scores, llm_judge_available)
    decision = "accept" if scores.final_score >= 7.0 and not rejection_reasons else "reject"

    return QualityReport(
        grade=quality_grade(scores.final_score),
        decision=decision,
        pass_threshold=7.0,
        judge_votes=votes,
        dimension_diagnostics=diagnostics,
        strengths=strengths or feedback[:2],
        weaknesses=weaknesses,
        improvement_actions=improvement_actions,
        rejection_reasons=rejection_reasons,
    )


def build_dimension_diagnostics(scores: QualityScores) -> list[dict[str, Any]]:
    labels = {
        "realism": "真实感",
        "difficulty": "难度",
        "diversity": "多样性",
        "consistency": "一致性",
        "conflict": "冲突强度",
        "training_value": "训练价值",
        "safety": "安全性",
    }
    values = scores.model_dump()
    diagnostics: list[dict[str, Any]] = []
    for key, label in labels.items():
        score = float(values[key])
        if score >= 8:
            level = "strong"
            reason = f"{label}表现较强，可作为样本优势保留。"
        elif score >= 7:
            level = "pass"
            reason = f"{label}达到可用标准，但仍有优化空间。"
        elif score >= 5.5:
            level = "risk"
            reason = f"{label}偏弱，建议补充更具体的上下文、证据或角色差异。"
        else:
            level = "fail"
            reason = f"{label}不足，当前样本不适合直接进入高质量数据集。"
        diagnostics.append({"dimension": key, "label": label, "score": round(score, 2), "level": level, "reason": reason})
    return diagnostics


def build_judge_votes(scores: QualityScores, llm_judge_available: bool) -> list[dict[str, Any]]:
    votes = [
        {
            "judge": "structure_judge",
            "vote": "pass" if scores.consistency >= 7 and scores.diversity >= 6.5 else "reject",
            "reason": "检查上下文一致性、角色差异和结构完整度。",
        },
        {
            "judge": "training_value_judge",
            "vote": "pass" if scores.training_value >= 7 and scores.difficulty >= 6.5 else "reject",
            "reason": "检查样本是否具备训练价值、推理难度和可复用信息密度。",
        },
        {
            "judge": "safety_judge",
            "vote": "pass" if scores.safety >= 8 else "reject",
            "reason": "检查安全风险、违规内容和不可控输出。",
        },
    ]
    if llm_judge_available:
        votes.append(
            {
                "judge": "llm_judge",
                "vote": "pass" if scores.final_score >= 7 else "reject",
                "reason": "LLM-as-a-Judge 对整体样本质量进行综合判断。",
            }
        )
    return votes


def build_rejection_reasons(
    scores: QualityScores,
    messages: list[Message],
    issue_hints: list[dict[str, Any]],
    weaknesses: list[str],
) -> list[str]:
    reasons: list[str] = []
    if len(messages) < 4:
        reasons.append("对话轮数过少，缺少足够多轮互动。")
    if len({message.role for message in messages}) < 2:
        reasons.append("参与角色过少，无法体现 multi-agent 数据价值。")
    if issue_hints and scores.consistency < 6.5:
        reasons.append("对话没有充分承接任务线索或问题证据。")
    if scores.training_value < 6.5:
        reasons.append("训练价值不足，信息密度或可学习模式不够。")
    if scores.safety < 8:
        reasons.append("安全性未达标。")
    if scores.final_score < 7:
        reasons.extend(weaknesses[:2])
    return list(dict.fromkeys(reasons))[:5]


def build_improvement_actions(
    diagnostics: list[dict[str, Any]],
    scenario: str,
    issue_hints: list[dict[str, Any]],
) -> list[str]:
    actions: list[str] = []
    weak_dimensions = {str(item["dimension"]) for item in diagnostics if float(item["score"]) < 7}
    if "diversity" in weak_dimensions:
        actions.append("增强不同 Agent 的立场差异、语言风格和目标冲突。")
    if "consistency" in weak_dimensions:
        actions.append("要求 Agent 明确引用任务输入、问题线索或前文观点。")
    if "conflict" in weak_dimensions:
        actions.append("增加追问、反驳、边界条件和替代方案讨论。")
    if "training_value" in weak_dimensions:
        actions.append("补充可执行结论、判断依据和对业务场景有迁移价值的总结。")
    if issue_hints:
        actions.append("围绕已识别问题线索生成更具体的证据链和修复/处理方案。")
    if scenario == "technical_interview":
        actions.append("让面试官追问失败案例、工程权衡和候选人认知边界。")
    return list(dict.fromkeys(actions))[:6]


def quality_grade(final_score: float) -> str:
    if final_score >= 9:
        return "S"
    if final_score >= 8:
        return "A"
    if final_score >= 7:
        return "B"
    if final_score >= 6:
        return "C"
    return "D"


def clamp_score(value: float) -> float:
    return max(0.0, min(10.0, value))
