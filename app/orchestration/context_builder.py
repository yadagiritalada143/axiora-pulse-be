"""
Context Builder
──────────────────────────────────────────────────────────────────────────────
Assembles the AgentInput that every agent receives from the raw
OrchestrationRequest. In Phase 1 this is a simple mapping.
Phase 2+ will enrich this with workspace history, prior agent outputs,
survey data, and founder profile from the database.
"""
import logging

from app.models.agent_models import AgentInput
from app.models.orchestration_models import IdeaInput

logger = logging.getLogger(__name__)


class ContextBuilder:
    """
    Converts an IdeaInput (from the API request) into an AgentInput
    (the standardised payload every agent understands).

    Phase 2 extension points (marked with TODO):
      - Fetch prior agent outputs from DB
      - Attach survey response summary
      - Attach workspace-level founder context
    """

    def build_agent_input(self, idea: IdeaInput) -> AgentInput:
        logger.debug(f"[ContextBuilder] Building context for idea: '{idea.idea_title}'")
        return AgentInput(
            idea_title=idea.idea_title,
            idea_description=idea.idea_description,
            problem_statement=idea.problem_statement,
            target_customer=idea.target_customer,
            industry=idea.industry,
            founder_validation_goal=idea.founder_validation_goal,
            geography=idea.geography,
            # TODO Phase 2: additional_context = await db.fetch_workspace_context(workspace_id)
        )


# Module-level singleton
context_builder = ContextBuilder()
