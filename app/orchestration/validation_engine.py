"""
Validation Engine
──────────────────────────────────────────────────────────────────────────────
Pure business logic — NOT an LLM call.

Takes aggregated agent results and produces:
  - validation_score   (0–100 weighted average)
  - confidence_rating  (0.0–1.0 average across agents)
  - verdict            (Build / Validate More / Reduce Scope / Pivot / Hold)
  - strengths          (extracted from agent data)
  - risks              (extracted from red_flags)
  - assumptions        (extracted from key_assumptions)
  - recommendations    (next-step guidance)
  - mentor_summary     (human-readable explanation for the AI Mentor)

Phase 1 weights
  idea_validation_agent = 1.0 (100%)  ← only agent active right now

Phase 2+ weights (will normalise to 1.0 total):
  idea_validation_agent  = 0.20
  market_research_agent  = 0.20
  survey_intelligence    = 0.25
  gtm_strategy_agent     = 0.15
  financial_readiness    = 0.20
"""
import logging
from typing import Any

from app.models.orchestration_models import ValidationVerdict

logger = logging.getLogger(__name__)


# ── Scoring weights ────────────────────────────────────────────────────────────
# Must sum to 1.0.  Update here when a new agent becomes active.
AGENT_WEIGHTS: dict[str, float] = {
    "idea_validation_agent": 1.0,
    # Phase 2 (uncomment and re-normalise):
    # "market_research_agent":      0.20,
    # "survey_intelligence_agent":  0.25,
    # "gtm_strategy_agent":         0.15,
    # "financial_readiness_agent":  0.20,
}

# ── Verdict thresholds ─────────────────────────────────────────────────────────
_VERDICT_TABLE = [
    (80.0, ValidationVerdict.BUILD),
    (60.0, ValidationVerdict.VALIDATE_MORE),
    (40.0, ValidationVerdict.REDUCE_SCOPE),
    (0.0,  ValidationVerdict.HOLD),
]

_VERDICT_MESSAGES = {
    ValidationVerdict.BUILD: (
        "Your idea shows strong validation signals. "
        "The problem is well-defined and the customer hypothesis is clear. "
        "Consider building a focused MVP to test your key assumptions."
    ),
    ValidationVerdict.VALIDATE_MORE: (
        "Your idea has real potential, but some critical assumptions still need testing. "
        "I recommend running a short validation survey with your target customers "
        "before committing to building."
    ),
    ValidationVerdict.REDUCE_SCOPE: (
        "The idea as described may be too broad or has significant clarity gaps. "
        "Try narrowing to one specific problem for one specific customer segment first."
    ),
    ValidationVerdict.PIVOT: (
        "The current idea framing has multiple gaps or conflicts. "
        "Consider revisiting the core problem or exploring a different approach "
        "to the same customer need."
    ),
    ValidationVerdict.HOLD: (
        "We need considerably more information to validate this idea. "
        "Please provide more detail about the problem, target customer, "
        "and what you specifically want to validate."
    ),
}


def _score_to_verdict(score: float) -> ValidationVerdict:
    for threshold, verdict in _VERDICT_TABLE:
        if score >= threshold:
            return verdict
    return ValidationVerdict.HOLD


