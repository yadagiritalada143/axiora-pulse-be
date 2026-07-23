"""
Context Builder
──────────────────────────────────────────────────────────────────────────────
Assembles the AgentInput that every agent receives from the raw
OrchestrationRequest. In Phase 1 this is a simple mapping.
Phase 2+ will enrich this with workspace history, prior agent outputs,
survey data, and founder profile from the database.
"""
import json
import logging
import re
from typing import Optional

from app.llm.llm_gateway import get_llm_gateway, LLMRequest
from app.models.agent_models import AgentInput
from app.models.orchestration_models import IdeaInput

logger = logging.getLogger(__name__)

# Prompt specifications for field inference
INFER_FIELDS_SYSTEM_PROMPT = """
You are an expert startup analyst inside the Axiora Pulse Orchestration Engine.
Your task is to analyze a startup idea's title, description, and problem statement, and infer/refine any missing or placeholder fields.

Analyze the provided inputs and generate:
- target_customer: Who the target audience or customer persona is. Be specific and descriptive.
- industry: The sector or industry this startup operates in (e.g., FinTech, EdTech, Healthcare, E-commerce, B2B SaaS, Creator Economy, etc.).
- geography: The target geographical market (e.g., Global, North America, India, Europe, local city, etc.). If not specified, default to a reasonable target market or "Global".
- founder_validation_goal: A clear, actionable validation goal showing what the founder wants to learn or validate (e.g., "Verify if college students are willing to pay for peer tutoring", "Confirm if small businesses face cash flow delays", etc.).

Return ONLY a raw JSON object with these keys: target_customer, industry, geography, founder_validation_goal.
Do not include any other text, markdown, or code blocks.
"""


class ContextBuilder:
    """
    Converts an IdeaInput (from the API request) into an AgentInput
    (the standardised payload every agent understands).

    Phase 2 extension points (marked with TODO):
      - Fetch prior agent outputs from DB
      - Attach survey response summary
      - Attach workspace-level founder context
    """

    async def build_agent_input(self, idea: IdeaInput) -> AgentInput:
        logger.debug(f"[ContextBuilder] Building context for idea: '{idea.idea_title}'")

        logger.info("[ContextBuilder] Running LLM field inference to deduce target_customer, industry, geography, and validation goal...")
        user_prompt = f"""Analyze the following startup idea:
Title: {idea.idea_title}
Description: {idea.idea_description}
Problem Statement: {idea.problem_statement}

Please infer and provide realistic, specific and professional values for:
- target_customer: Who the target audience or customer persona is. Be specific.
- industry: The sector or industry this startup operates in.
- geography: The target geographical market. If not specified, default to a reasonable target market or "Global".
- founder_validation_goal: A clear, actionable validation goal showing what the founder wants to learn or validate.
"""
        inferred = {}
        try:
            llm = get_llm_gateway()
            req = LLMRequest(
                system_prompt=INFER_FIELDS_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                response_format="json",
                temperature=0.2
            )
            res = await llm.complete(req)
            if res.success and res.content:
                # Clean markdown wrappers if any
                cleaned_content = res.content.strip()
                match = re.search(r"\{.*\}", cleaned_content, re.DOTALL)
                if match:
                    cleaned_content = match.group()
                inferred = json.loads(cleaned_content)
                logger.info(f"[ContextBuilder] Inferred fields successfully: {inferred}")
        except Exception as e:
            logger.warning(f"[ContextBuilder] Field inference failed: {e}. Using fallback defaults.")

        target_customer = inferred.get("target_customer") or "General audience"
        industry = inferred.get("industry") or "general"
        founder_validation_goal = inferred.get("founder_validation_goal") or "validate my idea"
        geography = inferred.get("geography") or "global"

        return AgentInput(
            idea_title=idea.idea_title,
            idea_description=idea.idea_description,
            problem_statement=idea.problem_statement,
            target_customer=target_customer.strip(),
            industry=industry.strip(),
            founder_validation_goal=founder_validation_goal.strip(),
            geography=geography.strip(),
            # TODO Phase 2: additional_context = await db.fetch_workspace_context(workspace_id)
        )


# Module-level singleton
context_builder = ContextBuilder()
