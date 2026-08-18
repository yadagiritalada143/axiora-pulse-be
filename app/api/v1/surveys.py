"""
Surveys API Router  —  /api/v1/surveys
──────────────────────────────────────────────────────────────────────────────
Routes:
  POST   /api/v1/surveys                              → save_all_survey_questions
  GET    /api/v1/surveys                              → get_all_surveys
  GET    /api/v1/surveys/{survey_id}                  → get_survey_by_id
  PUT    /api/v1/surveys/{survey_id}                  → update_survey
  DELETE /api/v1/surveys/{survey_id}                  → delete_survey
  GET    /api/v1/surveys/workspace/{workspace_id}    → get_survey_by_workspace_id
  GET    /api/v1/surveys/{survey_id}/export           → export_survey
  GET    /api/v1/surveys/{survey_id}/responses        → get_survey_responses
  GET    /api/v1/surveys/public/{token}                → get_public_survey (Unauthenticated)
  POST   /api/v1/surveys/public/{token}/submit         → submit_public_survey (Unauthenticated)

The public routes are keyed by Survey.public_token (an opaque, unguessable
value) rather than the internal sequential `id`, so a respondent can't
enumerate other users' surveys by incrementing the URL.
"""
import logging

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.limiter import limiter
from app.db.database import get_db
from app.db.models import User
from app.models.survey_models import (
    ExportSurveyResponse,
    PublicSurveyDetailResponse,
    SaveAllSurveyQuestionsRequest,
    SubmitPublicSurveyRequest,
    SubmitPublicSurveyResponse,
    SurveyAnalysisResponse,
    SurveyListResponse,
    SurveyResponse,
    SurveyResponsesListResponse,
    UpdateSurveyRequest,
)
from app.services.survey_service import survey_service

router = APIRouter(prefix="/surveys", tags=["Surveys"])
logger = logging.getLogger(__name__)


