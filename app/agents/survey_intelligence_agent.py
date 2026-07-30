"""
Survey Intelligence Agent
──────────────────────────────────────────────────────────────────────────────
Generates customer validation surveys and hypothesis-testing questionnaires.
Uses the survey_intelligence_skill to structure unbiased questions.
Applies rigorous 5-point output validation via OutputValidator guardrail engine.

Skill      : survey_intelligence_skill
Score      : survey_quality_score (0–100)
Outputs    : survey_title, survey_objective, target_audience_summary,
             questions, survey_quality_score, confidence, disclaimer
"""
import logging
from typing import Any

from app.agents.base_agent import BaseAgent
from app.guardrails.output_guardrails import OutputValidator
from app.llm.llm_gateway import LLMGateway
from app.models.agent_models import AgentInput

logger = logging.getLogger(__name__)

REQUIRED_SURVEY_FIELDS = [
    "survey_title",
    "survey_objective",
    "questions",
    "confidence",
]

DEFAULT_SURVEY_OUTPUT = {
    "survey_title": "Customer Validation Survey",
    "survey_objective": "Understand target customer pain points and current workarounds.",
    "target_audience_summary": "Prospective early adopters facing the core problem statement.",
    "questions": [
        {
            "question_text": "How do you currently address this challenge in your daily workflow?",
            "question_type": "open_ended",
            "target_hypothesis": "Verify existence of current workarounds and pain severity.",
        },
        {
            "question_text": "On a scale of 1-5, how severe is this problem when it occurs?",
            "question_type": "rating_scale",
            "target_hypothesis": "Quantify urgency and problem intensity.",
        },
    ],
    "survey_quality_score": 75.0,
    "confidence": 0.7,
    "disclaimer": "This output provides decision-support guidance only. It does not constitute formal legal, financial, or tax advice.",
}


class SurveyIntelligenceAgent(BaseAgent):
    """
    Survey Intelligence Agent.
    Creates targeted, unbiased customer surveys to test key business assumptions.
    """

    agent_name = "survey_intelligence_agent"
    skill_name = "survey_intelligence_skill"

    def __init__(self, llm_gateway: LLMGateway) -> None:
        super().__init__(llm_gateway)
        self.validator = OutputValidator()

    # ── Prompt Builder ─────────────────────────────────────────────────────────

    def _build_prompt(self, agent_input: AgentInput) -> str:
        if not self.skill:
            raise ValueError(f"[{self.agent_name}] Skill not loaded.")

        target_cust = (
            agent_input.target_customer
            or agent_input.additional_context.get("target_customer")
            or "Prospective target customer base"
        )
        val_goal = (
            agent_input.founder_validation_goal
            or agent_input.additional_context.get("validation_goal")
            or "Validate core problem statement and willingness to switch"
        )
        problem_stmt = (
            agent_input.problem_statement
            or agent_input.additional_context.get("problem_statement")
            or "Unclear problem statement"
        )

        return self.skill.build_prompt(
            idea_title=agent_input.idea_title,
            idea_description=agent_input.idea_description,
            problem_statement=problem_stmt,
            target_customer=target_cust,
            validation_goal=val_goal,
        )

    # ── Output Parser & Validation Pipeline ─────────────────────────────────────

    def _parse_output(self, raw_content: str) -> dict[str, Any]:
        """
        Runs full 5-tier output validation:
        1. JSON syntax check
        2. Required fields presence check
        3. Score & range bounds check
        4. Disclaimer enforcement
        5. Forbidden advice detection
        """
        val_result = self.validator.validate_all(
            raw_content=raw_content,
            required_fields=REQUIRED_SURVEY_FIELDS,
            range_specs={
                "survey_quality_score": (0.0, 100.0),
                "confidence": (0.0, 1.0),
            },
            default_values=DEFAULT_SURVEY_OUTPUT,
        )

        if not val_result.is_valid:
            logger.warning(
                f"[{self.agent_name}] Validation failed with errors: {val_result.errors}. "
                "Applying fallback structured output."
            )

        data = val_result.data

        # Normalize score alias
        if "survey_quality_score" not in data or data["survey_quality_score"] is None:
            data["survey_quality_score"] = float(data.get("score", 70.0))

        # Ensure questions field is a list
        if not isinstance(data.get("questions"), list):
            data["questions"] = DEFAULT_SURVEY_OUTPUT["questions"]

        if val_result.warnings:
            logger.info(f"[{self.agent_name}] Validation warnings: {val_result.warnings}")

        return data

    # ── Score Extractor ────────────────────────────────────────────────────────

    def _extract_score(self, parsed_output: dict[str, Any]) -> float:
        """Extract survey_quality_score (0–100)."""
        score_val = parsed_output.get("survey_quality_score")
        if score_val is None:
            score_val = parsed_output.get("score", 70.0)
        try:
            return float(score_val)
        except (ValueError, TypeError):
            return 70.0
