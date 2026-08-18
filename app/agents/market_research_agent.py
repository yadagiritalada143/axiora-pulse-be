"""
Market Research Agent — Analysis 2 (Target Customer Profiling & Market Research)
──────────────────────────────────────────────────────────────────────────────
Forces a narrow, specific customer definition (F.O.U.N.D.E.R principle — 
"Own a Narrow Audience"), builds an Ideal Customer Profile (ICP), maps competitor
dynamics, and generates market opportunity signals from problem validation context.

Skill      : market_research_skill
Score      : market_opportunity_score (0–100)
Outputs    : audience_narrowness_score, primary_icp_summary, secondary_segments,
             persona_summary, red_flags,
             market_opportunity_score, market_opportunity_summary,
             target_customer_segments, competitor_overview,
             opportunity_signals, risk_signals, confidence
"""
import json
import logging
import re
from typing import Any

from app.agents.base_agent import BaseAgent
from app.llm.llm_gateway import LLMGateway
from app.models.agent_models import AgentInput

logger = logging.getLogger(__name__)


class MarketResearchAgent(BaseAgent):
    """
    Second agent in the pipeline (Analysis 2: Target Customer & Market Research).
    Uses market_research_skill to profile the Ideal Customer and score market opportunity.
    """
    agent_name = "market_research_agent"
    skill_name = "market_research_skill"

    def __init__(self, llm_gateway: LLMGateway) -> None:
        super().__init__(llm_gateway)

    # ── Prompt builder ─────────────────────────────────────────────────────────

    def _build_prompt(self, agent_input: AgentInput) -> str:
        if not self.skill:
            raise ValueError("Skill not loaded for MarketResearchAgent")

        ctx = agent_input.additional_context

        # Pull problem analysis context passed forward from IdeaValidationAgent
        problem_summary = (
            ctx.get("problem_statement_summary")
            or ctx.get("problem_summary")
            or agent_input.problem_statement
        )
        falsifiable_problem = (
            ctx.get("falsifiable_problem_sentence")
            or agent_input.problem_statement
        )
        who_and_frequency = (
            ctx.get("who_and_frequency")
            or ctx.get("customer_hypothesis")
            or "Not specified"
        )

        return self.skill.build_prompt(
            idea_title=agent_input.idea_title,
            idea_description=agent_input.idea_description,
            problem_statement=agent_input.problem_statement,
            industry=agent_input.industry,
            geography=agent_input.geography,
            business_type=agent_input.business_type,
            problem_statement_summary=problem_summary,
            falsifiable_problem_sentence=falsifiable_problem,
            who_and_frequency=who_and_frequency,
        )

    # ── Output parser ──────────────────────────────────────────────────────────

    def _parse_output(self, raw_content: str) -> dict[str, Any]:
        """
        Parse the LLM response into the Analysis 2 market research schema.
        Applies defaults for missing fields and validates value ranges.
        """
        parsed: dict[str, Any] = {}

        try:
            parsed = json.loads(raw_content)
        except json.JSONDecodeError:
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

        # ── Normalize market opportunity score ─────────────────────────────────
        market_score = parsed.get("market_opportunity_score") or parsed.get("market_score", 50)
        parsed["market_opportunity_score"] = market_score

        # ── Normalize audience narrowness score ────────────────────────────────
        narrowness_score = parsed.get("audience_narrowness_score", 30)
        parsed["audience_narrowness_score"] = narrowness_score

        # ── Defaults for string fields ─────────────────────────────────────────
        parsed.setdefault(
            "primary_icp_summary",
            "Customer profile requires further clarification from founder."
        )
        parsed.setdefault(
            "persona_summary",
            "Persona narrative could not be determined from available context."
        )
        parsed.setdefault(
            "market_opportunity_summary",
            "Market analysis indicates potential opportunity requiring further validation."
        )

        # ── Defaults for array fields ──────────────────────────────────────────
        parsed.setdefault("secondary_segments", [])
        parsed.setdefault("red_flags", [])
        parsed.setdefault("target_customer_segments", ["Early adopters facing the validated pain point."])
        parsed.setdefault("competitor_overview", ["Existing manual processes and incumbent market solutions."])
        parsed.setdefault("opportunity_signals", ["Growing market interest in this problem space."])
        parsed.setdefault("risk_signals", ["Customer acquisition friction and buyer switching costs."])
        parsed.setdefault("confidence", 0.5)

        # ── Clamp numeric scores ───────────────────────────────────────────────
        try:
            parsed["market_opportunity_score"] = max(0, min(100, int(parsed["market_opportunity_score"])))
        except (ValueError, TypeError):
            parsed["market_opportunity_score"] = 50

        try:
            parsed["audience_narrowness_score"] = max(0, min(100, int(parsed["audience_narrowness_score"])))
        except (ValueError, TypeError):
            parsed["audience_narrowness_score"] = 30

        try:
            parsed["confidence"] = max(0.0, min(1.0, float(parsed["confidence"])))
        except (ValueError, TypeError):
            parsed["confidence"] = 0.5

        parsed.setdefault("research_sources", [])
        if not isinstance(parsed.get("research_sources"), list):
            parsed["research_sources"] = []

        # ── Ensure list fields are arrays of strings ───────────────────────────
        for field in (
            "secondary_segments",
            "red_flags",
            "target_customer_segments",
            "competitor_overview",
            "opportunity_signals",
            "risk_signals",
        ):
            if not isinstance(parsed.get(field), list):
                val = parsed.get(field, "")
                parsed[field] = [str(val)] if val else []

        return parsed


    # ── Score extractor ────────────────────────────────────────────────────────

    def _extract_score(self, parsed_output: dict[str, Any]) -> float:
        return float(parsed_output.get("market_opportunity_score", 50.0))
