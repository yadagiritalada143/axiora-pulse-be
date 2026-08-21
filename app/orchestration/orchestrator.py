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
"""
import logging
import uuid
from datetime import datetime
from typing import Any

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
from app.services.research_trace_service import research_trace_service
from app.services.token_tracking_service import token_tracking_service
from app.db.database import AsyncSessionLocal
from app.db.models import Workspace

# ── Agent Registry ─────────────────────────────────────────────────────────────
from app.agents.idea_validation_agent import IdeaValidationAgent
from app.agents.market_research_agent import MarketResearchAgent
from app.agents.survey_intelligence_agent import SurveyIntelligenceAgent

AGENT_REGISTRY: dict[str, type] = {
    "idea_validation_agent": IdeaValidationAgent,
    "market_research_agent": MarketResearchAgent,
    "survey_intelligence_agent": SurveyIntelligenceAgent,
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

            # ── Step 3.5: Initialise research trace for this run ───────────────
            research_trace_service.start_run_trace(run_id)
            research_trace_service.set_context(run_id=run_id)

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
                research_trace_service.set_context(run_id=run_id, agent_name=agent_name)
                agent = agent_class(llm_gateway)
                output = await agent.run(agent_input)
                agent_outputs.append(output)
                if output.data:
                    agent_input.additional_context.update(output.data)
                logger.info(
                    f"[Orchestrator] {agent_name} → status={output.status} "
                    f"score={output.score}"
                )

                # Record token usage for this agent execution
                await self._record_agent_token_usage(
                    request=request,
                    agent_name=agent_name,
                    output=output,
                    llm_gateway=llm_gateway,
                    run_id=run_id,
                )

            if not agent_outputs:
                research_trace_service.end_run_trace(run_id)
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

            # ── Step 7.5: Finalise research traces ─────────────────────────────
            research_trace_service.end_run_trace(run_id)
            trace_snapshot = research_trace_service.get_traces(run_id)

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
                research_queries=trace_snapshot.queries,
                research_sources=trace_snapshot.sources,
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
            research_trace_service.end_run_trace(run_id)
            return self._failed_response(
                run_id=run_id,
                request=request,
                started_at=started_at,
                error="Orchestration failed unexpectedly. Please try again.",
            )

    # ── Helpers ────────────────────────────────────────────────────────────────

    async def _record_agent_token_usage(
        self,
        request: OrchestrationRequest,
        agent_name: str,
        output: Any,
        llm_gateway: Any,
        run_id: str,
    ) -> None:
        """Asynchronously persist token usage for an agent execution."""
        try:
            prompt_tokens = getattr(output, "tokens_input", 0) or 0
            completion_tokens = getattr(output, "tokens_output", 0) or 0
            if prompt_tokens <= 0 and completion_tokens <= 0:
                return

            ws_id_int = int(request.workspace_id) if str(request.workspace_id).isdigit() else None
            user_id = request.user_id

            async with AsyncSessionLocal() as db:
                # If user_id is not directly on request, attempt to resolve from workspace
                if user_id is None and ws_id_int is not None:
                    res = await db.get(Workspace, ws_id_int)
                    if res:
                        user_id = res.user_id

                if user_id is not None:
                    model = getattr(output, "model_used", None) or llm_gateway.get_default_model()
                    provider = llm_gateway.get_provider_name()
                    await token_tracking_service.record_usage(
                        db=db,
                        user_id=user_id,
                        workspace_id=ws_id_int,
                        source="agent_execution",
                        agent_name=agent_name,
                        provider=provider,
                        model=model,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        metadata={
                            "run_id": run_id,
                            "workflow_type": str(request.workflow_type),
                            "agent_status": str(output.status),
                            "score": getattr(output, "score", None),
                        },
                    )
                    await db.commit()
        except Exception as err:
            logger.warning(f"[Orchestrator] Failed to record token usage for agent '{agent_name}': {err}")

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
