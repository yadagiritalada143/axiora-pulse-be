"""
Orchestrator
──────────────────────────────────────────────────────────────────────────────
The backend brain of Axiora Pulse.

Responsibilities:
  1. Create orchestration run record
  2. Build agent context (ContextBuilder)
  3. Select agents to run (Planner)
  4. Instantiate and execute each agent (Agent Registry)
  5. Aggregate all outputs (ResultAggregator)
  6. Calculate score and verdict (ValidationEngine)
  7. Return a structured OrchestrationResponse

Adding a new agent:
  → Implement the agent class in app/agents/
  → Register it in AGENT_REGISTRY below
  → Add it to WORKFLOW_AGENT_MAP in planner.py
  → That's it — no other changes needed.
"""
import logging
import uuid
from datetime import datetime

from app.llm.llm_gateway import get_llm_gateway
from app.models.orchestration_models import (
    IdeaInput,
    OrchestrationRequest,
    OrchestrationResponse,
    ValidationResult,
    WorkflowType,
)
from app.orchestration.context_builder import context_builder
from app.orchestration.planner import planner
from app.orchestration.result_aggregator import result_aggregator
from app.orchestration.validation_engine import validation_engine

# ── Agent Registry ─────────────────────────────────────────────────────────────
# Import each agent class and register it here.
# Phase 2+: add market_research_agent, survey_intelligence_agent, etc.
from app.agents.idea_validation_agent import IdeaValidationAgent
from app.agents.market_research_agent import MarketResearchAgent

AGENT_REGISTRY: dict[str, type] = {
    "idea_validation_agent": IdeaValidationAgent,
    "market_research_agent": MarketResearchAgent,
    # "survey_intelligence_agent": SurveyIntelligenceAgent, # Phase 2
    # "gtm_strategy_agent":        GTMStrategyAgent,        # Phase 2
    # "financial_readiness_agent": FinancialReadinessAgent, # Phase 2
}

logger = logging.getLogger(__name__)


class Orchestrator:
    """
    Coordinates the full agentic workflow for a single OrchestrationRequest.
    Returns an OrchestrationResponse regardless of success or failure —
    errors are surfaced in the response, never raised to the caller.
    """

    async def run(self, request: OrchestrationRequest) -> OrchestrationResponse:
        run_id = str(uuid.uuid4())
        started_at = datetime.utcnow()

        logger.info(
            f"[Orchestrator] ▶ Run {run_id[:8]}… | "
            f"workflow={request.workflow_type} | idea='{request.idea.idea_title}'"
        )

        try:
            # ── Step 1: Build agent context ────────────────────────────────────
            agent_input = await context_builder.build_agent_input(request.idea)

            # ── Step 2: Select agents via Planner ──────────────────────────────
            agent_names = planner.plan(request)

            if not agent_names:
                return self._failed_response(
                    run_id=run_id,
                    request=request,
                    started_at=started_at,
                    error=(
                        f"No agents are configured for workflow "
                        f"'{request.workflow_type}'. Check planner.py."
                    ),
                )

            # ── Step 3: Initialise LLM Gateway ────────────────────────────────
            llm_gateway = get_llm_gateway()
            logger.info(
                f"[Orchestrator] LLM provider: {llm_gateway.get_provider_name()} | "
                f"model: {llm_gateway.get_default_model()}"
            )

            # ── Step 4: Execute agents in sequence ─────────────────────────────
            agent_outputs = []
            for agent_name in agent_names:
                agent_class = AGENT_REGISTRY.get(agent_name)
                if not agent_class:
                    logger.warning(
                        f"[Orchestrator] Agent '{agent_name}' is in the plan "
                        "but not registered in AGENT_REGISTRY — skipping."
                    )
                    continue

                logger.info(f"[Orchestrator] Executing: {agent_name}")
                agent = agent_class(llm_gateway)
                output = await agent.run(agent_input)
                agent_outputs.append(output)
                if output.data:
                    agent_input.additional_context.update(output.data)
                logger.info(
                    f"[Orchestrator] {agent_name} → status={output.status} "
                    f"score={output.score}"
                )

            if not agent_outputs:
                return self._failed_response(
                    run_id=run_id,
                    request=request,
                    started_at=started_at,
                    error="All agents were skipped or not registered.",
                )

            # ── Step 5: Aggregate results ──────────────────────────────────────
            aggregated = result_aggregator.aggregate(agent_outputs)

            # ── Step 6: Score and verdict ──────────────────────────────────────
            validation_data = validation_engine.calculate(aggregated)

            # ── Step 7: Build final response ───────────────────────────────────
            completed_at = datetime.utcnow()
            duration_ms = int((completed_at - started_at).total_seconds() * 1000)

            validation_result = ValidationResult(
                idea_id=request.idea_id,
                orchestration_run_id=run_id,
                validation_score=validation_data["validation_score"],
                confidence_rating=validation_data["confidence_rating"],
                verdict=validation_data["verdict"],
                strengths=validation_data["strengths"],
                risks=validation_data["risks"],
                assumptions=validation_data["assumptions"],
                recommendations=validation_data["recommendations"],
                agent_results=aggregated["agent_results"],
                mentor_summary=validation_data["mentor_summary"],
                inferred_idea=IdeaInput(
                    idea_title=agent_input.idea_title,
                    idea_description=agent_input.idea_description,
                    problem_statement=agent_input.problem_statement,
                    founder_evidence=agent_input.founder_evidence,
                ),
            )

            logger.info(
                f"[Orchestrator] ✓ Run {run_id[:8]}… complete | "
                f"score={validation_data['validation_score']} | "
                f"verdict={validation_data['verdict']} | {duration_ms}ms"
            )

            return OrchestrationResponse(
                run_id=run_id,
                workspace_id=request.workspace_id,
                idea_id=request.idea_id,
                workflow_type=request.workflow_type,
                status="success",
                result=validation_result,
                started_at=started_at,
                completed_at=completed_at,
            )

        except Exception as e:
            logger.error(
                f"[Orchestrator] ✗ Run {run_id[:8]}… failed with unexpected error: {e}",
                exc_info=True,
            )
            return self._failed_response(
                run_id=run_id,
                request=request,
                started_at=started_at,
                error="Orchestration failed unexpectedly. Please try again.",
            )

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _failed_response(
        run_id: str,
        request: OrchestrationRequest,
        started_at: datetime,
        error: str,
    ) -> OrchestrationResponse:
        return OrchestrationResponse(
            run_id=run_id,
            workspace_id=request.workspace_id,
            idea_id=request.idea_id,
            workflow_type=request.workflow_type,
            status="failed",
            error=error,
            started_at=started_at,
            completed_at=datetime.utcnow(),
        )


# Module-level singleton
orchestrator = Orchestrator()
