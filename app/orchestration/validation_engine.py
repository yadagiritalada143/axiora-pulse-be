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

Phase 1 active weights (sum to 1.0):
  idea_validation_agent      = 0.35 (35%)
  market_research_agent      = 0.35 (35%)
  survey_intelligence_agent  = 0.30 (30%)

Future Phase 2+ targets:
  idea_validation_agent      = 0.20
  market_research_agent      = 0.20
  survey_intelligence_agent  = 0.25
  gtm_strategy_agent         = 0.15
  financial_readiness_agent  = 0.20
"""
import logging
from typing import Any

from app.models.orchestration_models import ValidationVerdict

logger = logging.getLogger(__name__)


# ── Scoring weights ────────────────────────────────────────────────────────────
AGENT_WEIGHTS: dict[str, float] = {
    "idea_validation_agent": 0.35,
    "market_research_agent": 0.35,
    "survey_intelligence_agent": 0.30,
    # Phase 2+ addition:
    # "gtm_strategy_agent": 0.15,
    # "financial_readiness_agent": 0.20,
}

# ── Verdict thresholds ─────────────────────────────────────────────────────────
_VERDICT_TABLE = [
    (80.0, ValidationVerdict.BUILD),
    (60.0, ValidationVerdict.VALIDATE_MORE),
    (40.0, ValidationVerdict.REDUCE_SCOPE),
    (0.0, ValidationVerdict.HOLD),
]

_VERDICT_MESSAGES = {
    ValidationVerdict.BUILD: (
        "Your idea shows strong validation signals across problem clarity, target market profiling, "
        "and survey hypothesis design. Consider building a focused MVP to test your key assumptions."
    ),
    ValidationVerdict.VALIDATE_MORE: (
        "Your idea has real potential, but some critical assumptions still need testing. "
        "I recommend running a short validation survey with your target customers before committing to building."
    ),
    ValidationVerdict.REDUCE_SCOPE: (
        "The idea as described may be too broad or has significant clarity gaps. "
        "Try narrowing to one specific problem for one specific customer segment first."
    ),
    ValidationVerdict.PIVOT: (
        "The current idea framing has multiple gaps or conflicts. "
        "Consider revisiting the core problem or exploring a different approach to the same customer need."
    ),
    ValidationVerdict.HOLD: (
        "We need considerably more information to validate this idea. "
        "Please provide more detail about the problem, target customer, and validation goal."
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

        # 1. idea_validation_agent
        idea_data: dict = agent_results.get("idea_validation_agent", {}).get("data", {})
        if idea_data:
            score = idea_data.get("problem_clarity_score") or idea_data.get("idea_clarity_score", 0)
            problem = idea_data.get("problem_statement_summary") or idea_data.get("problem_summary", "")
            customer = idea_data.get("who_and_frequency") or idea_data.get("customer_hypothesis", "")

            if score >= 60 and problem:
                strengths.append(f"Problem Definition: {problem}")
            if score >= 60 and customer:
                strengths.append(f"Customer Cohort: {customer}")

            for flag in idea_data.get("red_flags", []):
                risks.append(str(flag))

            assumptions_list = idea_data.get("assumption_list") or idea_data.get("key_assumptions", [])
            for assumption in assumptions_list:
                assumptions.append(str(assumption))

        # 2. market_research_agent
        market_data: dict = agent_results.get("market_research_agent", {}).get("data", {})
        if market_data:
            icp = market_data.get("primary_icp_summary", "")
            if icp:
                strengths.append(f"Primary ICP: {icp}")
            persona = market_data.get("persona_summary", "")
            if persona:
                strengths.append(f"Persona: {persona}")

            for signal in market_data.get("opportunity_signals", []):
                strengths.append(f"Market Signal: {signal}")
            for flag in market_data.get("red_flags", []):
                risks.append(str(flag))
            for risk in market_data.get("risk_signals", []):
                risks.append(str(risk))

        # 3. survey_intelligence_agent
        survey_data: dict = agent_results.get("survey_intelligence_agent", {}).get("data", {})
        if survey_data:
            stitle = survey_data.get("survey_title", "")
            if stitle:
                strengths.append(f"Survey Objective: Designed '{stitle}' to test core assumptions.")
            q_count = len(survey_data.get("questions", []))
            if q_count > 0:
                strengths.append(f"Hypothesis Questionnaire: {q_count} targeted questions generated.")

        # Verdict-based next steps
        if verdict == ValidationVerdict.BUILD:
            recommendations.append("Deploy validation survey to 20-30 target respondents.")
            recommendations.append("Build landing page prototype to capture early signups.")
        elif verdict == ValidationVerdict.VALIDATE_MORE:
            recommendations.append("Run customer interviews to confirm pain severity.")
            recommendations.append("Distribute validation survey to refine value proposition.")
        elif verdict == ValidationVerdict.REDUCE_SCOPE:
            recommendations.append("Focus on one core pain point and single ideal customer profile.")
        elif verdict == ValidationVerdict.HOLD:
            recommendations.append("Gather further detail on problem severity and target buyer profile.")

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

        risk_note = f" Key risk to address: {risks[0]}" if risks else ""
        top_rec = f" Suggested next step: {recommendations[0]}" if recommendations else ""

        disclaimer = (
            "\n\n⚠ This is decision-support guidance only — "
            "not professional business, legal, financial, or investment advice."
        )

        return (
            f"[Validation Score: {score:.0f}/100 — {verdict.value.replace('_', ' ').upper()}]\n\n"
            f"{base}{risk_note}{top_rec}{disclaimer}"
        )

    # ── Empty result ──────────────────────────────────────────────────────────

    def _empty_result(self) -> dict[str, Any]:
        return {
            "validation_score": 0.0,
            "confidence_rating": 0.0,
            "verdict": ValidationVerdict.HOLD,
            "strengths": [],
            "risks": ["No agent results were produced."],
            "assumptions": [],
            "recommendations": ["Please retry the validation."],
            "mentor_summary": (
                "[Validation Score: 0/100 — HOLD]\n\n"
                "We could not complete the validation at this time. Please try again.\n\n"
                "⚠ This is decision-support guidance only — "
                "not professional business, legal, financial, or investment advice."
            ),
        }


# Module-level singleton
validation_engine = ValidationEngine()
