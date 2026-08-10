
import logging
import os
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import PublicSurveyResponse, Survey, User, Workspace
from app.models.survey_models import (
    ExportSurveyResponse,
    PublicSurveyDetailResponse,
    SaveAllSurveyQuestionsRequest,
    SingleSurveyResponseItem,
    SubmitPublicSurveyRequest,
    SubmitPublicSurveyResponse,
    SurveyListResponse,
    SurveyQuestionItem,
    SurveyResponse,
    SurveyResponsesListResponse,
    UpdateSurveyRequest,
)

logger = logging.getLogger(__name__)


class SurveyService:

    async def sync_survey_from_validation_result(
        self,
        user_id: int,
        workspace_id: int,
        validation_result: dict,
        db: AsyncSession,
    ) -> None:
        """Automatically sync agent-generated survey questions into the `surveys` table."""
        if not validation_result or not isinstance(validation_result, dict):
            return

        agent_results = validation_result.get("agent_results") or {}
        survey_agent_output = agent_results.get("survey_intelligence_agent") or {}
        survey_data = survey_agent_output.get("data") or {}
        agent_questions = survey_data.get("questions") or []

        if not agent_questions:
            return

        type_mapping = {
            "open_ended": "text",
            "textarea": "text",
            "text": "text",
            "multiple_choice": "radio",
            "radiobuttons": "radio",
            "radio": "radio",
            "rating_scale": "radio",
            "ranking": "radio",
            "checkbox": "checkbox",
            "checkboxes": "checkbox",
            "dropdown": "dropdown",
        }

        mapped_questions = []
        for idx, q in enumerate(agent_questions, start=1):
            q_text = q.get("question_text") or q.get("question") or f"Question {idx}"
            raw_type = str(q.get("question_type") or q.get("questionType") or "text").lower()
            q_type = type_mapping.get(raw_type, "text")
            options = q.get("options") or []
            if not isinstance(options, list):
                options = []

            mapped_questions.append(
                SurveyQuestionItem(
                    id=idx,
                    question=q_text,
                    questionType=q_type,
                    options=options,
                )
            )

        req = SaveAllSurveyQuestionsRequest(
            userId=user_id,
            workspaceId=workspace_id,
            questions=mapped_questions,
        )

        user_result = await db.execute(select(User).where(User.id == user_id))
        user = user_result.scalar_one_or_none()
        if user is None:
            return

        try:
            await self.save_all_questions(req, user, db)
            logger.info(
                "Synced agent-generated survey to surveys table: workspace_id=%s user_id=%s count=%s",
                workspace_id, user_id, len(mapped_questions)
            )
        except Exception:
            logger.exception(
                "Failed to auto-sync survey questions to surveys table for workspace_id=%s",
                workspace_id
            )

    #save all questions
    async def save_all_questions(
        self,
        payload: SaveAllSurveyQuestionsRequest,
        current_user: User,
        db: AsyncSession,
    ) -> SurveyResponse:
        """Create or replace the full set of survey questions for a workspace, owned by current_user."""
        if payload.userId != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to save survey questions for this user.",
            )

        workspace_result = await db.execute(
            select(Workspace).where(Workspace.id == payload.workspaceId)
        )
        workspace = workspace_result.scalar_one_or_none()
        if workspace is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workspace {payload.workspaceId} not found.",
            )
        if workspace.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this workspace.",
            )

        questions_payload = [q.model_dump() for q in payload.questions]
        now = datetime.now(timezone.utc)

        survey_result = await db.execute(
            select(Survey).where(
                Survey.user_id == payload.userId,
                Survey.workspace_id == payload.workspaceId,
            )
        )
        survey = survey_result.scalar_one_or_none()

        if survey is None:
            survey = Survey(
                user_id=payload.userId,
                workspace_id=payload.workspaceId,
                questions=questions_payload,
                created_at=now,
                updated_at=now,
            )
            db.add(survey)
        else:
            survey.questions = questions_payload
            survey.updated_at = now

        await db.flush()

        if not survey.survey_link:
            base_url = os.getenv("PUBLIC_APP_URL", "http://localhost:8000")
            survey.survey_link = f"{base_url.rstrip('/')}/api/v1/surveys/public/{survey.id}"
            await db.flush()

        await db.refresh(survey)

        logger.info(
            "Survey questions saved: survey_id=%s workspace_id=%s user_id=%s question_count=%s",
            survey.id, survey.workspace_id, survey.user_id, len(questions_payload),
        )
        return SurveyResponse.model_validate(survey)

    # Update a survey
    async def update_survey(
        self,
        survey_id: int,
        payload: UpdateSurveyRequest,
        current_user: User,
        db: AsyncSession,
    ) -> SurveyResponse:
        """Partially update a survey's link and/or question set — 404/403 enforced."""
        if payload.userId != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to update surveys for this user.",
            )

        result = await db.execute(select(Survey).where(Survey.id == survey_id))
        survey = result.scalar_one_or_none()

        if survey is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Survey {survey_id} not found.",
            )
        if survey.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this survey.",
            )

        if payload.surveyLink is not None:
            survey.survey_link = payload.surveyLink
        if payload.questions is not None:
            survey.questions = [q.model_dump() for q in payload.questions]
        survey.updated_at = datetime.now(timezone.utc)

        await db.flush()
        await db.refresh(survey)

        logger.info(
            "Survey updated: survey_id=%s user_id=%s",
            survey.id, current_user.id,
        )
        return SurveyResponse.model_validate(survey)

    #get all surveys
    async def get_all_surveys(
        self,
        current_user: User,
        db: AsyncSession,
    ) -> SurveyListResponse:
        """Return all surveys owned by current_user."""
        result = await db.execute(
            select(Survey)
            .where(Survey.user_id == current_user.id)
            .order_by(Survey.created_at.desc())
        )
        surveys = result.scalars().all()

        return SurveyListResponse(
            total=len(surveys),
            surveys=[SurveyResponse.model_validate(s) for s in surveys],
        )

    # ── Get single survey by ID
    async def get_survey_by_id(
        self,
        survey_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> SurveyResponse:
        """Fetch a single survey by ID — 404/403 enforced."""
        result = await db.execute(select(Survey).where(Survey.id == survey_id))
        survey = result.scalar_one_or_none()

        if survey is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Survey {survey_id} not found.",
            )
        if survey.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to access this survey.",
            )

        return SurveyResponse.model_validate(survey)

    # ── Get survey by Workspace ID
    async def get_survey_by_workspace_id(
        self,
        workspace_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> SurveyResponse:
        """Fetch the survey associated with a specific workspace ID."""
        result = await db.execute(
            select(Survey).where(
                Survey.workspace_id == workspace_id,
                Survey.user_id == current_user.id,
            )
        )
        survey = result.scalar_one_or_none()

        if survey is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No survey found for workspace {workspace_id}.",
            )

        return SurveyResponse.model_validate(survey)

    # ── Delete survey
    async def delete_survey(
        self,
        survey_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> None:
        """Hard-delete a survey — 404/403 enforced."""
        result = await db.execute(select(Survey).where(Survey.id == survey_id))
        survey = result.scalar_one_or_none()

        if survey is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Survey {survey_id} not found.",
            )
        if survey.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to delete this survey.",
            )

        await db.delete(survey)
        await db.flush()
        logger.info("Survey deleted: survey_id=%s user_id=%s", survey_id, current_user.id)

    # ── Export survey
    async def export_survey(
        self,
        survey_id: int,
        export_format: str,
        current_user: User,
        db: AsyncSession,
    ) -> ExportSurveyResponse:
        """Export survey questions as markdown or JSON representation."""
        survey = await self.get_survey_by_id(survey_id, current_user, db)
        questions = survey.questions

        if export_format.lower() == "markdown":
            lines = [f"# Survey #{survey.id}\n"]
            for q in questions:
                lines.append(f"### Q{q.id}. {q.question}")
                lines.append(f"*Type:* {q.questionType}")
                if q.options:
                    lines.append("*Options:*")
                    for opt in q.options:
                        lines.append(f"  - {opt}")
                lines.append("")
            content_str = "\n".join(lines)
        else:
            import json
            content_str = json.dumps([q.model_dump() for q in questions], indent=2)

        return ExportSurveyResponse(
            survey_id=survey.id,
            workspace_id=survey.workspace_id,
            survey_link=survey.survey_link,
            total_questions=len(questions),
            format=export_format.lower(),
            content=content_str,
        )

    # ── Public survey details (Unauthenticated)
    async def get_public_survey(
        self,
        survey_id: int,
        db: AsyncSession,
    ) -> PublicSurveyDetailResponse:
        """Retrieve public details of a survey for external respondents without login."""
        result = await db.execute(select(Survey).where(Survey.id == survey_id))
        survey = result.scalar_one_or_none()

        if survey is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Survey {survey_id} not found.",
            )

        workspace_result = await db.execute(select(Workspace).where(Workspace.id == survey.workspace_id))
        workspace = workspace_result.scalar_one_or_none()
        ws_name = workspace.name if workspace else f"Workspace #{survey.workspace_id}"

        questions_list = [SurveyQuestionItem(**q) if isinstance(q, dict) else q for q in survey.questions]

        return PublicSurveyDetailResponse(
            surveyId=survey.id,
            workspaceName=ws_name,
            questions=questions_list,
        )

    # ── Submit public survey response (Unauthenticated)
    async def submit_public_survey(
        self,
        survey_id: int,
        payload: SubmitPublicSurveyRequest,
        db: AsyncSession,
    ) -> SubmitPublicSurveyResponse:
        """Persist responses from an external respondent for a public survey."""
        survey_result = await db.execute(select(Survey).where(Survey.id == survey_id))
        survey = survey_result.scalar_one_or_none()

        if survey is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Survey {survey_id} not found.",
            )

        answers_payload = [ans.model_dump() for ans in payload.answers]
        now = datetime.now(timezone.utc)

        response_record = PublicSurveyResponse(
            survey_id=survey_id,
            respondent_email=payload.respondentEmail.strip() if payload.respondentEmail else None,
            answers=answers_payload,
            submitted_at=now,
        )

        db.add(response_record)
        await db.flush()
        await db.refresh(response_record)

        logger.info(
            "Public survey response submitted: response_id=%s survey_id=%s respondent=%s",
            response_record.id, survey_id, payload.respondentEmail
        )

        return SubmitPublicSurveyResponse(
            responseId=response_record.id,
            message="Thank you! Your survey response has been submitted.",
        )

    # ── Get collected responses for a survey (Authenticated Owner)
    async def get_survey_responses(
        self,
        survey_id: int,
        current_user: User,
        db: AsyncSession,
    ) -> SurveyResponsesListResponse:
        """Fetch all collected external responses for a survey owned by current_user."""
        await self.get_survey_by_id(survey_id, current_user, db)  # ownership check

        result = await db.execute(
            select(PublicSurveyResponse)
            .where(PublicSurveyResponse.survey_id == survey_id)
            .order_by(PublicSurveyResponse.submitted_at.desc())
        )
        responses = result.scalars().all()

        return SurveyResponsesListResponse(
            survey_id=survey_id,
            total_responses=len(responses),
            responses=[SingleSurveyResponseItem.model_validate(r) for r in responses],
        )


# Singleton
survey_service = SurveyService()

