"""
Idea Validation Agent — Analysis 1 (Problem Analysis)
──────────────────────────────────────────────────────────────────────────────
Evaluates whether a founder's idea is anchored in a real, evidenced, and
sufficiently painful problem — not an assumed or solution-shaped concept.

Skill      : idea_validation_skill
Score      : problem_clarity_score (0–100)
Outputs    : problem_clarity_score, falsifiable_problem_sentence,
             problem_statement_summary, pain_type_classification,
             who_and_frequency, current_workarounds, assumption_list,
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

VALID_PAIN_TYPES = {
    "painkiller": "Painkiller",
    "vitamin": "Vitamin",
    "unclear": "Unclear",
}


class IdeaValidationAgent(BaseAgent):
    """
    First agent in the Phase 1 pipeline (Analysis 1: Problem Analysis).
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

        evidence = (
            agent_input.founder_evidence
            or agent_input.additional_context.get("founder_evidence")
            or "No explicit evidence provided beyond founder assertion."
        )

        return self.skill.build_prompt(
            idea_title=agent_input.idea_title,
            idea_description=agent_input.idea_description,
            problem_statement=agent_input.problem_statement,
            industry=agent_input.industry,
            geography=agent_input.geography,
            founder_validation_goal=agent_input.founder_validation_goal,
            founder_evidence=evidence,
        )

    # ── Output parser ──────────────────────────────────────────────────────────

    def _parse_output(self, raw_content: str) -> dict[str, Any]:
        """
        Parse the LLM response into the Analysis 1 problem analysis schema.
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

        # ── Normalize alias fields for score & summaries ───────────────────────
        score_val = parsed.get("problem_clarity_score")
        if score_val is None:
            score_val = parsed.get("idea_clarity_score", 40)

        summary_val = (
            parsed.get("problem_statement_summary")
            or parsed.get("problem_summary")
            or "Unable to generate a problem statement summary."
        )
        assumptions_val = (
            parsed.get("assumption_list")
            or parsed.get("key_assumptions")
            or ["Customers have this problem", "They will pay for a solution"]
        )

        who_val = (
            parsed.get("who_and_frequency")
            or parsed.get("customer_hypothesis")
            or "Not specified — frequency and user cohort need clarification."
        )
        parsed["who_and_frequency"] = who_val
        parsed["customer_hypothesis"] = who_val

        parsed["problem_clarity_score"] = score_val
        parsed["idea_clarity_score"] = score_val
        parsed["problem_statement_summary"] = summary_val
        parsed["problem_summary"] = summary_val
        parsed["assumption_list"] = assumptions_val if isinstance(assumptions_val, list) else [str(assumptions_val)]
        parsed["key_assumptions"] = parsed["assumption_list"]

        # ── Apply defaults for Analysis 1 fields ───────────────────────────────
        parsed.setdefault("falsifiable_problem_sentence", "Problem statement requires further definition.")
        parsed.setdefault("pain_type_classification", "Unclear")
        parsed.setdefault("current_workarounds", "Not specified — existing substitutes need investigation.")
        parsed.setdefault("red_flags", [])
        parsed.setdefault("initial_recommendation", "needs_clarification")
        parsed.setdefault("confidence", 0.4)
        parsed.setdefault(
            "disclaimer",
            "This is decision-support guidance only, not professional business advice.",
        )

        # ── Validate and clamp numeric fields ──────────────────────────────────
        try:
            clamped_score = max(0, min(100, int(parsed["problem_clarity_score"])))
            parsed["problem_clarity_score"] = clamped_score
            parsed["idea_clarity_score"] = clamped_score
        except (ValueError, TypeError):
            parsed["problem_clarity_score"] = 40
            parsed["idea_clarity_score"] = 40

        try:
            parsed["confidence"] = max(0.0, min(1.0, float(parsed["confidence"])))
        except (ValueError, TypeError):
            parsed["confidence"] = 0.4

        # ── Validate pain type enum ─────────────────────────────────────────────
        ptype = str(parsed.get("pain_type_classification", "")).lower().strip()
        parsed["pain_type_classification"] = VALID_PAIN_TYPES.get(ptype, "Unclear")

        # ── Validate recommendation enum ───────────────────────────────────────
        rec = str(parsed.get("initial_recommendation", "")).lower().replace(" ", "_")
        if rec not in VALID_RECOMMENDATIONS:
            logger.warning(f"[{self.agent_name}] Invalid recommendation: '{rec}' → defaulting to 'needs_clarification'")
            parsed["initial_recommendation"] = "needs_clarification"
        else:
            parsed["initial_recommendation"] = rec

        # ── Ensure list fields are arrays of strings ───────────────────────────
        for field in ("assumption_list", "key_assumptions", "red_flags"):
            if not isinstance(parsed.get(field), list):
                val = parsed.get(field, "")
                parsed[field] = [str(val)] if val else []

        return parsed

    # ── Score extractor ────────────────────────────────────────────────────────

    def _extract_score(self, parsed_output: dict[str, Any]) -> float:
        score_val = parsed_output.get("problem_clarity_score")
        if score_val is None:
            score_val = parsed_output.get("idea_clarity_score", 40)
        return float(score_val)
