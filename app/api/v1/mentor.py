"""
AI Mentor API Routes  —  /api/v1/mentor
──────────────────────────────────────────────────────────────────────────────
Handles conversation with the founder-facing AI Mentor.
Exposes an endpoint to chat.

Health checks are handled globally at GET /health (see main.py).
"""
import logging
import uuid
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import MentorSessionORM
from app.services.mentor_service import mentor_service, MentorSession

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
async def mentor_chat(
    request: MentorChatRequest,
    db: AsyncSession = Depends(get_db),
) -> MentorChatResponse:
    logger.info(f"[Mentor API] Chat request in session: {request.session_id}")
    
    # 1. Fetch or create session from database
    result = await db.execute(
        select(MentorSessionORM).where(MentorSessionORM.session_id == request.session_id)
    )
    orm_session = result.scalar_one_or_none()

    if not orm_session:
        w_id = request.workspace_id or f"ws-{uuid.uuid4().hex[:8]}"
        orm_session = MentorSessionORM(
            session_id=request.session_id,
            workspace_id=w_id,
            state="GATHERING_INFO",
            idea={
                "idea_title": None,
                "idea_description": None,
                "problem_statement": None,
                "target_customer": None,
                "industry": "general",
                "founder_validation_goal": "validate my idea",
                "geography": "global"
            },
            conversation_history=[],
            validation_result=None
        )
        db.add(orm_session)
        await db.commit()
        await db.refresh(orm_session)
        logger.info(f"[Mentor API] Created new session in DB: {request.session_id} in workspace: {w_id}")

    # Convert ORM model to Pydantic schema for the service
    session = MentorSession(
        session_id=orm_session.session_id,
        workspace_id=orm_session.workspace_id,
        state=orm_session.state,
        idea=orm_session.idea,
        conversation_history=orm_session.conversation_history,
        validation_result=orm_session.validation_result
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

    # 3. Save updated session state back to database
    orm_session.state = updated_session.state
    orm_session.idea = updated_session.idea
    orm_session.conversation_history = list(updated_session.conversation_history)
    orm_session.validation_result = updated_session.validation_result

    await db.commit()

    # 4. Get last assistant reply from history
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


@router.get(
    "/session/{session_id}",
    response_model=MentorSession,
    summary="Get an existing AI Mentor session",
    description="Retrieves the session state, extracted idea context, and conversation history.",
)
async def get_mentor_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> MentorSession:
    logger.info(f"[Mentor API] Get session request: {session_id}")
    result = await db.execute(
        select(MentorSessionORM).where(MentorSessionORM.session_id == session_id)
    )
    orm_session = result.scalar_one_or_none()
    if not orm_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mentor session {session_id} not found."
        )
    
    return MentorSession(
        session_id=orm_session.session_id,
        workspace_id=orm_session.workspace_id,
        state=orm_session.state,
        idea=orm_session.idea,
        conversation_history=orm_session.conversation_history,
        validation_result=orm_session.validation_result
    )


@router.post(
    "/reset/{session_id}",
    response_model=MentorChatResponse,
    summary="Reset an existing AI Mentor session",
    description="Resets the session state, clearing the conversation history and extracted idea details.",
)
async def reset_mentor_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> MentorChatResponse:
    logger.info(f"[Mentor API] Reset session request: {session_id}")
    result = await db.execute(
        select(MentorSessionORM).where(MentorSessionORM.session_id == session_id)
    )
    orm_session = result.scalar_one_or_none()
    
    default_idea = {
        "idea_title": None,
        "idea_description": None,
        "problem_statement": None,
        "target_customer": None,
        "industry": "general",
        "founder_validation_goal": "validate my idea",
        "geography": "global"
    }

    if orm_session:
        orm_session.state = "GATHERING_INFO"
        orm_session.idea = default_idea
        orm_session.conversation_history = []
        orm_session.validation_result = None
        await db.commit()
    else:
        orm_session = MentorSessionORM(
            session_id=session_id,
            workspace_id=f"ws-{uuid.uuid4().hex[:8]}",
            state="GATHERING_INFO",
            idea=default_idea,
            conversation_history=[],
            validation_result=None
        )
        db.add(orm_session)
        await db.commit()
        await db.refresh(orm_session)

    return MentorChatResponse(
        reply="Hello! I'm your AI Mentor. Tell me about your startup idea to get started.",
        session_id=orm_session.session_id,
        workspace_id=orm_session.workspace_id,
        state=orm_session.state,
        idea=orm_session.idea,
        validation_result=orm_session.validation_result
    )



