"""
AI Mentor API Routes  —  /api/v1/mentor
──────────────────────────────────────────────────────────────────────────────
Handles conversation with the founder-facing AI Mentor.
Exposes an endpoint to chat.

Health checks are handled globally at GET /health (see main.py).
"""
import logging
from typing import Any, Dict, Optional
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.services.mentor_service import mentor_store, mentor_service, MentorSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mentor", tags=["AI Mentor"])


# ── API Models ─────────────────────────────────────────────────────────────────

class MentorChatRequest(BaseModel):
    message: str
    session_id: str = "default-session"
    workspace_id: Optional[str] = None


class MentorChatResponse(BaseModel):
    reply: str
    session_id: str
    workspace_id: str
    state: str
    idea: Dict[str, Any]
    validation_result: Optional[Dict[str, Any]] = None


# ── API Endpoints ──────────────────────────────────────────────────────────────

@router.post(
    "/chat",
    response_model=MentorChatResponse,
    summary="Send a message to the AI Mentor",
    description="Processes the message, updates the extracted idea context, and returns the mentor's response.",
)
async def mentor_chat(request: MentorChatRequest) -> MentorChatResponse:
    logger.info(f"[Mentor API] Chat request in session: {request.session_id}")
    
    # 1. Fetch or create session
    session: MentorSession = mentor_store.get_or_create(
        session_id=request.session_id,
        workspace_id=request.workspace_id
    )

    # 2. Process message using the mentor service
    try:
        updated_session = await mentor_service.process_message(session, request.message)
    except Exception as e:
        logger.error(f"[Mentor API] Error processing message: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing your message."
        )

    # 3. Get last assistant reply from history
    assistant_reply = "I'm listening. Tell me more!"
    if updated_session.conversation_history:
        for msg in reversed(updated_session.conversation_history):
            if msg.get("role") == "assistant":
                assistant_reply = msg.get("content", "")
                break

    return MentorChatResponse(
        reply=assistant_reply,
        session_id=updated_session.session_id,
        workspace_id=updated_session.workspace_id,
        state=updated_session.state,
        idea=updated_session.idea,
        validation_result=updated_session.validation_result
    )

