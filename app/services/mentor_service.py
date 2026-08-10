import json
import logging
import re
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.llm.llm_gateway import get_llm_gateway, LLMRequest
from app.models.orchestration_models import OrchestrationRequest, IdeaInput, WorkflowType
from app.orchestration.orchestrator import orchestrator
from app.skills.skill_registry import skill_registry

logger = logging.getLogger(__name__)

# ── Workspace State Models ───────────────────────────────────────────────────

class WorkspaceMentorState(BaseModel):
    workspace_id: str
    state: str = "GATHERING_INFO"  # GATHERING_INFO | READY_TO_VALIDATE | VALIDATING | VALIDATED
    idea: Dict[str, Any] = Field(default_factory=lambda: {
        "idea_title": None,
        "idea_description": None,
        "problem_statement": None,
        "industry": "general",
        "founder_validation_goal": "validate my idea",
        "geography": "global"
    })
    conversation_history: List[Dict[str, str]] = Field(default_factory=list)
    validation_result: Optional[Dict[str, Any]] = None


# Alias for backward compatibility
MentorSession = WorkspaceMentorState


# ── LLM Prompts ────────────────────────────────────────────────────────────────

EXTRACT_SYSTEM_PROMPT = """
You are a structured data extractor inside the Axiora Pulse AI Mentor system.
Your task is to analyze the conversation history between a founder and an AI mentor, and extract/update the founder's startup idea details.

Return ONLY a raw JSON object containing these keys:
- idea_title: A short, catchy name/title for the venture (string or null)
- idea_description: Clear description of what the venture does (string or null)
- problem_statement: The specific customer problem/pain point solved (string or null)
- industry: Sector or industry (string, default "general")
- geography: Target market region (string, default "global")
- founder_validation_goal: What the founder wants to learn from validation (string, default "validate my idea")

Guidelines:
1. Do NOT guess or invent details. Only extract what the user has explicitly stated.
2. If a field was extracted previously and the user hasn't modified it, keep it.
3. Return raw JSON ONLY. No markdown formatting like ```json ... ```. No extra text.
"""

# ── Dynamic workspace state block (appended to skill knowledge base) ─────────────

_WORKSPACE_STATE_TEMPLATE = """

══════════════════════════════════════════════════════
CURRENT WORKSPACE CONTEXT
══════════════════════════════════════════════════════

Workspace ID: {workspace_id}
Current Workflow State: {state}
Extracted Idea details: {idea_json}
Missing required fields to run validation: {missing_fields}

State-Specific Instructions:
1. If state is GATHERING_INFO:
   - Ask clarifying, targeted questions to help the founder fill in the missing fields: {missing_fields}.
   - Ask only ONE or TWO clear questions at a time. Keep it conversational.
   - If they gave you a vague description, help them expand it.
   - Provide a useful insight after every two or three questions.
   - Follow the progressive disclosure rules from your knowledge base.
2. If state is READY_TO_VALIDATE:
   - Summarize the idea you've understood based on the extracted fields.
   - Explain that you are ready to trigger the AI Orchestration validation analysis.
   - Tell them they can click the "Run Validation" button on the dashboard or tell you "Run validation analysis".
3. If state is VALIDATING:
   - Let the user know the validation engine is processing their idea.
4. If state is VALIDATED:
   - Comment on the validation run result.
   - Summarize the final score ({validation_score}/100) and the verdict ({validation_verdict}).
   - Highlight the main strengths and the critical risks.
   - Give actionable advice on what they should address next.
   - Produce a practical 7-day action plan when appropriate.

Remember: Follow your complete knowledge base above for behaviour, response format,
questioning style, devil's advocate protocol, and all guardrails.
"""


