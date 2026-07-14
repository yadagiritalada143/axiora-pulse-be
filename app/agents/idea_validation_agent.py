"""
Idea Validation Agent
──────────────────────────────────────────────────────────────────────────────
Evaluates whether a founder's idea is clear, solves a real problem,
has a defined customer, and is ready for structured validation.

Skill      : idea_validation_skill
Score      : idea_clarity_score (0–100)
Outputs    : problem_summary, customer_hypothesis, key_assumptions,
             red_flags, initial_recommendation, confidence
"""
import json
import logging
import re
from typing import Any

from app.agents.base_agent import BaseAgent
from app.llm.llm_gateway import LLMGateway
from app.models.agent_models import AgentInput

logger = logging.getLogger(__name__)

# Valid recommendation values — guard against model hallucinations
VALID_RECOMMENDATIONS = {
    "proceed_to_validation",
    "needs_clarification",
    "reduce_scope",
    "pivot",
    "hold",
}
class IdeaValidationAgent(BaseAgent):
    """
    First agent in the Phase 1 pipeline.
    Uses the idea_validation_skill to score and analyse the founder's idea.
    """
    agent_name = "idea_validation_agent"
    skill_name = "idea_validation_skill"

    def __init__(self, llm_gateway: LLMGateway) -> None:
        super().__init__(llm_gateway)

    # ── Prompt builder ─────────────────────────────────────────────────────────

    def _build_prompt(self, agent_input: AgentInput) -> str:
        if not self.skill:
            raise ValueError("Skill not loaded for IdeaValidationAgent")

        return self.skill.build_prompt(
            idea_title=agent_input.idea_title,
            idea_description=agent_input.idea_description,
            problem_statement=agent_input.problem_statement,
            target_customer=agent_input.target_customer,
            industry=agent_input.industry,
            founder_validation_goal=agent_input.founder_validation_goal,
        )

    # ── Output parser ──────────────────────────────────────────────────────────

    def _parse_output(self, raw_content: str) -> dict[str, Any]:
        """
        Parse the LLM response into the idea validation schema.
        Applies defaults for missing fields and validates value ranges.
        """
        parsed: dict[str, Any] = {}

        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError:
            # Attempt to extract JSON block from freeform text
            match = re.search(r"\{.*\}", raw_content, re.DOTALL)
            if match:
                try:
                    parsed = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

            if not parsed:
                logger.warning(
                    f"[{self.agent_name}] Could not parse JSON. "
                    f"Raw (first 300 chars): {raw_content[:300]}"
                )
                raise json.JSONDecodeError("No valid JSON found", raw_content, 0)

        # ── Apply defaults for missing fields ──────────────────────────────────
        parsed.setdefault("idea_clarity_score", 40)
        parsed.setdefault("problem_summary", "Unable to generate a problem summary.")
        parsed.setdefault("customer_hypothesis", "Not specified — more detail needed.")
        parsed.setdefault("key_assumptions", ["Customers have this problem", "They will pay for a solution"])
        parsed.setdefault("red_flags", [])
        parsed.setdefault("initial_recommendation", "needs_clarification")
        parsed.setdefault("confidence", 0.4)
        parsed.setdefault(
            "disclaimer",
            "This is decision-support guidance only, not professional business advice.",
        )

        # ── Validate and clamp numeric fields ──────────────────────────────────
        try:
            parsed["idea_clarity_score"] = max(0, min(100, int(parsed["idea_clarity_score"])))
        except (ValueError, TypeError):
            parsed["idea_clarity_score"] = 40

        try:
            parsed["confidence"] = max(0.0, min(1.0, float(parsed["confidence"])))
        except (ValueError, TypeError):
            parsed["confidence"] = 0.4

        # ── Validate recommendation enum ───────────────────────────────────────
        rec = str(parsed.get("initial_recommendation", "")).lower().replace(" ", "_")
        if rec not in VALID_RECOMMENDATIONS:
            logger.warning(f"[{self.agent_name}] Invalid recommendation: '{rec}' → defaulting to 'needs_clarification'")
            parsed["initial_recommendation"] = "needs_clarification"
        else:
            parsed["initial_recommendation"] = rec

        # ── Ensure lists are actually lists ────────────────────────────────────
        for field in ("key_assumptions", "red_flags"):
            if not isinstance(parsed.get(field), list):
                val = parsed.get(field, "")
                parsed[field] = [str(val)] if val else []

        return parsed

    # ── Score extractor ────────────────────────────────────────────────────────

    def _extract_score(self, parsed_output: dict[str, Any]) -> float:
        return float(parsed_output.get("idea_clarity_score", 40))
