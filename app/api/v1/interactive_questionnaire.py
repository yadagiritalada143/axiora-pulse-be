import logging

from fastapi import APIRouter, Depends, Path, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import User
from app.models.questionnaire_models import (
    DeleteQuestionResponse,
    InteractiveQuestionnaireResponse,
    SubmitAnswersRequestItem,
    SubmitAnswersResponse,
    SubmitQuestionRequest,
    UpdateQuestionRequest,
)
from app.services.questionnaire_service import questionnaire_service

router = APIRouter(prefix="/admin", tags=["Interactive Questionnaire"])
logger = logging.getLogger(__name__)


@router.post(
    "/questionnaire/create-question",
    response_model=InteractiveQuestionnaireResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new questionnaire question",
    description="Allows administrators to create a new interactive questionnaire question item.",
)
async def create_question(
    request: Request,
    payload: SubmitQuestionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InteractiveQuestionnaireResponse:
    return await questionnaire_service.create_question(payload, current_user, db)


@router.get(
    "/questionnaire/questions",
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
    "/questionnaire/submit-answers",
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


@router.put(
    "/questionnaire/update-question/{question_id}",
    response_model=InteractiveQuestionnaireResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a questionnaire question",
    description="Allows administrators to update an existing interactive questionnaire question item.",
)
async def update_question(
    payload: UpdateQuestionRequest,
    question_id: int = Path(..., ge=1, description="ID of the questionnaire question to update"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> InteractiveQuestionnaireResponse:
    return await questionnaire_service.update_question(question_id, payload, current_user, db)


@router.delete(
    "/questionnaire/delete-question/{question_id}",
    response_model=DeleteQuestionResponse,
    status_code=status.HTTP_200_OK,
    summary="Delete a questionnaire question",
    description="Allows administrators to delete an interactive questionnaire question item.",
)
async def delete_question(
    question_id: int = Path(..., ge=1, description="ID of the questionnaire question to delete"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DeleteQuestionResponse:
    return await questionnaire_service.delete_question(question_id, current_user, db)