def _build_mentor_system_prompt(
    workspace_id: str,
    state: str,
    idea_json: str,
    missing_fields: str,
    validation_score: float = 0.0,
    validation_verdict: str = "N/A",
) -> str:
    """Build the full mentor system prompt by combining the core mentor specification,
    the specific idea validation mentor subpart, and the dynamic workspace state."""
    core_skill = skill_registry.get("ai_mentor_core_skill")
    val_skill = skill_registry.get("ai_idea_validation_mentor_skill")

    parts = []

    if core_skill and core_skill.prompt_template:
        parts.append(core_skill.prompt_template)
        logger.info("[MentorService] Loaded ai_mentor_core_skill (%d chars)", len(core_skill.prompt_template))

    if val_skill and val_skill.prompt_template:
        parts.append(val_skill.prompt_template)
        logger.info("[MentorService] Loaded ai_idea_validation_mentor_skill subpart (%d chars)", len(val_skill.prompt_template))

    if not parts:
        logger.warning("[MentorService] Mentor skills not found — using minimal fallback prompt")
        knowledge_base = (
            "You are the Axiora Pulse AI Mentor & Co-Founder.\n"
            "Help the founder clarify, challenge, evaluate and validate their business idea.\n"
            "Be supportive, direct, evidence-driven and politely firm.\n"
            "Never guarantee success or give legal, tax or investment advice.\n"
        )
    else:
        knowledge_base = "\n\n".join(parts)

    # Append the dynamic workspace context
    workspace_block = _WORKSPACE_STATE_TEMPLATE.format(
        workspace_id=workspace_id,
        state=state,
        idea_json=idea_json,
        missing_fields=missing_fields,
        validation_score=validation_score,
        validation_verdict=validation_verdict,
    )

    return knowledge_base + workspace_block


# ── Service Implementation ─────────────────────────────────────────────────────

from app.models.workspace_models import AttachmentInput
from app.services.attachment_processor import attachment_processor

