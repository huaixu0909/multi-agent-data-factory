import uuid
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from app.core.models import ConversationRecord, Message, Persona, QualityScores
from app.core.scenario import Scenario


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
    description = "模拟 Developer、Reviewer、Challenger、Judge 的代码审查讨论。"
    status = "v0.2 / scenario-ready"
    endpoint = "/api/simulations/code-review"
    agent_roles = ["Developer", "Reviewer", "Challenger", "Judge"]

    def simulate(self, request: CodeReviewSimulationRequest) -> ConversationRecord:
        agents = self.generate_personas(request.review_focus)
        issues = self.detect_code_issues(request.code_diff, request.language)
        messages = self.generate_messages(agents, issues, request.max_turns)
        scores = self.score_conversation(messages, issues)
        return ConversationRecord(
            conversation_id=f"conv_{uuid.uuid4().hex[:12]}",
            task_type=self.name,
            scenario=self.name,
            language=request.language,
            code_diff=request.code_diff,
            review_focus=request.review_focus,
            task_input=request.model_dump(),
            agents=agents,
            messages=messages,
            scores=scores,
            accepted=scores.final_score >= 7.0,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

    def generate_personas(self, review_focus: list[str]) -> list[Persona]:
        focus_text = ", ".join(review_focus) if review_focus else "code quality"
        return [
            Persona(
                agent_id="agent_developer",
                role="Developer",
                personality="pragmatic",
                style="defensive but cooperative",
                focus="shipping speed and implementation intent",
                goal="explain the change and get the review accepted",
                tolerance="medium",
            ),
            Persona(
                agent_id="agent_reviewer",
                role="Reviewer",
                personality="strict",
                style="precise and evidence-driven",
                focus=focus_text,
                goal="identify concrete risks and request actionable fixes",
                tolerance="low",
            ),
            Persona(
                agent_id="agent_challenger",
                role="Challenger",
                personality="skeptical",
                style="argumentative and alternative-seeking",
                focus="edge cases and trade-offs",
                goal="increase reasoning depth by challenging easy conclusions",
                tolerance="low",
            ),
            Persona(
                agent_id="agent_judge",
                role="Judge",
                personality="balanced",
                style="concise and criteria-based",
                focus="training data quality and final decision",
                goal="summarize the discussion and label the review outcome",
                tolerance="high",
            ),
        ]

    def detect_code_issues(self, code_diff: str, language: str) -> list[CodeIssue]:
        lower = code_diff.lower()
        issues: list[CodeIssue] = []

        patterns: list[tuple[str, Literal["low", "medium", "high"], list[str], str]] = [
            (
                "security",
                "high",
                ["select ", " where ", "f\"", "format(", "%"],
                "Potential SQL injection or unsafe query construction. Prefer parameterized queries.",
            ),
            (
                "security",
                "high",
                ["eval(", "exec("],
                "Dynamic code execution can become remote code execution. Remove eval/exec or sandbox strictly.",
            ),
            (
                "secret",
                "high",
                ["api_key", "password", "secret", "token"],
                "Possible hardcoded secret. Move sensitive values into environment variables or a secret manager.",
            ),
            (
                "reliability",
                "medium",
                ["except:", "except exception"],
                "Broad exception handling can hide failures. Catch specific exceptions and log context.",
            ),
            (
                "observability",
                "low",
                ["print("],
                "Debug prints are not production logging. Use structured logging with request context.",
            ),
            (
                "performance",
                "medium",
                ["for ", "query(", "select "],
                "Loop-level database calls may create N+1 queries. Batch loading or prefetching may be safer.",
            ),
            (
                "testing",
                "medium",
                ["def ", "class ", "return "],
                "The diff appears functional but has no visible test update. Add a regression test for the changed behavior.",
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
                    suggestion="Ask reviewers to focus on naming, boundary conditions, tests, and rollback behavior.",
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
                "I submitted this diff to unblock the feature quickly. The intent is to keep the change small and avoid touching unrelated modules.",
            ),
            self.build_message(
                2,
                reviewer,
                f"I see a {primary.severity}-severity {primary.issue_type} risk. Evidence: `{primary.evidence}`. {primary.suggestion}",
            ),
            self.build_message(
                3,
                developer,
                "That concern is fair, but the input currently comes from an internal path. I chose the smaller change because the release is time-sensitive.",
            ),
            self.build_message(
                4,
                challenger,
                "Internal input is not a stable safety boundary. If this code path is reused later, the risk becomes invisible. We should fix the design rather than rely on caller discipline.",
            ),
            self.build_message(
                5,
                reviewer,
                f"There is also a {secondary.issue_type} concern: `{secondary.evidence}`. The review should require a test or a safer implementation before approval.",
            ),
            self.build_message(
                6,
                developer,
                "I can update the patch with a safer implementation and add a regression test. I would prefer not to expand the scope beyond the risky path.",
            ),
            self.build_message(
                7,
                challenger,
                "A narrow fix is acceptable if the test proves the risky case. Otherwise this becomes a style-only review and loses training value.",
            ),
            self.build_message(
                8,
                judge,
                "Decision: request changes. The discussion contains a concrete risk, evidence from the diff, a counterargument, and an actionable resolution. This is useful code review training data.",
            ),
        ]

        if max_turns >= 10:
            messages.insert(
                6,
                self.build_message(
                    7,
                    reviewer,
                    "Please include the exact failure mode in the test name so future maintainers understand why the safer path exists.",
                ),
            )
            messages.insert(
                7,
                self.build_message(
                    8,
                    developer,
                    "Agreed. I will add the test name and keep the implementation localized to this function.",
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
            if any(token in item.content.lower() for token in ["risk", "concern", "not", "should", "otherwise"])
        )
        evidence_count = sum(1 for item in messages if "`" in item.content or "Evidence:" in item.content)
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

