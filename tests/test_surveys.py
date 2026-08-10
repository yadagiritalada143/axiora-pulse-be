import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from types import SimpleNamespace

from app.core.dependencies import get_current_user
from app.core.security import hash_password_async
from app.db.models import PublicSurveyResponse, Survey, User, Workspace


# helpers

async def create_test_user(db_session: AsyncSession, *, username: str) -> User:
    user = User(
        username=username,
        password=await hash_password_async("Test@12345"),
        role="user",
        register_mfa=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def create_workspace(
    db_session: AsyncSession,
    *,
    user_id: int,
    name: str = "Survey Workspace",
) -> Workspace:
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


async def create_survey(
    db_session: AsyncSession,
    *,
    user_id: int,
    workspace_id: int,
    questions: list | None = None,
    survey_link: str | None = None,
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


def sample_questions() -> list[dict]:
    return [
        {"id": 1, "question": "What is your age?", "questionType": "text", "options": []},
        {
            "id": 2,
            "question": "What is your primary goal?",
            "questionType": "radio",
            "options": ["Validate", "Raise funds", "Others"],
        },
    ]


def authenticate_as(user: User) -> None:
    current_user = SimpleNamespace(id=user.id, username=user.username, role=user.role)

    async def _mock_current_user():
        return current_user

    from main import app

    app.dependency_overrides[get_current_user] = _mock_current_user


# post /api/v1/surveys — save (create/replace) all survey questions

@pytest.mark.asyncio
async def test_save_all_survey_questions_creates_new_survey(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="survey-create@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    authenticate_as(user)

    payload = {
        "userId": user.id,
        "workspaceId": workspace.id,
        "questions": sample_questions(),
    }

    response = await client.post("/api/v1/surveys", json=payload)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["user_id"] == user.id
    assert data["workspace_id"] == workspace.id
    assert len(data["questions"]) == 2
    assert data["survey_link"] is not None  # auto-generated on first save

    saved = await db_session.get(Survey, data["id"])
    assert saved is not None
    assert saved.workspace_id == workspace.id


@pytest.mark.asyncio
async def test_save_all_survey_questions_replaces_existing_survey(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="survey-replace@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    survey = await create_survey(db_session, user_id=user.id, workspace_id=workspace.id)
    authenticate_as(user)

    new_questions = [
        {"id": 1, "question": "New question?", "questionType": "dropdown", "options": ["A", "B"]}
    ]
    response = await client.post(
        "/api/v1/surveys",
        json={"userId": user.id, "workspaceId": workspace.id, "questions": new_questions},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == survey.id  # same survey row reused, not duplicated
    assert len(data["questions"]) == 1
    assert data["questions"][0]["question"] == "New question?"

    result = await db_session.execute(
        select(Survey).where(Survey.workspace_id == workspace.id)
    )
    assert len(result.scalars().all()) == 1


@pytest.mark.asyncio
async def test_save_all_survey_questions_rejects_mismatched_user_id(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="survey-mismatch@axiorapulse.com")
    other_user = await create_test_user(db_session, username="survey-other@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    authenticate_as(user)

    response = await client.post(
        "/api/v1/surveys",
        json={"userId": other_user.id, "workspaceId": workspace.id, "questions": sample_questions()},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_save_all_survey_questions_workspace_not_found(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="survey-noworkspace@axiorapulse.com")
    authenticate_as(user)

    response = await client.post(
        "/api/v1/surveys",
        json={"userId": user.id, "workspaceId": 999999, "questions": sample_questions()},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_save_all_survey_questions_rejects_workspace_owned_by_other_user(
    client: AsyncClient, db_session: AsyncSession
):
    owner = await create_test_user(db_session, username="survey-ws-owner@axiorapulse.com")
    intruder = await create_test_user(db_session, username="survey-ws-intruder@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id)
    authenticate_as(intruder)

    response = await client.post(
        "/api/v1/surveys",
        json={"userId": intruder.id, "workspaceId": workspace.id, "questions": sample_questions()},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_save_all_survey_questions_rejects_empty_body(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="survey-invalid@axiorapulse.com")
    authenticate_as(user)

    response = await client.post("/api/v1/surveys", json={"userId": user.id})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


# get /api/v1/surveys — list surveys for current user

@pytest.mark.asyncio
async def test_get_all_surveys_returns_only_authenticated_users_surveys(
    client: AsyncClient, db_session: AsyncSession
):
    user_a = await create_test_user(db_session, username="survey-list-a@axiorapulse.com")
    user_b = await create_test_user(db_session, username="survey-list-b@axiorapulse.com")
    ws_a = await create_workspace(db_session, user_id=user_a.id)
    ws_b = await create_workspace(db_session, user_id=user_b.id)
    survey_a = await create_survey(db_session, user_id=user_a.id, workspace_id=ws_a.id)
    await create_survey(db_session, user_id=user_b.id, workspace_id=ws_b.id)
    authenticate_as(user_a)

    response = await client.get("/api/v1/surveys")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total"] == 1
    assert data["surveys"][0]["id"] == survey_a.id


@pytest.mark.asyncio
async def test_get_all_surveys_rejects_unauthenticated_requests(client: AsyncClient):
    response = await client.get("/api/v1/surveys")
    assert response.status_code == status.HTTP_403_FORBIDDEN


# get /api/v1/surveys/{survey_id} — get survey by id

@pytest.mark.asyncio
async def test_get_survey_by_id_success(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="survey-get@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    survey = await create_survey(db_session, user_id=user.id, workspace_id=workspace.id)
    authenticate_as(user)

    response = await client.get(f"/api/v1/surveys/{survey.id}")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == survey.id


@pytest.mark.asyncio
async def test_get_survey_by_id_not_found(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="survey-get-404@axiorapulse.com")
    authenticate_as(user)

    response = await client.get("/api/v1/surveys/999999")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_get_survey_by_id_forbidden_for_non_owner(
    client: AsyncClient, db_session: AsyncSession
):
    owner = await create_test_user(db_session, username="survey-get-owner@axiorapulse.com")
    intruder = await create_test_user(db_session, username="survey-get-intruder@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id)
    survey = await create_survey(db_session, user_id=owner.id, workspace_id=workspace.id)
    authenticate_as(intruder)

    response = await client.get(f"/api/v1/surveys/{survey.id}")

    assert response.status_code == status.HTTP_403_FORBIDDEN


# get /api/v1/surveys/workspace/{workspace_id} — get survey by workspace id

@pytest.mark.asyncio
async def test_get_survey_by_workspace_id_success(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="survey-by-ws@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    survey = await create_survey(db_session, user_id=user.id, workspace_id=workspace.id)
    authenticate_as(user)

    response = await client.get(f"/api/v1/surveys/workspace/{workspace.id}")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["id"] == survey.id


@pytest.mark.asyncio
async def test_get_survey_by_workspace_id_not_found(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="survey-by-ws-404@axiorapulse.com")
    authenticate_as(user)

    response = await client.get("/api/v1/surveys/workspace/999999")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_get_survey_by_workspace_id_scoped_to_current_user(
    client: AsyncClient, db_session: AsyncSession
):
    owner = await create_test_user(db_session, username="survey-by-ws-owner@axiorapulse.com")
    intruder = await create_test_user(db_session, username="survey-by-ws-intruder@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id)
    await create_survey(db_session, user_id=owner.id, workspace_id=workspace.id)
    authenticate_as(intruder)

    # Not owned by intruder → treated as not found (query is scoped by user_id)
    response = await client.get(f"/api/v1/surveys/workspace/{workspace.id}")

    assert response.status_code == status.HTTP_404_NOT_FOUND


# put /api/v1/surveys/{survey_id} — update survey

@pytest.mark.asyncio
async def test_update_survey_link_only(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="survey-update-link@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    survey = await create_survey(db_session, user_id=user.id, workspace_id=workspace.id)
    authenticate_as(user)

    response = await client.put(
        f"/api/v1/surveys/{survey.id}",
        json={"userId": user.id, "surveyLink": "https://example.com/s/abc"},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["survey_link"] == "https://example.com/s/abc"
    assert len(data["questions"]) == 2  # unchanged


@pytest.mark.asyncio
async def test_update_survey_questions_only(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="survey-update-q@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    survey = await create_survey(db_session, user_id=user.id, workspace_id=workspace.id)
    authenticate_as(user)

    new_questions = [
        {"id": 1, "question": "Updated question?", "questionType": "checkbox", "options": ["X", "Y"]}
    ]
    response = await client.put(
        f"/api/v1/surveys/{survey.id}",
        json={"userId": user.id, "questions": new_questions},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert len(data["questions"]) == 1
    assert data["questions"][0]["question"] == "Updated question?"


@pytest.mark.asyncio
async def test_update_survey_requires_at_least_one_field(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="survey-update-empty@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    survey = await create_survey(db_session, user_id=user.id, workspace_id=workspace.id)
    authenticate_as(user)

    response = await client.put(
        f"/api/v1/surveys/{survey.id}",
        json={"userId": user.id},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_update_survey_not_found(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="survey-update-404@axiorapulse.com")
    authenticate_as(user)

    response = await client.put(
        "/api/v1/surveys/999999",
        json={"userId": user.id, "surveyLink": "https://example.com/s/xyz"},
    )

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_update_survey_rejects_mismatched_user_id(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="survey-update-mismatch@axiorapulse.com")
    other_user = await create_test_user(db_session, username="survey-update-other@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    survey = await create_survey(db_session, user_id=user.id, workspace_id=workspace.id)
    authenticate_as(user)

    response = await client.put(
        f"/api/v1/surveys/{survey.id}",
        json={"userId": other_user.id, "surveyLink": "https://example.com/s/hijack"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_update_survey_forbidden_for_non_owner(
    client: AsyncClient, db_session: AsyncSession
):
    owner = await create_test_user(db_session, username="survey-update-owner@axiorapulse.com")
    intruder = await create_test_user(db_session, username="survey-update-intruder@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id)
    survey = await create_survey(db_session, user_id=owner.id, workspace_id=workspace.id)
    authenticate_as(intruder)

    response = await client.put(
        f"/api/v1/surveys/{survey.id}",
        json={"userId": intruder.id, "surveyLink": "https://example.com/s/hijack"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


# delete /api/v1/surveys/{survey_id} — delete survey

@pytest.mark.asyncio
async def test_delete_survey_success(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="survey-delete@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    survey = await create_survey(db_session, user_id=user.id, workspace_id=workspace.id)
    survey_id = survey.id
    authenticate_as(user)

    response = await client.delete(f"/api/v1/surveys/{survey_id}")

    assert response.status_code == status.HTTP_204_NO_CONTENT
    assert await db_session.get(Survey, survey_id) is None


@pytest.mark.asyncio
async def test_delete_survey_not_found(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="survey-delete-404@axiorapulse.com")
    authenticate_as(user)

    response = await client.delete("/api/v1/surveys/999999")

    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_delete_survey_forbidden_for_non_owner(
    client: AsyncClient, db_session: AsyncSession
):
    owner = await create_test_user(db_session, username="survey-delete-owner@axiorapulse.com")
    intruder = await create_test_user(db_session, username="survey-delete-intruder@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id)
    survey = await create_survey(db_session, user_id=owner.id, workspace_id=workspace.id)
    survey_id = survey.id
    authenticate_as(intruder)

    response = await client.delete(f"/api/v1/surveys/{survey_id}")

    assert response.status_code == status.HTTP_403_FORBIDDEN
    result = await db_session.execute(select(Survey).where(Survey.id == survey_id))
    assert result.scalar_one_or_none() is not None


# get /api/v1/surveys/{survey_id}/export — export survey

@pytest.mark.asyncio
async def test_export_survey_json_format(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="survey-export-json@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    survey = await create_survey(db_session, user_id=user.id, workspace_id=workspace.id)
    authenticate_as(user)

    response = await client.get(f"/api/v1/surveys/{survey.id}/export?format=json")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["format"] == "json"
    assert data["total_questions"] == 2
    assert data["survey_id"] == survey.id


@pytest.mark.asyncio
async def test_export_survey_markdown_format(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="survey-export-md@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    survey = await create_survey(db_session, user_id=user.id, workspace_id=workspace.id)
    authenticate_as(user)

    response = await client.get(f"/api/v1/surveys/{survey.id}/export?format=markdown")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["format"] == "markdown"
    assert "What is your age?" in data["content"]


@pytest.mark.asyncio
async def test_export_survey_not_found(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="survey-export-404@axiorapulse.com")
    authenticate_as(user)

    response = await client.get("/api/v1/surveys/999999/export")

    assert response.status_code == status.HTTP_404_NOT_FOUND


# get /api/v1/surveys/public/{survey_id} — public survey details (unauthenticated)

@pytest.mark.asyncio
async def test_get_public_survey_success(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="survey-public-get@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id, name="Public Workspace")
    survey = await create_survey(db_session, user_id=user.id, workspace_id=workspace.id)

    # No authentication override — public endpoint
    response = await client.get(f"/api/v1/surveys/public/{survey.id}")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["surveyId"] == survey.id
    assert data["workspaceName"] == "Public Workspace"
    assert len(data["questions"]) == 2


@pytest.mark.asyncio
async def test_get_public_survey_not_found(client: AsyncClient):
    response = await client.get("/api/v1/surveys/public/999999")
    assert response.status_code == status.HTTP_404_NOT_FOUND


# post /api/v1/surveys/public/{survey_id}/submit — submit public survey answers

@pytest.mark.asyncio
async def test_submit_public_survey_success(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="survey-public-submit@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    survey = await create_survey(db_session, user_id=user.id, workspace_id=workspace.id)

    payload = {
        "respondentEmail": "respondent@example.com",
        "answers": [
            {"questionId": 1, "answer": "29"},
            {"questionId": 2, "answer": "Validate"},
        ],
    }

    response = await client.post(f"/api/v1/surveys/public/{survey.id}/submit", json=payload)

    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert "responseId" in data

    result = await db_session.execute(
        select(PublicSurveyResponse).where(PublicSurveyResponse.survey_id == survey.id)
    )
    saved = result.scalar_one_or_none()
    assert saved is not None
    assert saved.respondent_email == "respondent@example.com"
    assert len(saved.answers) == 2


@pytest.mark.asyncio
async def test_submit_public_survey_not_found(client: AsyncClient):
    payload = {"answers": [{"questionId": 1, "answer": "x"}]}
    response = await client.post("/api/v1/surveys/public/999999/submit", json=payload)
    assert response.status_code == status.HTTP_404_NOT_FOUND


@pytest.mark.asyncio
async def test_submit_public_survey_allows_missing_email(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="survey-public-noemail@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    survey = await create_survey(db_session, user_id=user.id, workspace_id=workspace.id)

    payload = {"answers": [{"questionId": 1, "answer": "29"}]}
    response = await client.post(f"/api/v1/surveys/public/{survey.id}/submit", json=payload)

    assert response.status_code == status.HTTP_201_CREATED


# get /api/v1/surveys/{survey_id}/responses — collected public responses

@pytest.mark.asyncio
async def test_get_survey_responses_success(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="survey-responses@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    survey = await create_survey(db_session, user_id=user.id, workspace_id=workspace.id)

    resp1 = PublicSurveyResponse(
        survey_id=survey.id, respondent_email="a@example.com", answers=[{"questionId": 1, "answer": "1"}]
    )
    resp2 = PublicSurveyResponse(
        survey_id=survey.id, respondent_email="b@example.com", answers=[{"questionId": 1, "answer": "2"}]
    )
    db_session.add_all([resp1, resp2])
    await db_session.commit()

    authenticate_as(user)
    response = await client.get(f"/api/v1/surveys/{survey.id}/responses")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total_responses"] == 2
    assert data["survey_id"] == survey.id


@pytest.mark.asyncio
async def test_get_survey_responses_forbidden_for_non_owner(
    client: AsyncClient, db_session: AsyncSession
):
    owner = await create_test_user(db_session, username="survey-responses-owner@axiorapulse.com")
    intruder = await create_test_user(db_session, username="survey-responses-intruder@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id)
    survey = await create_survey(db_session, user_id=owner.id, workspace_id=workspace.id)
    authenticate_as(intruder)

    response = await client.get(f"/api/v1/surveys/{survey.id}/responses")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_get_survey_responses_empty_list(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="survey-responses-empty@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    survey = await create_survey(db_session, user_id=user.id, workspace_id=workspace.id)
    authenticate_as(user)

    response = await client.get(f"/api/v1/surveys/{survey.id}/responses")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["total_responses"] == 0
