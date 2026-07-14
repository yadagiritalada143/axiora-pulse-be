"""
Result Aggregator
──────────────────────────────────────────────────────────────────────────────
Combines the list of AgentOutputs from the Orchestrator into a single
structured dict that the Validation Engine can score.
"""
import logging
from typing import Any

from app.models.agent_models import AgentOutput, AgentStatus

logger = logging.getLogger(__name__)


class ResultAggregator:
    """
    Takes the raw list of AgentOutputs and returns a unified dict:
      {
        "agent_results":       { agent_name: {score, confidence, data, ...} },
        "total_agents":        int,
        "successful_agents":   int,
        "failed_agents":       int,
        "failed_agent_names":  [str],
      }
    """

    def aggregate(self, agent_outputs: list[AgentOutput]) -> dict[str, Any]:
        successful = [o for o in agent_outputs if o.status == AgentStatus.SUCCESS]
        failed = [o for o in agent_outputs if o.status == AgentStatus.FAILED]
        skipped = [o for o in agent_outputs if o.status == AgentStatus.SKIPPED]

        if failed:
            logger.warning(
                f"[ResultAggregator] {len(failed)} agent(s) failed: "
                f"{[o.agent_name for o in failed]}"
            )

        agent_results: dict[str, Any] = {}
        for output in successful:
            agent_results[output.agent_name] = {
                "score": output.score,
                "confidence": output.confidence,
                "data": output.data or {},
                "model_used": output.model_used,
                "tokens_input": output.tokens_input,
                "tokens_output": output.tokens_output,
                "executed_at": output.executed_at.isoformat(),
            }

        logger.info(
            f"[ResultAggregator] Aggregated {len(successful)} successful, "
            f"{len(failed)} failed, {len(skipped)} skipped"
        )

        return {
            "agent_results": agent_results,
            "total_agents": len(agent_outputs),
            "successful_agents": len(successful),
            "failed_agents": len(failed),
            "failed_agent_names": [o.agent_name for o in failed],
            "skipped_agent_names": [o.agent_name for o in skipped],
        }


# Module-level singleton
result_aggregator = ResultAggregator()
