import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import User
from app.models.questionnaire_models import (
    InteractiveQuestionnaireResponse,
    SubmitAnswersRequestItem,
    SubmitAnswersResponse,
)
from app.services.questionnaire_service import questionnaire_service

router = APIRouter(prefix="/questionnaire", tags=["Questionnaire"])
logger = logging.getLogger(__name__)


@router.get(
    "/questions",
    response_model=list[InteractiveQuestionnaireResponse],
    status_code=status.HTTP_200_OK,
    summary="List all questionnaire questions",
    description="Returns all active questionnaire questions ordered by ID ascending.",
)
async def get_questions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[InteractiveQuestionnaireResponse]:
    logger.info("Listing questionnaire questions for user_id=%s", current_user.id)
    return await questionnaire_service.list_questions(db)


@router.post(
    "/submit-answers",
    response_model=SubmitAnswersResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit questionnaire answers",
    description="Persists a user's questionnaire responses in a transactional workflow.",
)
async def submit_answers(
    payload: list[SubmitAnswersRequestItem],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubmitAnswersResponse:
    logger.info(
        "Submitting questionnaire answers for user_id=%s with %s item(s)",
        current_user.id,
        len(payload),
    )
    try:
        return await questionnaire_service.submit_answers(payload, current_user, db)
    except Exception:
        logger.exception("Questionnaire answer submission failed for user_id=%s", current_user.id)
        raise
