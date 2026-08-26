from datetime import datetime, timezone

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from types import SimpleNamespace

from app.core.dependencies import get_current_user
from app.core.security import hash_password_async
from app.db.models import PublicSurveyResponse, Survey, User, Workspace


# helpers

async def create_test_user(
    db_session: AsyncSession,
    *,
    username: str,
    role: str = "user",
    display_name: str | None = None,
    created_at: datetime | None = None,
) -> User:
    user = User(
        username=username,
        password=await hash_password_async("Test@12345"),
        role=role,
        display_name=display_name,
        register_mfa=True,
    )
    if created_at is not None:
        user.created_at = created_at
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def create_workspace(db_session: AsyncSession, *, user_id: int, name: str) -> Workspace:
    workspace = Workspace(
        user_id=user_id,
        name=name,
        description=None,
        state="GATHERING_INFO",
        idea={},
        conversation_history=[],
        validation_result=None,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


def sample_questions() -> list[dict]:
    return [
        {"id": 1, "question": "How satisfied are you?", "questionType": "radio", "options": ["Yes", "No"]},
        {"id": 2, "question": "What should improve?", "questionType": "text", "options": []},
    ]


async def create_survey(
    db_session: AsyncSession,
    *,
    user_id: int,
    workspace_id: int,
    questions: list[dict] | None = None,
    survey_link: str | None = "https://example.com/survey",
) -> Survey:
    survey = Survey(
        user_id=user_id,
        workspace_id=workspace_id,
        survey_link=survey_link,
        questions=questions if questions is not None else sample_questions(),
    )
    db_session.add(survey)
    await db_session.commit()
    await db_session.refresh(survey)
    return survey


async def create_survey_response(
    db_session: AsyncSession,
    *,
    survey_id: int,
    respondent_email: str | None = None,
    answers: list[dict] | None = None,
) -> PublicSurveyResponse:
    response = PublicSurveyResponse(
        survey_id=survey_id,
        respondent_email=respondent_email,
        answers=answers if answers is not None else [{"questionId": 1, "answer": "Yes"}],
    )
    db_session.add(response)
    await db_session.commit()
    await db_session.refresh(response)
    return response


def authenticate_as(user: User) -> None:
    current_user = SimpleNamespace(id=user.id, username=user.username, role=user.role)

    async def _mock_current_user():
        return current_user

    from main import app

    app.dependency_overrides[get_current_user] = _mock_current_user


# get /api/v1/admin/users

@pytest.mark.asyncio
async def test_list_users_requires_admin(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="admin-list-nonadmin@axiorapulse.com")
    authenticate_as(user)

    response = await client.get("/api/v1/admin/users")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_list_users_returns_paginated_directory_with_workspace_counts(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(db_session, username="admin-list-admin@axiorapulse.com", role="admin")
    user_a = await create_test_user(db_session, username="admin-list-a@axiorapulse.com")
    user_b = await create_test_user(db_session, username="admin-list-b@axiorapulse.com")
    await create_workspace(db_session, user_id=user_a.id, name="WS 1")
    await create_workspace(db_session, user_id=user_a.id, name="WS 2")
    authenticate_as(admin)

    response = await client.get("/api/v1/admin/users")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    users_by_id = {u["id"]: u for u in data["users"]}
    assert users_by_id[user_a.id]["workspace_count"] == 2
    assert users_by_id[user_b.id]["workspace_count"] == 0
    assert data["pagination"]["total"] == len(data["users"])


@pytest.mark.asyncio
async def test_list_users_pagination_limit_and_offset(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(db_session, username="admin-list-page-admin@axiorapulse.com", role="admin")
    for i in range(5):
        await create_test_user(db_session, username=f"admin-list-page-{i}@axiorapulse.com")
    authenticate_as(admin)

    response = await client.get("/api/v1/admin/users", params={"limit": 2, "offset": 0})

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["users"]) == 2
    assert data["pagination"]["limit"] == 2
    assert data["pagination"]["offset"] == 0
    assert data["pagination"]["total"] == 6  # 5 seeded + the admin itself


@pytest.mark.asyncio
async def test_list_users_search_filters_by_username_and_display_name(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(db_session, username="admin-search-admin@axiorapulse.com", role="admin")
    await create_test_user(
        db_session, username="findme@axiorapulse.com", display_name="Findable Person"
    )
    await create_test_user(db_session, username="nomatch@axiorapulse.com", display_name="Someone Else")
    authenticate_as(admin)

    response = await client.get("/api/v1/admin/users", params={"search": "findme"})

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["users"]) == 1
    assert data["users"][0]["username"] == "findme@axiorapulse.com"


@pytest.mark.asyncio
async def test_list_users_search_by_display_name(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(db_session, username="admin-search-name-admin@axiorapulse.com", role="admin")
    await create_test_user(
        db_session, username="displayname-match@axiorapulse.com", display_name="Unique Display Name"
    )
    authenticate_as(admin)

    response = await client.get("/api/v1/admin/users", params={"search": "Unique Display"})

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["users"]) == 1
    assert data["users"][0]["display_name"] == "Unique Display Name"


@pytest.mark.asyncio
async def test_list_users_rejects_invalid_pagination_params(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(db_session, username="admin-invalid-params@axiorapulse.com", role="admin")
    authenticate_as(admin)

    response = await client.get("/api/v1/admin/users", params={"limit": 0})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    response_over = await client.get("/api/v1/admin/users", params={"limit": 101})
    assert response_over.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    response_negative_offset = await client.get("/api/v1/admin/users", params={"offset": -1})
    assert response_negative_offset.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# get /api/v1/admin/users/surveys

@pytest.mark.asyncio
async def test_list_surveys_includes_survey_link(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(db_session, username="admin-survey-links-admin@axiorapulse.com", role="admin")
    owner = await create_test_user(db_session, username="admin-survey-links-owner@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id, name="Survey Link Workspace")
    survey = await create_survey(
        db_session,
        user_id=owner.id,
        workspace_id=workspace.id,
        survey_link="https://example.com/s/public-link",
    )
    authenticate_as(admin)

    response = await client.get("/api/v1/admin/users/surveys", params={"user_id": owner.id})

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["surveys"][0]["id"] == survey.id
    assert data["surveys"][0]["survey_link"] == "https://example.com/s/public-link"


@pytest.mark.asyncio
async def test_list_surveys_builds_url_from_public_token_when_link_is_missing(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PUBLIC_APP_URL", "https://app.example.com")
    admin = await create_test_user(db_session, username="admin-survey-fallback-admin@axiorapulse.com", role="admin")
    owner = await create_test_user(db_session, username="admin-survey-fallback-owner@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id, name="Survey Fallback Workspace")
    survey = await create_survey(
        db_session,
        user_id=owner.id,
        workspace_id=workspace.id,
        survey_link=None,
    )
    authenticate_as(admin)

    response = await client.get("/api/v1/admin/users/surveys", params={"user_id": owner.id})

    assert response.status_code == status.HTTP_200_OK
    expected_url = f"https://app.example.com/surveys/public/{survey.public_token}"
    data = response.json()
    assert data["surveys"][0]["survey_link"] == expected_url
    assert data["surveys"][0]["status"] == "Active"


# get /api/v1/admin/users/{user_id}/survey-summary

@pytest.mark.asyncio
async def test_user_survey_summary_includes_surveys_with_links(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(db_session, username="admin-summary-links-admin@axiorapulse.com", role="admin")
    owner = await create_test_user(db_session, username="admin-summary-links-owner@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id, name="Summary Workspace")
    survey = await create_survey(
        db_session,
        user_id=owner.id,
        workspace_id=workspace.id,
        survey_link="https://example.com/s/summary-link",
    )
    await create_survey_response(db_session, survey_id=survey.id)
    authenticate_as(admin)

    response = await client.get(f"/api/v1/admin/users/{owner.id}/survey-summary")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["surveys_created"] == 1
    assert data["total_responses"] == 1
    assert data["surveys"][0]["id"] == survey.id
    assert data["surveys"][0]["survey_link"] == "https://example.com/s/summary-link"
    assert data["surveys"][0]["responses_count"] == 1


# get /api/v1/admin/surveys/{survey_id}/responses

@pytest.mark.asyncio
async def test_list_survey_responses_requires_admin(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="admin-responses-nonadmin@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id, name="Survey Workspace")
    survey = await create_survey(db_session, user_id=user.id, workspace_id=workspace.id)
    authenticate_as(user)

    response = await client.get(f"/api/v1/admin/surveys/{survey.id}/responses")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_list_survey_responses_returns_paginated_rows_with_preview(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(db_session, username="admin-responses-admin@axiorapulse.com", role="admin")
    owner = await create_test_user(db_session, username="admin-responses-owner@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id, name="Customer Survey")
    survey = await create_survey(db_session, user_id=owner.id, workspace_id=workspace.id)
    await create_survey_response(
        db_session,
        survey_id=survey.id,
        respondent_email="a@example.com",
        answers=[{"questionId": 1, "answer": "Yes"}, {"questionId": 2, "answer": "Speed"}],
    )
    await create_survey_response(
        db_session,
        survey_id=survey.id,
        respondent_email="b@example.com",
        answers=[{"questionId": 1, "answer": "No"}],
    )
    authenticate_as(admin)

    response = await client.get(
        f"/api/v1/admin/surveys/{survey.id}/responses",
        params={"limit": 1, "offset": 0},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["survey_id"] == survey.id
    assert data["survey_link"] == "https://example.com/survey"
    assert data["total_responses"] == 2
    assert data["pagination"] == {"total": 2, "limit": 1, "offset": 0}
    assert len(data["responses"]) == 1
    row = data["responses"][0]
    assert row["response_code"].startswith("#RS-")
    assert row["status"] == "Completed"
    assert row["source"] == "Web"
    assert row["answers_preview"][0]["question"] == "How satisfied are you?"


@pytest.mark.asyncio
async def test_list_survey_responses_searches_email_and_answers(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(db_session, username="admin-responses-search-admin@axiorapulse.com", role="admin")
    owner = await create_test_user(db_session, username="admin-responses-search-owner@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id, name="Search Workspace")
    survey = await create_survey(db_session, user_id=owner.id, workspace_id=workspace.id)
    await create_survey_response(
        db_session,
        survey_id=survey.id,
        respondent_email="match@example.com",
        answers=[{"questionId": 1, "answer": "Yes"}],
    )
    await create_survey_response(
        db_session,
        survey_id=survey.id,
        respondent_email="other@example.com",
        answers=[{"questionId": 1, "answer": "Unique answer"}],
    )
    authenticate_as(admin)

    email_response = await client.get(
        f"/api/v1/admin/surveys/{survey.id}/responses",
        params={"search": "match@example.com"},
    )
    answer_response = await client.get(
        f"/api/v1/admin/surveys/{survey.id}/responses",
        params={"search": "Unique answer"},
    )

    assert email_response.status_code == status.HTTP_200_OK
    assert email_response.json()["total_responses"] == 1
    assert answer_response.status_code == status.HTTP_200_OK
    assert answer_response.json()["total_responses"] == 1


@pytest.mark.asyncio
async def test_list_survey_responses_not_found(client: AsyncClient, db_session: AsyncSession):
    admin = await create_test_user(db_session, username="admin-responses-404-admin@axiorapulse.com", role="admin")
    authenticate_as(admin)

    response = await client.get("/api/v1/admin/surveys/999999/responses")

    assert response.status_code == status.HTTP_404_NOT_FOUND


# get /api/v1/admin/surveys/{survey_id}/responses/{response_id}

@pytest.mark.asyncio
async def test_get_survey_response_detail_returns_owner_and_workspace_context(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(db_session, username="admin-response-detail-admin@axiorapulse.com", role="admin")
    owner = await create_test_user(db_session, username="admin-response-detail-owner@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id, name="Detail Workspace")
    survey = await create_survey(db_session, user_id=owner.id, workspace_id=workspace.id)
    saved_response = await create_survey_response(
        db_session,
        survey_id=survey.id,
        respondent_email="detail@example.com",
        answers=[{"questionId": 2, "answer": "Make it faster"}],
    )
    authenticate_as(admin)

    response = await client.get(
        f"/api/v1/admin/surveys/{survey.id}/responses/{saved_response.id}"
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == saved_response.id
    assert data["user_id"] == owner.id
    assert data["owner_username"] == owner.username
    assert data["workspace_name"] == "Detail Workspace"
    assert data["survey_link"] == "https://example.com/survey"
    assert data["answers_preview"] == [
        {"question": "What should improve?", "answer": "Make it faster"}
    ]


@pytest.mark.asyncio
async def test_get_survey_response_detail_not_found(client: AsyncClient, db_session: AsyncSession):
    admin = await create_test_user(db_session, username="admin-response-detail-404-admin@axiorapulse.com", role="admin")
    owner = await create_test_user(db_session, username="admin-response-detail-404-owner@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id, name="Detail 404 Workspace")
    survey = await create_survey(db_session, user_id=owner.id, workspace_id=workspace.id)
    authenticate_as(admin)

    response = await client.get(f"/api/v1/admin/surveys/{survey.id}/responses/999999")

    assert response.status_code == status.HTTP_404_NOT_FOUND


# get /api/v1/admin/stats/user-growth

@pytest.mark.asyncio
async def test_user_growth_requires_admin(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="growth-nonadmin@axiorapulse.com")
    authenticate_as(user)

    response = await client.get("/api/v1/admin/stats/user-growth")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_user_growth_by_month_buckets_and_zero_fills(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(
        db_session, username="growth-month-admin@axiorapulse.com", role="admin"
    )
    await create_test_user(
        db_session,
        username="growth-jan-a@axiorapulse.com",
        created_at=datetime(2025, 1, 10, tzinfo=timezone.utc),
    )
    await create_test_user(
        db_session,
        username="growth-jan-b@axiorapulse.com",
        created_at=datetime(2025, 1, 20, tzinfo=timezone.utc),
    )
    await create_test_user(
        db_session,
        username="growth-mar@axiorapulse.com",
        created_at=datetime(2025, 3, 5, tzinfo=timezone.utc),
    )
    authenticate_as(admin)

    response = await client.get(
        "/api/v1/admin/stats/user-growth", params={"granularity": "month"}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["granularity"] == "month"
    periods = [point["period"] for point in data["series"]]
    counts = {point["period"]: point["count"] for point in data["series"]}

    assert counts["2025-01"] == 2
    assert counts["2025-02"] == 0  # zero-filled gap month
    assert counts["2025-03"] == 1
    # Series is continuous and ascending from the first signup through the present.
    assert periods == sorted(periods)
    now = datetime.now(timezone.utc)
    current = f"{now.year:04d}-{now.month:02d}"
    assert periods[-1] == current
    assert counts[current] >= 1  # the admin registered "now"


@pytest.mark.asyncio
async def test_user_growth_by_year_buckets_and_zero_fills(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(
        db_session, username="growth-year-admin@axiorapulse.com", role="admin"
    )
    await create_test_user(
        db_session,
        username="growth-2024@axiorapulse.com",
        created_at=datetime(2024, 6, 1, tzinfo=timezone.utc),
    )
    authenticate_as(admin)

    response = await client.get(
        "/api/v1/admin/stats/user-growth", params={"granularity": "year"}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["granularity"] == "year"
    counts = {point["period"]: point["count"] for point in data["series"]}
    assert counts["2024"] == 1
    now = datetime.now(timezone.utc)
    if now.year > 2025:
        assert counts["2025"] == 0  # zero-filled gap year
    assert str(now.year) in counts  # current year is always present


@pytest.mark.asyncio
async def test_user_growth_defaults_to_month(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(
        db_session, username="growth-default-admin@axiorapulse.com", role="admin"
    )
    authenticate_as(admin)

    response = await client.get("/api/v1/admin/stats/user-growth")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["granularity"] == "month"


@pytest.mark.asyncio
async def test_user_growth_rejects_invalid_granularity(
    client: AsyncClient, db_session: AsyncSession
):
    admin = await create_test_user(
        db_session, username="growth-invalid-admin@axiorapulse.com", role="admin"
    )
    authenticate_as(admin)

    response = await client.get(
        "/api/v1/admin/stats/user-growth", params={"granularity": "week"}
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
