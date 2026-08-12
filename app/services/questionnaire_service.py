import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuthActions, InteractiveQuestionnaire, User, UserInteractiveQuestionnaire
from app.models.questionnaire_models import (
    DeleteQuestionResponse,
    InteractiveQuestionnaireResponse,
    SubmitAnswersRequestItem,
    SubmitAnswersResponse,
    SubmitQuestionRequest,
    UpdateQuestionRequest,
)

logger = logging.getLogger(__name__)


class QuestionnaireService:
    async def list_questions(self, db: AsyncSession) -> list[InteractiveQuestionnaireResponse]:
        """Retrieve all questionnaire questions ordered by id ascending."""
        result = await db.execute(
            select(InteractiveQuestionnaire).order_by(InteractiveQuestionnaire.id.asc())
        )
        questions = result.scalars().all()
        logger.info("Fetched %s questionnaire questions", len(questions))
        return [InteractiveQuestionnaireResponse.model_validate(question) for question in questions]

    async def submit_answers(
        self,
        payload: list[SubmitAnswersRequestItem],
        current_user: User,
        db: AsyncSession,
    ) -> SubmitAnswersResponse:
        """Persist user questionnaire answers inside a single transaction."""
        if not payload:
            logger.warning("Questionnaire submission rejected for user_id=%s: empty payload", current_user.id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one questionnaire answer item is required.",
            )

        # Fetch all questions from the database
        all_questions_result = await db.execute(select(InteractiveQuestionnaire))
        all_questionnaires = all_questions_result.scalars().all()
        questionnaire_map = {q.id: q for q in all_questionnaires}

        # Check if all submitted questionnaire IDs exist
        payload_map = {}
        for item in payload:
            if item.questionnaire_id not in questionnaire_map:
                logger.warning(
                    "Questionnaire submission failed for user_id=%s: questionnaire id %s not found",
                    current_user.id,
                    item.questionnaire_id,
                )
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Questionnaire(s) not found: {[item.questionnaire_id]}",
                )
            payload_map[item.questionnaire_id] = item

        # Validate that all required/mandatory questions are answered
        for q_id, questionnaire in questionnaire_map.items():
            if not questionnaire.optional:
                # If required, it must be in the payload
                if q_id not in payload_map:
                    logger.warning(
                        "Questionnaire submission failed for user_id=%s: mandatory question %s missing from payload",
                        current_user.id,
                        q_id,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Questionnaire {q_id} requires a submission entry.",
                    )
                
                # And the answers must not be empty
                item = payload_map[q_id]
                if not item.user_answers or not any(answer.strip() for answer in item.user_answers):
                    logger.warning(
                        "Questionnaire submission failed for user_id=%s: mandatory question %s missing answer",
                        current_user.id,
                        q_id,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Questionnaire {q_id} requires at least one non-empty answer.",
                    )

            # Validate answers for choice-based questions if present in payload
            if q_id in payload_map:
                item = payload_map[q_id]
                if questionnaire.answer_type in {"radiobuttons", "dropdown"}:
                    if len(item.user_answers) > 1:
                        logger.warning(
                            "Questionnaire submission failed for user_id=%s: single-choice question %s has multiple answers",
                            current_user.id,
                            q_id,
                        )
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Questionnaire {q_id} only accepts a single choice answer.",
                        )
                
                if questionnaire.answer_type in {"radiobuttons", "dropdown", "checkboxes"}:
                    allowed_options = set(questionnaire.answers)
                    for ans in item.user_answers:
                        if ans not in allowed_options:
                            logger.warning(
                                "Questionnaire submission failed for user_id=%s: answer %r not allowed for question %s",
                                current_user.id,
                                ans,
                                q_id,
                            )
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Answer '{ans}' is not a valid option for question {q_id}.",
                            )

        # Query existing answers for this user to avoid duplicates
        existing_answers_query = await db.execute(
            select(UserInteractiveQuestionnaire).where(
                UserInteractiveQuestionnaire.user_id == current_user.id
            )
        )
        existing_answers = {
            ans.questionnaire_id: ans for ans in existing_answers_query.scalars().all()
        }

        try:
            for item in payload_map.values():
                q_id = item.questionnaire_id
                now = datetime.now(timezone.utc)
                if q_id in existing_answers:
                    # Update the existing record instead of inserting a duplicate
                    ans_record = existing_answers[q_id]
                    ans_record.user_answers = list(item.user_answers)
                    ans_record.updated_at = now
                    ans_record.submission_date = now
                else:
                    # Create a new record
                    ans_record = UserInteractiveQuestionnaire(
                        user_id=current_user.id,
                        questionnaire_id=q_id,
                        user_answers=list(item.user_answers),
                        submission_date=now,
                        created_at=now,
                        updated_at=now,
                    )
                    db.add(ans_record)
            await db.flush()
        except Exception:
            logger.exception(
                "Database transaction failed while saving questionnaire answers for user_id=%s",
                current_user.id,
            )
            raise

        logger.info(
            "Questionnaire answers submitted: user_id=%s count=%s",
            current_user.id,
            len(payload_map),
        )

        # ── Mark interactive_questions as completed in auth_actions ────────────
        # Fetch or lazily create the auth_actions row and flip the flag.
        auth_actions_result = await db.execute(
            select(AuthActions).where(AuthActions.user_id == current_user.id)
        )
        auth_actions_row = auth_actions_result.scalar_one_or_none()

        if auth_actions_row is None:
            auth_actions_row = AuthActions(
                user_id=current_user.id,
                payment=True,
                interactive_questions=True,
            )
            db.add(auth_actions_row)
        else:
            auth_actions_row.interactive_questions = True
            auth_actions_row.updated_at = datetime.now(timezone.utc)

        await db.flush()
        logger.info(
            "auth_actions.interactive_questions set to True for user_id=%s",
            current_user.id,
        )

        return SubmitAnswersResponse(message="Questionnaire answers submitted successfully.")

    async def create_question(
        self,
        payload: SubmitQuestionRequest,
        current_user: User,
        db: AsyncSession,
    ) -> InteractiveQuestionnaireResponse:
        """Persist a new interactive questionnaire question for admins."""
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required.",
            )

        now = datetime.now(timezone.utc)
        questionnaire = InteractiveQuestionnaire(
            question=payload.question.strip(),
            answer_type=payload.answer_type,
            optional=payload.optional,
            answers=list(payload.answers),
            created_at=now,
            updated_at=now,
        )

        db.add(questionnaire)
        await db.flush()
        await db.refresh(questionnaire)

        logger.info(
            "Questionnaire question created: id=%s by admin_user_id=%s",
            questionnaire.id,
            current_user.id,
        )
        return InteractiveQuestionnaireResponse.model_validate(questionnaire)

    async def update_question(
        self,
        question_id: int,
        payload: UpdateQuestionRequest,
        current_user: User,
        db: AsyncSession,
    ) -> InteractiveQuestionnaireResponse:
        """Update an existing interactive questionnaire question for admins."""
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required.",
            )

        questionnaire = await db.get(InteractiveQuestionnaire, question_id)
        if questionnaire is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Questionnaire question not found.",
            )

        if payload.question is not None:
            questionnaire.question = payload.question.strip()
        if payload.answer_type is not None:
            questionnaire.answer_type = payload.answer_type
        if payload.optional is not None:
            questionnaire.optional = payload.optional
        if payload.answers is not None:
            questionnaire.answers = list(payload.answers)

        questionnaire.updated_at = datetime.now(timezone.utc)
        await db.flush()
        await db.refresh(questionnaire)

        logger.info(
            "Questionnaire question updated: id=%s by admin_user_id=%s",
            question_id,
            current_user.id,
        )
        return InteractiveQuestionnaireResponse.model_validate(questionnaire)

    async def delete_question(
        self,
        question_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> DeleteQuestionResponse:
        """Delete an interactive questionnaire question for admins."""
        if current_user.role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin privileges required.",
            )

        questionnaire = await db.get(InteractiveQuestionnaire, question_id)
        if questionnaire is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Questionnaire question not found.",
            )

        await db.delete(questionnaire)
        await db.flush()

        logger.info(
            "Questionnaire question deleted: id=%s by admin_user_id=%s",
            question_id,
            current_user.id,
        )
        return DeleteQuestionResponse(message="Questionnaire question deleted successfully.")


questionnaire_service = QuestionnaireService()
