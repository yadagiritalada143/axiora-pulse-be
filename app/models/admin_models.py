"""Request and response schemas for the minimal administrator API."""

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel


class AdminUserResponse(BaseModel):
    """Safe user details displayed in the administrator directory."""

    id: int
    username: str
    display_name: str | None = None
    role: str
    created_at: datetime
    workspace_count: int
    active_workspace_count: int
    archived_workspace_count: int


class AdminUserPagination(BaseModel):
    total: int
    limit: int
    offset: int


class AdminUserListResponse(BaseModel):
    users: list[AdminUserResponse]
    pagination: AdminUserPagination


class AdminSurveyResponse(BaseModel):
    """Survey details displayed in the administrator directory, with owner info.

    `status` and `workspace_description` are inferred, not stored: status is
    "Active" once a survey_link has been generated (else "Closed"/draft), and
    workspace_description doubles as the survey's description since Survey
    itself has no title/description/status columns of its own.
    """

    id: int
    user_id: int
    owner_username: str
    workspace_id: int
    workspace_name: str
    workspace_description: Optional[str] = None
    survey_link: str | None = None
    status: Literal["Active", "Closed"]
    question_count: int
    responses_count: int
    created_at: datetime
    updated_at: datetime


class AdminUserSurveySummaryItem(BaseModel):
    """Survey row included in a user's admin survey summary."""

    id: int
    workspace_id: int
    workspace_name: str
    workspace_description: Optional[str] = None
    survey_link: str | None = None
    status: Literal["Active", "Closed"]
    question_count: int
    responses_count: int
    created_at: datetime
    updated_at: datetime


class AdminUserSurveySummaryResponse(BaseModel):
    """Header summary for the admin "user detail" page (Users > <name>)."""

    user_id: int
    name: str
    email: str
    status: str
    joined_on: datetime
    surveys_created: int
    total_responses: int
    surveys: list[AdminUserSurveySummaryItem]


class AdminSurveyPagination(BaseModel):
    total: int
    limit: int
    offset: int


class AdminSurveyListResponse(BaseModel):
    surveys: list[AdminSurveyResponse]
    pagination: AdminSurveyPagination


class AdminSurveyAnswerPreviewItem(BaseModel):
    """A submitted answer paired with its survey question text for admin previews."""

    question: str
    answer: Any


class AdminSurveyResponseItem(BaseModel):
    """Collected survey response row for the administrator survey detail page."""

    id: int
    response_code: str
    survey_id: int
    respondent_email: Optional[str] = None
    answers: list[dict]
    answers_preview: list[AdminSurveyAnswerPreviewItem]
    submitted_at: datetime
    status: Literal["Completed"] = "Completed"
    source: Literal["Web"] = "Web"


class AdminSurveyResponsePagination(BaseModel):
    total: int
    limit: int
    offset: int


class AdminSurveyResponsesListResponse(BaseModel):
    survey_id: int
    survey_link: Optional[str] = None
    total_responses: int
    responses: list[AdminSurveyResponseItem]
    pagination: AdminSurveyResponsePagination


class AdminSurveyResponseDetailResponse(AdminSurveyResponseItem):
    """Single survey response detail with survey and owner context."""

    user_id: int
    owner_username: str
    workspace_id: int
    workspace_name: str
    workspace_description: Optional[str] = None
    survey_link: Optional[str] = None




class UserGrowthPoint(BaseModel):
    """Number of users that registered within a single period."""

    period: str  # "YYYY-MM" for month granularity, "YYYY" for year granularity
    count: int


class UserGrowthResponse(BaseModel):
    """New-user counts bucketed by period for the growth chart."""

    granularity: str  # "month" | "year"
    series: list[UserGrowthPoint]


class AdminDashboardGrowth(BaseModel):
    """Percentage change for each headline metric vs the previous 7 days."""

    total_users: float
    paid_users: float
    non_paid_users: float
    active_subscriptions: float
    total_workspaces: float
    active_workspaces: float
    archived_workspaces: float


class AdminDashboardStatsResponse(BaseModel):
    """Headline counts plus week-over-week growth for the admin dashboard."""

    total_users: int
    paid_users: int
    non_paid_users: int
    active_subscriptions: int
    total_workspaces: int
    active_workspaces: int
    archived_workspaces: int
    growth: AdminDashboardGrowth


class UserGrowthDataPoint(BaseModel):
    """Registration count within a single date/period bucket."""

    period: str  # "YYYY-MM-DD" for day buckets, "YYYY-MM" for month buckets
    count: int


class UserGrowthAnalyticsResponse(BaseModel):
    """User registrations bucketed by the requested period filter."""

    period: str  # week | month | last_7_days | last_30_days | year
    series: list[UserGrowthDataPoint]


class UsersByPlanItem(BaseModel):
    """User count and share for a single subscription plan."""

    plan: str  # plan code (e.g. free, pro, enterprise)
    user_count: int
    percentage: float


class UsersByPlanResponse(BaseModel):
    """Distribution of users across subscription plans."""

    total_users: int
    plans: list[UsersByPlanItem]


class RevenueDataPoint(BaseModel):
    """Successful payment revenue within a single bucket."""

    period: str  # "YYYY-MM-DD HH:00" hourly | "YYYY-MM-DD" daily | "YYYY-MM" monthly
    amount: float  # in INR (major units)


class RevenueResponse(BaseModel):
    """Revenue aggregated over a period, with a bucketed time series."""

    period: str  # today | week | month | year
    total_amount: float  # sum of successful payments within the period, in INR
    series: list[RevenueDataPoint]