# ── Save All Survey Questions
@router.post(
    "",
    response_model=SurveyResponse,
    status_code=status.HTTP_200_OK,
    summary="Save all survey questions for a workspace",
    description="Creates or replaces the full set of survey questions for the given user's workspace.",
)
@limiter.limit("20/minute")
async def save_all_survey_questions(
    request: Request,
    payload: SaveAllSurveyQuestionsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SurveyResponse:
    logger.info(
        "Saving survey questions: user_id=%s workspace_id=%s question_count=%s",
        payload.userId, payload.workspaceId, len(payload.questions),
    )
    return await survey_service.save_all_questions(payload, current_user, db)


# ── Get All Surveys for Current User
@router.get(
    "",
    response_model=SurveyListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get all surveys for the current user",
    description="Returns all surveys owned by the authenticated user.",
)
@limiter.limit("60/minute")
async def get_all_surveys(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SurveyListResponse:
    return await survey_service.get_all_surveys(current_user, db)


# ── Get Survey by Workspace ID
@router.get(
    "/workspace/{workspace_id}",
    response_model=SurveyResponse,
    status_code=status.HTTP_200_OK,
    summary="Get survey by workspace ID",
    description="Fetches the survey questions associated with a specific workspace.",
)
@limiter.limit("60/minute")
async def get_survey_by_workspace_id(
    request: Request,
    workspace_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SurveyResponse:
    return await survey_service.get_survey_by_workspace_id(workspace_id, current_user, db)


# ── Public Survey Details (Unauthenticated for external survey takers)
@router.get(
    "/public/{token}",
    response_model=PublicSurveyDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get public survey details for external respondents",
    description="Unauthenticated public endpoint allowing external respondents to load questions for a shareable survey link.",
)
@limiter.limit("120/minute")
async def get_public_survey(
    request: Request,
    token: str,
    db: AsyncSession = Depends(get_db),
) -> PublicSurveyDetailResponse:
    return await survey_service.get_public_survey(token, db)


# ── Submit Public Survey Answers (Unauthenticated for external survey takers)
@router.post(
    "/public/{token}/submit",
    response_model=SubmitPublicSurveyResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit answers to a public survey",
    description="Unauthenticated public endpoint for external target customers/respondents to submit survey responses.",
)
@limiter.limit("30/minute")
async def submit_public_survey(
    request: Request,
    token: str,
    payload: SubmitPublicSurveyRequest,
    db: AsyncSession = Depends(get_db),
) -> SubmitPublicSurveyResponse:
    return await survey_service.submit_public_survey(token, payload, db)


# ── Get Single Survey by ID (Authenticated Owner)
@router.get(
    "/{survey_id}",
    response_model=SurveyResponse,
    status_code=status.HTTP_200_OK,
    summary="Get a survey by ID",
    description="Returns a single survey owned by the authenticated user.",
)
@limiter.limit("60/minute")
async def get_survey_by_id(
    request: Request,
    survey_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SurveyResponse:
    return await survey_service.get_survey_by_id(survey_id, current_user, db)


# ── Update Survey by ID
@router.put(
    "/{survey_id}",
    response_model=SurveyResponse,
    status_code=status.HTTP_200_OK,
    summary="Update a survey by ID",
    description="Updates the survey link and/or question set for an existing survey owned by the authenticated user.",
)
@limiter.limit("20/minute")
async def update_survey(
    request: Request,
    survey_id: int,
    payload: UpdateSurveyRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SurveyResponse:
    logger.info(
        "Updating survey: survey_id=%s user_id=%s",
        survey_id, payload.userId,
    )
    return await survey_service.update_survey(survey_id, payload, current_user, db)


# ── Delete Survey by ID
@router.delete(
    "/{survey_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a survey by ID",
    description="Permanently deletes a survey.",
)
@limiter.limit("20/minute")
async def delete_survey(
    request: Request,
    survey_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await survey_service.delete_survey(survey_id, current_user, db)


# ── Export Survey
@router.get(
    "/{survey_id}/export",
    response_model=ExportSurveyResponse,
    status_code=status.HTTP_200_OK,
    summary="Export survey questions",
    description="Exports survey questions in Markdown or JSON format.",
)
@limiter.limit("30/minute")
async def export_survey(
    request: Request,
    survey_id: int,
    format: str = Query("json", description="Export format: json or markdown"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExportSurveyResponse:
    return await survey_service.export_survey(survey_id, format, current_user, db)


# ── Get Collected Responses for Survey (Authenticated Owner)
@router.get(
    "/{survey_id}/responses",
    response_model=SurveyResponsesListResponse,
    status_code=status.HTTP_200_OK,
    summary="Get all collected public responses for a survey",
    description="Retrieves all external respondent submissions collected for a survey.",
)
@limiter.limit("60/minute")
async def get_survey_responses(
    request: Request,
    survey_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SurveyResponsesListResponse:
    return await survey_service.get_survey_responses(survey_id, current_user, db)


# ── Run Post-Link Response Intelligence Analysis (SI.11–SI.44)
@router.post(
    "/{survey_id}/analyze",
    response_model=SurveyAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Run post-survey-link response intelligence analysis",
    description="Triggers the Survey Intelligence Agent to evaluate collected responses across fraud detection, quality scoring, customer intelligence, customer validation, and GTM handoff (SI.11–SI.44). Requires at least 1 response.",
)
@limiter.limit("10/minute")
async def analyze_survey(
    request: Request,
    survey_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SurveyAnalysisResponse:
    result = await survey_service.run_post_link_analysis(survey_id, current_user, db)
    return SurveyAnalysisResponse(
        survey_id=survey_id,
        status="success",
        analysis_result=result,
    )


# ── Get Stored Post-Link Analysis Result
@router.get(
    "/{survey_id}/analysis",
    response_model=SurveyAnalysisResponse,
    status_code=status.HTTP_200_OK,
    summary="Get saved post-link analysis result",
    description="Retrieves the saved SI.11–SI.44 post-link response intelligence analysis for a survey.",
)
@limiter.limit("60/minute")
async def get_survey_analysis(
    request: Request,
    survey_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SurveyAnalysisResponse:
    survey = await survey_service.get_survey_by_id(survey_id, current_user, db)
    analysis = survey.analysis_result or {}
    return SurveyAnalysisResponse(
        survey_id=survey_id,
        status="success",
        analysis_result=analysis,
    )