class MentorService:
    """Manages workspace-scoped dialogue state and LLM extraction/generation loop."""

    def __init__(self):
        self._llm = None  # Lazy-initialized on first use to avoid startup crashes

    @property
    def llm(self):
        """Lazily resolve the LLM gateway on first access."""
        if self._llm is None:
            self._llm = get_llm_gateway()
        return self._llm

    async def process_message(
        self,
        state: WorkspaceMentorState,
        user_message: str,
        attachments: Optional[List[AttachmentInput]] = None,
    ) -> WorkspaceMentorState:
        # Process incoming attachments (PDFs via pdfplumber, Docs, Links, Images)
        processed_attachments, attachment_text_context, image_data_uris = (
            await attachment_processor.process_attachments(
                attachments or [], workspace_id=state.workspace_id
            )
        )

        # Build full content for user message including attachment context
        full_content = user_message
        if attachment_text_context:
            full_content = f"{user_message}\n\n[Attached Information Context]:\n{attachment_text_context}"

        # Create user message dict for conversation history
        user_msg_record: Dict[str, Any] = {"role": "user", "content": full_content}
        if processed_attachments:
            user_msg_record["attachments"] = [p.model_dump() for p in processed_attachments]

        state.conversation_history.append(user_msg_record)

        # Check for system trigger or manual validation command in text
        is_trigger_command = "[TRIGGER_VALIDATION]" in user_message or user_message.lower().strip() in (
            "run validation", "run validation analysis", "validate", "validate idea", "start validation"
        )


        if is_trigger_command and state.state == "READY_TO_VALIDATE":
            state.state = "VALIDATING"
            logger.info(f"[MentorService] State GATHERING_INFO -> VALIDATING for workspace {state.workspace_id}")
            
            try:
                # Prepare and trigger orchestration
                idea_input = IdeaInput(
                    idea_title=state.idea.get("idea_title") or "Unnamed Venture",
                    idea_description=state.idea.get("idea_description") or "No description provided.",
                    problem_statement=state.idea.get("problem_statement") or "No problem statement.",
                )

                request = OrchestrationRequest(
                    workspace_id=state.workspace_id,
                    idea_id=f"idea-{uuid.uuid4().hex[:8]}",
                    workflow_type=WorkflowType.IDEA_VALIDATION,
                    idea=idea_input
                )

                orchestrator_resp = await orchestrator.run(request)
                if orchestrator_resp.status == "success" and orchestrator_resp.result:
                    state.validation_result = json.loads(orchestrator_resp.result.json())
                    state.state = "VALIDATED"
                else:
                    state.state = "READY_TO_VALIDATE"
                    state.conversation_history.append({
                        "role": "assistant",
                        "content": f"I tried to run the validation analysis, but the orchestrator returned an error: {orchestrator_resp.error or 'Unknown failure'}. Let's try again when you are ready."
                    })
                    return state

            except Exception as e:
                logger.error(f"[MentorService] Orchestration run crashed: {e}", exc_info=True)
                state.state = "READY_TO_VALIDATE"
                state.conversation_history.append({
                    "role": "assistant",
                    "content": "I encountered an unexpected error running the validation engine. Let's try triggering it again."
                })
                return state

        # If we are gathering info, run the Information Extractor first
        if state.state == "GATHERING_INFO":
            await self._run_extraction(state)

        # Generate conversational response
        await self._generate_mentor_reply(state, image_data_uris=image_data_uris)
        return state

    async def _run_extraction(self, state: WorkspaceMentorState) -> None:
        """Helper to scan conversation history and extract idea details."""
        history_str = ""
        for msg in state.conversation_history[-6:]:  # focus on recent history for context
            history_str += f"{msg['role'].capitalize()}: {msg['content']}\n"

        prompt = f"Existing Idea Context:\n{json.dumps(state.idea, indent=2)}\n\nConversation History:\n{history_str}\n"

        try:
            req = LLMRequest(
                system_prompt=EXTRACT_SYSTEM_PROMPT,
                user_prompt=prompt,
                response_format="json",
                temperature=0.1
            )
            res = await self.llm.complete(req)
            if res.success and res.content:
                # Parse JSON
                cleaned_content = self._clean_json_str(res.content)
                parsed = json.loads(cleaned_content)
                
                # Merge parsed values back into state.idea (only non-null fields)
                for k, v in parsed.items():
                    if v is not None and v != "":
                        state.idea[k] = v

                logger.info(f"[MentorService] Workspace '{state.workspace_id}' Idea updated: {state.idea}")

                # Programmatic check of required fields
                required = ["idea_title", "idea_description", "problem_statement"]
                missing = [f for f in required if not state.idea.get(f)]
                if not missing:
                    state.state = "READY_TO_VALIDATE"
                    logger.info(f"[MentorService] All required fields satisfied for workspace '{state.workspace_id}'! State -> READY_TO_VALIDATE")

        except Exception as e:
            logger.warning(f"[MentorService] Extraction step failed: {e}. Continuing conversation without it.")

    async def _generate_mentor_reply(
        self,
        state: WorkspaceMentorState,
        image_data_uris: Optional[List[str]] = None,
    ) -> None:
        """Call LLM with current workspace state to write assistant response."""
        # Find missing required fields
        required = ["idea_title", "idea_description", "problem_statement"]
        missing = [f.replace("_", " ").title() for f in required if not state.idea.get(f)]

        # Get validation context if we just validated
        score = 0.0
        verdict = "N/A"
        if state.state == "VALIDATED" and state.validation_result:
            score = state.validation_result.get("validation_score", 0.0)
            verdict = str(state.validation_result.get("verdict", "hold")).upper()

        sys_prompt = _build_mentor_system_prompt(
            workspace_id=state.workspace_id,
            state=state.state,
            idea_json=json.dumps(state.idea, indent=2),
            missing_fields=", ".join(missing) if missing else "None",
            validation_score=score,
            validation_verdict=verdict,
        )

        # Build prompt using chat messages
        user_prompt = "Generate the next mentor message. Here is the recent chat history:\n"
        for msg in state.conversation_history[-10:]:
            user_prompt += f"{msg['role'].capitalize()}: {msg['content']}\n"
        user_prompt += "Assistant:"

        try:
            req = LLMRequest(
                system_prompt=sys_prompt,
                user_prompt=user_prompt,
                temperature=0.3,
                images=image_data_uris,
            )
            res = await self.llm.complete(req)

            if res.success and res.content:
                reply = res.content.strip()
                # Clean prefix "Assistant:" if model output it
                if reply.startswith("Assistant:"):
                    reply = reply[len("Assistant:"):].strip()
                state.conversation_history.append({"role": "assistant", "content": reply})
            else:
                state.conversation_history.append({
                    "role": "assistant",
                    "content": "I'm here! Tell me more about your startup idea, and we can validate it together."
                })
        except Exception as e:
            logger.error(f"[MentorService] Failed to generate mentor response: {e}")
            state.conversation_history.append({
                "role": "assistant",
                "content": "I'm having trouble connecting to my brain right now. Can you try again?"
            })

    def _clean_json_str(self, text: str) -> str:
        """Strip markdown wrapping (e.g. ```json ... ```) to extract raw JSON block."""
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return match.group()
        return text


# Global singleton service
mentor_service = MentorService()
