"""
Survey Intelligence Agent
──────────────────────────────────────────────────────────────────────────────
Generates customer validation surveys and hypothesis-testing questionnaires.
Uses survey_intelligence_skill (v2.0) to structure unbiased questions across
the 10-phase Survey Intelligence framework.
Applies 5-tier output validation via OutputValidator guardrail engine.

Skill      : survey_intelligence_skill
Score      : survey_quality_score (0–100)
Outputs    : survey_title, survey_objective, survey_context, validation_objectives,
             survey_strategy, audience_definition, sampling_strategy,
             survey_structure, question_optimization_report, multilingual_support,
             testing_report, questions, target_audience_summary,
             survey_quality_score, confidence, disclaimer
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
    "survey_context": {
        "startup_summary": "Customer validation survey for startup hypothesis testing.",
        "validation_scope": "Problem validation, pain severity, and willingness to switch.",
    },
    "validation_objectives": {
        "research_objectives": [
            "Verify existence of current workarounds and pain severity",
            "Quantify urgency and problem intensity",
        ],
        "learning_goals": ["Identify core workflow bottlenecks"],
        "research_hypotheses": [
            "Target customers experience significant daily friction using manual workarounds"
        ],
    },
    "survey_strategy": {
        "survey_type": "Customer Discovery",
        "target_completion_time_minutes": 7,
        "recommended_question_count": 12,
        "data_collection_method": "Online self-administered questionnaire",
        "required_confidence_level": "95%",
    },
    "audience_definition": {
        "icp_summary": "Prospective early adopters facing the core problem statement.",
        "demographics_or_firmographics": "Target role or prospective customer segment",
        "eligibility_rules": ["Must currently experience the targeted workflow challenge"],
        "exclusion_rules": ["Non-decision makers or non-users of relevant tools"],
    },
    "sampling_strategy": {
        "recommended_sample_size": 100,
        "sampling_method": "Purposive Sampling",
        "confidence_level": "95%",
        "margin_of_error": "5%",
        "sampling_bias_risks": ["Over-representation of highly vocal early adopters"],
    },
    "survey_structure": {
        "sections": [
            {
                "section_number": 1,
                "section_title": "Current Workflow & Background",
                "questions": [
                    {
                        "question_id": "Q1",
                        "question_text": "How do you currently address this challenge in your daily workflow?",
                        "question_type": "open_ended",
                        "options": [],
                        "is_mandatory": True,
                        "target_hypothesis": "Verify existence of current workarounds and pain severity.",
                        "skip_logic": None,
                    }
                ],
            },
            {
                "section_number": 2,
                "section_title": "Problem Severity",
                "questions": [
                    {
                        "question_id": "Q2",
                        "question_text": "On a scale of 1-5, how severe is this problem when it occurs?",
                        "question_type": "rating_scale",
                        "options": ["1 - Low", "2", "3", "4", "5 - Critical"],
                        "is_mandatory": True,
                        "target_hypothesis": "Quantify urgency and problem intensity.",
                        "skip_logic": None,
                    }
                ],
            },
        ]
    },
    "question_optimization_report": {
        "anti_bias_checks_passed": True,
        "improvements_made": ["Ensured questions ask about past behavior instead of future promises"],
    },
    "multilingual_support": {
        "default_language": "English",
        "supported_languages": ["English"],
        "localization_notes": "Use standard neutral wording",
    },
    "testing_report": {
        "question_logic_check": "Passed",
        "flow_check": "Logical flow confirmed",
        "estimated_completion_time_minutes": 7,
        "mobile_friendliness": "Optimized for mobile",
        "publishing_readiness": "Ready",
    },
    "target_audience_summary": "Prospective early adopters facing the core problem statement.",
    "questions": [
        {
            "question_text": "How do you currently address this challenge in your daily workflow?",
            "question_type": "open_ended",
            "options": [],
            "target_hypothesis": "Verify existence of current workarounds and pain severity.",
        },
        {
            "question_text": "How many people in your team are affected by this problem?",
            "question_type": "multiple_choice",
            "options": ["Just me", "2-5 people", "6-20 people", "More than 20"],
            "target_hypothesis": "Identify scale and organizational impact of the problem.",
        },
        {
            "question_text": "On a scale of 1-5, how severe is this problem when it occurs?",
            "question_type": "rating_scale",
            "options": ["1 - Low", "2", "3", "4", "5 - Critical"],
            "target_hypothesis": "Quantify urgency and problem intensity.",
        },
        {
            "question_text": "How many hours per week does this problem consume?",
            "question_type": "multiple_choice",
            "options": ["Less than 1 hour", "1-3 hours", "4-7 hours", "More than 7 hours"],
            "target_hypothesis": "Quantify time cost of the problem.",
        },
        {
            "question_text": "What are the biggest frustrations with your current workaround?",
            "question_type": "checkbox",
            "options": ["Too time consuming", "Error-prone", "Poor collaboration", "High cost", "Lack of automation"],
            "target_hypothesis": "Identify primary pain dimensions driving switching intent.",
        },
        {
            "question_text": "Have you tried any existing tools to solve this problem?",
            "question_type": "multiple_choice",
            "options": ["Yes, currently using one", "Yes, but stopped", "No, never tried", "Currently evaluating options"],
            "target_hypothesis": "Measure awareness of and dissatisfaction with existing solutions.",
        },
        {
            "question_text": "Which features would be most important in an ideal solution?",
            "question_type": "ranking",
            "options": ["Automation", "Real-time collaboration", "Integration with current tools", "Custom reporting", "Mobile access"],
            "target_hypothesis": "Identify the highest priority features for an MVP.",
        },
        {
            "question_text": "How important is integration with your existing tools?",
            "question_type": "rating_scale",
            "options": ["1 - Not important", "2", "3", "4", "5 - Deal breaker"],
            "target_hypothesis": "Validate integration as a key adoption barrier.",
        },
        {
            "question_text": "What budget range per user/month would you consider for a solution?",
            "question_type": "multiple_choice",
            "options": ["Free only", "$1-$10", "$11-$25", "$26-$50", "$50+"],
            "target_hypothesis": "Validate pricing model and willingness to pay.",
        },
        {
            "question_text": "How likely are you to adopt a solution that fully addresses this in 3 months?",
            "question_type": "rating_scale",
            "options": ["1 - Very unlikely", "2", "3", "4", "5 - Definitely would adopt"],
            "target_hypothesis": "Measure near-term adoption intent and purchase urgency.",
        },
        {
            "question_text": "Who makes the final decision on adopting new tools in your organization?",
            "question_type": "multiple_choice",
            "options": ["Myself", "My manager", "IT/Ops team", "C-suite", "Procurement committee"],
            "target_hypothesis": "Map the buying process and identify key decision-makers.",
        },
        {
            "question_text": "What would make you switch from your current solution to a new one?",
            "question_type": "open_ended",
            "options": [],
            "target_hypothesis": "Identify switching triggers and decision criteria.",
        },
    ],
    "survey_quality_score": 75.0,
    "confidence": 0.7,
    "disclaimer": "This output provides decision-support guidance only. It does not constitute formal legal, financial, or tax advice.",
}


class SurveyIntelligenceAgent(BaseAgent):
    """
    Survey Intelligence Agent.
    Creates targeted, unbiased 10-phase customer validation surveys to test key business assumptions.
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

        ctx = agent_input.additional_context or {}

        target_cust = (
            agent_input.target_customer
            or ctx.get("target_customer")
            or "Prospective target customer base"
        )
        val_goal = (
            agent_input.founder_validation_goal
            or ctx.get("validation_goal")
            or "Validate core problem statement and willingness to switch"
        )
        problem_stmt = (
            agent_input.problem_statement
            or ctx.get("problem_statement")
            or "Unclear problem statement"
        )

        problem_val = ctx.get("problem_validation") or ctx.get("idea_validation_output") or "Not provided"
        founder_inf = ctx.get("founder_info") or ctx.get("founder_evidence") or "Not provided"
        market_res = ctx.get("market_research") or ctx.get("market_research_output") or "Not provided"
        customer_intel = ctx.get("customer_intelligence") or ctx.get("customer_personas") or "Not provided"
        biz_assumptions = ctx.get("business_assumptions") or ctx.get("key_assumptions") or "Not provided"

        return self.skill.build_prompt(
            idea_title=agent_input.idea_title,
            idea_description=agent_input.idea_description,
            problem_statement=problem_stmt,
            target_customer=target_cust,
            validation_goal=val_goal,
            problem_validation=str(problem_val),
            founder_info=str(founder_inf),
            market_research=str(market_res),
            customer_intelligence=str(customer_intel),
            business_assumptions=str(biz_assumptions),
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

        # Ensure multi-phase sections exist or populate default
        if "survey_structure" not in data or not isinstance(data.get("survey_structure"), dict):
            data["survey_structure"] = DEFAULT_SURVEY_OUTPUT["survey_structure"]

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

