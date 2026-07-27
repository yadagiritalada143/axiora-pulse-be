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
- industry: The sector or industry this startup operates in (e.g., FinTech, EdTech, Healthcare, E-commerce, B2B SaaS, Creator Economy, etc.).
- geography: The target geographical market (e.g., Global, North America, India, Europe, local city, etc.). If not specified, default to a reasonable target market or "Global".
- business_type: The primary business model type. Choose ONE of: "B2B" (sells to businesses), "B2C" (sells to consumers), "B2B2C" (sells to businesses who serve consumers), or "Unclear" if insufficient information.
- founder_validation_goal: A clear, actionable validation goal showing what the founder wants to learn or validate (e.g., "Verify if college students are willing to pay for peer tutoring", "Confirm if small businesses face cash flow delays", etc.).

Return ONLY a raw JSON object with these keys: industry, geography, business_type, founder_validation_goal.
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

        logger.info("[ContextBuilder] Running LLM field inference to deduce industry, geography, business_type, and validation goal...")
        user_prompt = f"""Analyze the following startup idea:
Title: {idea.idea_title}
Description: {idea.idea_description}
Problem Statement: {idea.problem_statement}

Please infer and provide realistic, specific and professional values for:
- industry: The sector or industry this startup operates in.
- geography: The target geographical market. If not specified, default to a reasonable target market or "Global".
- business_type: Is this a B2B, B2C, or B2B2C business? Return one of: B2B, B2C, B2B2C, or Unclear.
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

        industry = inferred.get("industry") or "general"
        founder_validation_goal = inferred.get("founder_validation_goal") or "validate my idea"
        geography = inferred.get("geography") or "global"
        raw_bt = inferred.get("business_type", "Unclear") or "Unclear"
        business_type = raw_bt if raw_bt in ("B2B", "B2C", "B2B2C") else "Unclear"

        return AgentInput(
            idea_title=idea.idea_title,
            idea_description=idea.idea_description,
            problem_statement=idea.problem_statement,
            industry=industry.strip(),
            business_type=business_type,
            founder_validation_goal=founder_validation_goal.strip(),
            geography=geography.strip(),
            founder_evidence=idea.founder_evidence,
            # TODO Phase 2: additional_context = await db.fetch_workspace_context(workspace_id)
        )


# Module-level singleton
context_builder = ContextBuilder()
