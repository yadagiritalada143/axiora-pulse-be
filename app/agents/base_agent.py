"""
Base Agent
──────────────────────────────────────────────────────────────────────────────
Abstract base class that every Axiora Pulse agent must extend.

Standard agent lifecycle (every agent follows this — no exceptions):
  1. Load skill from SkillRegistry
  2. Build prompt using the skill template
  3. Call LLM Gateway (never the provider SDK directly)
  4. Parse raw LLM response
  5. Validate output schema
  6. Apply guardrails
  7. Return structured AgentOutput
"""
import json
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from app.llm.llm_gateway import LLMGateway, LLMRequest
from app.models.agent_models import AgentInput, AgentOutput, AgentStatus
from app.skills.skill_registry import Skill, skill_registry

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base for all Axiora Pulse agents.

    Subclasses must define:
      - agent_name : str       — unique name, used in logs and output
      - skill_name : str       — matches the 'name' field in the skill YAML
      - _build_prompt()        — renders the skill template with agent input
      - _parse_output()        — parses raw LLM text into a structured dict
      - _extract_score()       — returns a float 0–100 from parsed output
    """

    agent_name: str = "base_agent"
    skill_name: str = ""

    def __init__(self, llm_gateway: LLMGateway) -> None:
        self.llm = llm_gateway
        self.skill: Skill | None = None
        self._load_skill()

    # ── Lifecycle hooks (subclasses implement these) ───────────────────────────

    @abstractmethod
    def _build_prompt(self, agent_input: AgentInput) -> str:
        """Render the skill prompt template with the given input."""

    @abstractmethod
    def _parse_output(self, raw_content: str) -> dict[str, Any]:
        """Parse and normalise the raw LLM response string into a dict."""

    @abstractmethod
    def _extract_score(self, parsed_output: dict[str, Any]) -> float:
        """Return a numeric score 0–100 from the parsed output."""

    # ── Main execution entry point ─────────────────────────────────────────────

    async def run(self, agent_input: AgentInput) -> AgentOutput:
        """
        Execute the full agent lifecycle.
        Always returns an AgentOutput — never raises an exception to the caller.
        """
        logger.info(f"[{self.agent_name}] ▶ Starting execution")
        executed_at = datetime.utcnow()

        # ── Step 1: Ensure skill is available ─────────────────────────────────
        if not self.skill:
            return self._failed_output(
                "Skill not loaded. Check that the skill YAML file exists.",
                executed_at=executed_at,
            )

        # ── Step 2: Build prompt ───────────────────────────────────────────────
        try:
            prompt = self._build_prompt(agent_input)
        except Exception as e:
            logger.error(f"[{self.agent_name}] Prompt build failed: {e}")
            return self._failed_output(f"Prompt build error: {e}", executed_at=executed_at)

        # ── Step 3: Call LLM Gateway ───────────────────────────────────────────
        llm_request = LLMRequest(
            system_prompt=(
                f"You are {self.agent_name}, a specialist AI analysis unit "
                f"inside the Axiora Pulse AI Orchestration Engine. "
                f"Your purpose: {self.skill.purpose}"
            ),
            user_prompt=prompt,
            response_format="json",
            temperature=0.3,
            max_tokens=2048,
        )

        try:
            llm_response = await self.llm.complete(llm_request)
        except Exception as e:
            logger.error(f"[{self.agent_name}] LLM gateway call raised: {e}")
            return self._failed_output("LLM call failed unexpectedly.", executed_at=executed_at)

        if not llm_response.success:
            logger.error(f"[{self.agent_name}] LLM returned error: {llm_response.error}")
            return AgentOutput(
                agent_name=self.agent_name,
                status=AgentStatus.FAILED,
                error=llm_response.error or "LLM call failed.",
                model_used=llm_response.model,
                tokens_input=llm_response.tokens_input,
                tokens_output=llm_response.tokens_output,
                executed_at=executed_at,
            )

        # ── Step 4: Parse output ───────────────────────────────────────────────
        try:
            parsed = self._parse_output(llm_response.content)
        except json.JSONDecodeError as e:
            logger.error(f"[{self.agent_name}] JSON parse error: {e}. Raw: {llm_response.content[:200]}")
            return self._failed_output(
                "Could not parse agent response. Please retry.",
                model_used=llm_response.model,
                tokens_input=llm_response.tokens_input,
                tokens_output=llm_response.tokens_output,
                executed_at=executed_at,
            )
        except Exception as e:
            logger.error(f"[{self.agent_name}] Output parse error: {e}")
            return self._failed_output("Output parsing failed.", executed_at=executed_at)

        # ── Step 5: Extract score and confidence ───────────────────────────────
        try:
            score = float(self._extract_score(parsed))
            score = max(0.0, min(100.0, score))
        except Exception:
            score = 50.0  # safe default

        confidence = float(parsed.get("confidence", 0.5))
        confidence = max(0.0, min(1.0, confidence))

        logger.info(
            f"[{self.agent_name}] ✓ Done — score={score:.1f} confidence={confidence:.2f} "
            f"model={llm_response.model} tokens={llm_response.total_tokens}"
        )

        return AgentOutput(
            agent_name=self.agent_name,
            status=AgentStatus.SUCCESS,
            score=score,
            confidence=confidence,
            data=parsed,
            model_used=llm_response.model,
            tokens_input=llm_response.tokens_input,
            tokens_output=llm_response.tokens_output,
            executed_at=executed_at,
        )

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _load_skill(self) -> None:
        if not self.skill_name:
            return
        self.skill = skill_registry.get(self.skill_name)
        if not self.skill:
            raise ValueError(
                f"[{self.agent_name}] Skill '{self.skill_name}' not found in registry. "
                "Ensure the YAML file exists in app/skills/ and is correctly named."
            )
        logger.debug(f"[{self.agent_name}] Skill loaded: {self.skill}")

    def _failed_output(
        self,
        error: str,
        model_used: str = "",
        tokens_input: int = 0,
        tokens_output: int = 0,
        executed_at: datetime | None = None,
    ) -> AgentOutput:
        return AgentOutput(
            agent_name=self.agent_name,
            status=AgentStatus.FAILED,
            error=error,
            model_used=model_used,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            executed_at=executed_at or datetime.utcnow(),
        )