class ValidationEngine:
    """
    Calculates a weighted validation score and verdict from aggregated
    agent results. Contains zero LLM calls — pure deterministic logic.
    """

    def calculate(self, aggregated: dict[str, Any]) -> dict[str, Any]:
        agent_results: dict[str, Any] = aggregated.get("agent_results", {})

        if not agent_results:
            logger.warning("[ValidationEngine] No agent results to score")
            return self._empty_result()

        # ── Weighted score ─────────────────────────────────────────────────────
        total_weight = 0.0
        weighted_score = 0.0
        confidence_values: list[float] = []

        for agent_name, result in agent_results.items():
            weight = AGENT_WEIGHTS.get(agent_name, 0.0)
            if weight == 0.0:
                logger.debug(f"[ValidationEngine] No weight for '{agent_name}' — skipping")
                continue

            raw_score = result.get("score") or 0.0
            raw_confidence = result.get("confidence") or 0.5

            weighted_score += float(raw_score) * weight
            total_weight += weight
            confidence_values.append(float(raw_confidence))

        if total_weight == 0.0:
            logger.warning("[ValidationEngine] Total weight is 0 — check AGENT_WEIGHTS")
            return self._empty_result()

        final_score = weighted_score / total_weight
        final_score = max(0.0, min(100.0, final_score))

        final_confidence = (
            sum(confidence_values) / len(confidence_values)
            if confidence_values else 0.5
        )

        # ── Verdict ────────────────────────────────────────────────────────────
        verdict = _score_to_verdict(final_score)

        # ── Extract human-readable insights ────────────────────────────────────
        strengths, risks, assumptions, recommendations = self._extract_insights(
            agent_results, verdict
        )

        # ── Mentor summary ─────────────────────────────────────────────────────
        mentor_summary = self._build_mentor_summary(
            final_score, verdict, risks, recommendations
        )

        logger.info(
            f"[ValidationEngine] Score={final_score:.1f} | "
            f"Confidence={final_confidence:.2f} | Verdict={verdict}"
        )

        return {
            "validation_score": round(final_score, 1),
            "confidence_rating": round(final_confidence, 2),
            "verdict": verdict,
            "strengths": strengths,
            "risks": risks,
            "assumptions": assumptions,
            "recommendations": recommendations,
            "mentor_summary": mentor_summary,
        }

    # ── Insight extraction ─────────────────────────────────────────────────────

    def _extract_insights(
        self,
        agent_results: dict[str, Any],
        verdict: ValidationVerdict,
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        strengths: list[str] = []
        risks: list[str] = []
        assumptions: list[str] = []
        recommendations: list[str] = []

        # ── idea_validation_agent ──────────────────────────────────────────────
        idea_data: dict = agent_results.get("idea_validation_agent", {}).get("data", {})
        if idea_data:
            # Strengths — use problem summary if clarity is decent
            score = idea_data.get("idea_clarity_score", 0)
            problem = idea_data.get("problem_summary", "")
            customer = idea_data.get("customer_hypothesis", "")

            if score >= 60 and problem:
                strengths.append(f"Clear problem identified: {problem}")
            if score >= 60 and customer:
                strengths.append(f"Customer hypothesis defined: {customer}")

            # Risks
            for flag in idea_data.get("red_flags", []):
                risks.append(str(flag))

            # Assumptions
            for assumption in idea_data.get("key_assumptions", []):
                assumptions.append(str(assumption))

            # Recommendation from agent
            agent_rec = idea_data.get("initial_recommendation", "")
            if agent_rec:
                recommendations.append(
                    f"Idea validation analysis suggests: {agent_rec.replace('_', ' ').title()}"
                )

        # Add next-step recommendations based on verdict
        if verdict == ValidationVerdict.BUILD:
            recommendations.append(
                "Create a landing page or simple prototype to test real demand."
            )
            recommendations.append(
                "Run a 6-question validation survey to confirm willingness-to-pay."
            )
        elif verdict == ValidationVerdict.VALIDATE_MORE:
            recommendations.append(
                "Create a short validation survey and target 20–30 potential customers."
            )
            recommendations.append(
                "Validate the top 2–3 assumptions before investing in development."
            )
        elif verdict == ValidationVerdict.REDUCE_SCOPE:
            recommendations.append(
                "Pick ONE customer segment and ONE specific problem to start with."
            )
        elif verdict == ValidationVerdict.PIVOT:
            recommendations.append(
                "Revisit the problem statement — talk to 5 potential customers first."
            )
        elif verdict == ValidationVerdict.HOLD:
            recommendations.append(
                "Provide more details about the problem, customer, and validation goal."
            )

        return strengths, risks, assumptions, recommendations

    # ── Mentor summary builder ─────────────────────────────────────────────────

    def _build_mentor_summary(
        self,
        score: float,
        verdict: ValidationVerdict,
        risks: list[str],
        recommendations: list[str],
    ) -> str:
        base = _VERDICT_MESSAGES.get(verdict, "Validation complete.")

        risk_note = ""
        if risks:
            risk_note = f" Key risk to address: {risks[0]}"

        top_rec = ""
        if recommendations:
            top_rec = f" Suggested next step: {recommendations[0]}"

        disclaimer = (
            "\n\n⚠ This is decision-support guidance only — "
            "not professional business, legal, financial, or investment advice."
        )

        return (
            f"[Validation Score: {score:.0f}/100 — {verdict.value.replace('_', ' ').upper()}]\n\n"
            f"{base}{risk_note}{top_rec}{disclaimer}"
        )

    # ── Empty result (when no agents ran) ─────────────────────────────────────

    def _empty_result(self) -> dict[str, Any]:
        return {
            "validation_score": 0.0,
            "confidence_rating": 0.0,
            "verdict": ValidationVerdict.HOLD,
            "strengths": [],
            "risks": ["No agent results were produced."],
            "assumptions": [],
            "recommendations": [
                "Please retry the validation. If the problem persists, check server logs."
            ],
            "mentor_summary": (
                "[Validation Score: 0/100 — HOLD]\n\n"
                "We could not complete the validation at this time. Please try again.\n\n"
                "⚠ This is decision-support guidance only — "
                "not professional business, legal, financial, or investment advice."
            ),
        }


# Module-level singleton
validation_engine = ValidationEngine()
