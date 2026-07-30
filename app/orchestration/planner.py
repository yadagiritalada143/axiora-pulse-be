"""
Planner
──────────────────────────────────────────────────────────────────────────────
Decides WHICH agents to run based on the requested workflow type.
"""
import logging

from app.models.orchestration_models import OrchestrationRequest, WorkflowType

logger = logging.getLogger(__name__)


# ── Workflow → Agent mapping ───────────────────────────────────────────────────

WORKFLOW_AGENT_MAP: dict[WorkflowType, list[str]] = {
    WorkflowType.IDEA_VALIDATION: [
        "idea_validation_agent",
        "market_research_agent",
        "survey_intelligence_agent",
    ],
    WorkflowType.SURVEY_GENERATION: [
        "survey_intelligence_agent",
    ],
    WorkflowType.SURVEY_ANALYTICS: [
        "survey_intelligence_agent",
    ],
    WorkflowType.REPORT_GENERATION: [
        # Handled by the Report Engine
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
