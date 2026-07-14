"""
Planner
──────────────────────────────────────────────────────────────────────────────
Decides WHICH agents to run based on the requested workflow type.

Phase 1: Only idea_validation_agent is active.
Phase 2+: Uncomment agents as they are implemented.
"""
import logging

from app.models.orchestration_models import OrchestrationRequest, WorkflowType

logger = logging.getLogger(__name__)


# ── Workflow → Agent mapping ───────────────────────────────────────────────────
# Agents are executed in the order listed.
# Add new agents here as they are built — no changes needed elsewhere.

WORKFLOW_AGENT_MAP: dict[WorkflowType, list[str]] = {
    WorkflowType.IDEA_VALIDATION: [
        "idea_validation_agent",
        # Phase 2 — uncomment when implemented:
        # "market_research_agent",
        # "survey_intelligence_agent",
        # "gtm_strategy_agent",
        # "financial_readiness_agent",
    ],
    WorkflowType.SURVEY_GENERATION: [
        # "survey_intelligence_agent",   # Phase 2
    ],
    WorkflowType.SURVEY_ANALYTICS: [
        # "survey_intelligence_agent",   # Phase 2
    ],
    WorkflowType.REPORT_GENERATION: [
        # Handled by the Report Engine, not agents
    ],
}


class Planner:
    """
    Selects the ordered list of agent names to run
    for a given orchestration request.
    """

    def plan(self, request: OrchestrationRequest) -> list[str]:
        workflow = request.workflow_type
        agents = WORKFLOW_AGENT_MAP.get(workflow, [])

        if not agents:
            logger.warning(
                f"[Planner] No agents configured for workflow '{workflow}'. "
                "Check WORKFLOW_AGENT_MAP."
            )
        else:
            logger.info(f"[Planner] Workflow '{workflow}' → agents: {agents}")

        return agents


# Module-level singleton
planner = Planner()
