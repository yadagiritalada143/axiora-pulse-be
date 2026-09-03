import pytest
from typing import Any
from unittest.mock import patch
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from types import SimpleNamespace

from app.core.dependencies import get_current_user
from app.core.security import hash_password_async
from app.db.models import Role, Survey, User, Workspace
from app.services.mentor_service import mentor_service, WorkspaceMentorState


# helpers

async def create_test_user(db_session: AsyncSession, *, username: str, role: str = "member") -> User:
    role_obj = (await db_session.execute(select(Role).where(Role.name == role))).scalar_one_or_none()
    if role_obj is None:
        role_obj = Role(name=role, description=f"{role} role")
        db_session.add(role_obj)
        await db_session.flush()

    user = User(
        username=username,
        password=await hash_password_async("Test@12345"),
        register_mfa=True,
        role=role_obj,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def create_workspace(
    db_session: AsyncSession,
    *,
    user_id: int,
    name: str = "Mentor Workspace",
    validation_result: dict | None = None,
) -> Workspace:
    workspace = Workspace(
        user_id=user_id,
        name=name,
        description=None,
        state="GATHERING_INFO",
        idea={
            "idea_title": None,
            "idea_description": None,
            "problem_statement": None,
            "industry": "general",
            "founder_validation_goal": "validate my idea",
            "geography": "global",
        },
        conversation_history=[],
        validation_result=validation_result,
    )
    db_session.add(workspace)
    await db_session.commit()
    await db_session.refresh(workspace)
    return workspace


def authenticate_as(user: User) -> None:
    role_name = user._primary_role

    def _has_role(name: str) -> bool:
        return role_name == name

    current_user = SimpleNamespace(id=user.id, username=user.username, role=role_name, has_role=_has_role)

    async def _mock_current_user():
        return current_user

    from main import app

    app.dependency_overrides[get_current_user] = _mock_current_user


async def _fake_process_message(
    state: WorkspaceMentorState,
    user_message: str,
    attachments: list | None = None,
    user_id: int | None = None,
    db: Any | None = None,
    **kwargs,
) -> WorkspaceMentorState:
    """Deterministic stand-in for mentor_service.process_message — avoids real LLM calls."""
    state.conversation_history.append({"role": "user", "content": user_message})
    state.idea["idea_title"] = "Mocked Idea Title"
    state.conversation_history.append({"role": "assistant", "content": "Mocked mentor reply"})
    return state


def sample_validation_result() -> dict:
    return {
        "validation_score": 78,
        "verdict": "proceed",
        "confidence_rating": 0.8,
        "strengths": ["Clear problem"],
        "risks": ["Small market"],
        "recommendations": ["Talk to 10 customers"],
        "agent_results": {
            "idea_validation_agent": {"data": {"problem_clarity_score": 80}},
            "market_research_agent": {"data": {"market_opportunity_score": 70}},
            "survey_intelligence_agent": {
                "data": {
                    "questions": [
                        {"question_text": "What is your biggest challenge?", "question_type": "open_ended"},
                        {
                            "question_text": "How often does this occur?",
                            "question_type": "multiple_choice",
                            "options": ["Daily", "Weekly", "Rarely"],
                        },
                    ]
                }
            },
        },
    }


# post /api/v1/workspaces/{id}/chat

@pytest.mark.asyncio
async def test_chat_with_mentor_updates_workspace_and_returns_reply(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="chat-user@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    authenticate_as(user)

    with patch.object(mentor_service, "process_message", side_effect=_fake_process_message):
        response = await client.post(
            f"/api/v1/workspaces/{workspace.id}/chat",
            json={"message": "We help freelancers track invoices."},
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["reply"] == "Mocked mentor reply"
    assert data["workspace_id"] == workspace.id
    assert data["idea"]["idea_title"] == "Mocked Idea Title"

    await db_session.refresh(workspace)
    assert workspace.idea["idea_title"] == "Mocked Idea Title"
    assert len(workspace.conversation_history) == 2


@pytest.mark.asyncio
async def test_chat_with_mentor_rejects_empty_message(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="chat-empty@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    authenticate_as(user)

    response = await client.post(f"/api/v1/workspaces/{workspace.id}/chat", json={"message": ""})

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_chat_with_mentor_forbidden_for_non_owner(
    client: AsyncClient, db_session: AsyncSession
):
    owner = await create_test_user(db_session, username="chat-owner@axiorapulse.com")
    intruder = await create_test_user(db_session, username="chat-intruder@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id)
    authenticate_as(intruder)

    with patch.object(mentor_service, "process_message", side_effect=_fake_process_message):
        response = await client.post(
            f"/api/v1/workspaces/{workspace.id}/chat", json={"message": "Hijack attempt"}
        )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_chat_with_mentor_auto_syncs_survey_when_validated(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="chat-autosync@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    authenticate_as(user)

    async def _validated_process_message(
        state: WorkspaceMentorState,
        user_message: str,
        attachments: list | None = None,
        user_id: int | None = None,
        db: Any | None = None,
        **kwargs,
    ) -> WorkspaceMentorState:
        state.conversation_history.append({"role": "user", "content": user_message})
        state.state = "VALIDATED"
        state.validation_result = sample_validation_result()
        state.conversation_history.append({"role": "assistant", "content": "Here is your validation result."})
        return state

    with patch.object(mentor_service, "process_message", side_effect=_validated_process_message):
        response = await client.post(
            f"/api/v1/workspaces/{workspace.id}/chat", json={"message": "Run validation"}
        )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["state"] == "VALIDATED"

    result = await db_session.execute(select(Survey).where(Survey.workspace_id == workspace.id))
    survey = result.scalar_one_or_none()
    assert survey is not None
    assert len(survey.questions) == 2


# get /api/v1/workspaces/{id}/state

@pytest.mark.asyncio
async def test_get_workspace_state_returns_full_dialogue_context(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="state-user@axiorapulse.com")
    workspace = await create_workspace(
        db_session, user_id=user.id, validation_result=sample_validation_result()
    )
    authenticate_as(user)

    response = await client.get(f"/api/v1/workspaces/{workspace.id}/state")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["id"] == workspace.id
    assert data["validation_result"]["validation_score"] == 78


@pytest.mark.asyncio
async def test_get_workspace_state_forbidden_for_non_owner(
    client: AsyncClient, db_session: AsyncSession
):
    owner = await create_test_user(db_session, username="state-owner@axiorapulse.com")
    intruder = await create_test_user(db_session, username="state-intruder@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id)
    authenticate_as(intruder)

    response = await client.get(f"/api/v1/workspaces/{workspace.id}/state")

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_get_workspace_state_not_found(client: AsyncClient, db_session: AsyncSession):
    user = await create_test_user(db_session, username="state-404@axiorapulse.com")
    authenticate_as(user)

    response = await client.get("/api/v1/workspaces/999999/state")

    assert response.status_code == status.HTTP_404_NOT_FOUND


# post /api/v1/workspaces/{id}/reset

@pytest.mark.asyncio
async def test_reset_workspace_mentor_restores_defaults(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="reset-user@axiorapulse.com")
    workspace = await create_workspace(
        db_session, user_id=user.id, validation_result=sample_validation_result()
    )
    workspace.state = "VALIDATED"
    workspace.conversation_history = [{"role": "user", "content": "old message"}]
    await db_session.commit()
    authenticate_as(user)

    response = await client.post(f"/api/v1/workspaces/{workspace.id}/reset")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["state"] == "GATHERING_INFO"
    assert data["validation_result"] is None
    assert len(data["conversation_history"]) == 1
    assert data["conversation_history"][0]["role"] == "assistant"


@pytest.mark.asyncio
async def test_reset_workspace_mentor_forbidden_for_non_owner(
    client: AsyncClient, db_session: AsyncSession
):
    owner = await create_test_user(db_session, username="reset-owner@axiorapulse.com")
    intruder = await create_test_user(db_session, username="reset-intruder@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id)
    authenticate_as(intruder)

    response = await client.post(f"/api/v1/workspaces/{workspace.id}/reset")

    assert response.status_code == status.HTTP_403_FORBIDDEN


# get /api/v1/workspaces/{id}/reports/{agent_name} & post .../reports/export

@pytest.mark.asyncio
async def test_download_report_requires_prior_validation(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="report-novalidation@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    authenticate_as(user)

    response = await client.get(f"/api/v1/workspaces/{workspace.id}/reports/idea_validation_agent")

    assert response.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.asyncio
async def test_download_report_returns_file_with_attachment_header(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="report-download@axiorapulse.com")
    workspace = await create_workspace(
        db_session, user_id=user.id, validation_result=sample_validation_result()
    )
    authenticate_as(user)

    response = await client.get(
        f"/api/v1/workspaces/{workspace.id}/reports/idea_validation_agent",
        params={"format": "doc"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert "attachment" in response.headers["content-disposition"]
    assert len(response.content) > 0


@pytest.mark.asyncio
async def test_export_report_via_post_returns_file(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="report-export@axiorapulse.com")
    workspace = await create_workspace(
        db_session, user_id=user.id, validation_result=sample_validation_result()
    )
    authenticate_as(user)

    response = await client.post(
        f"/api/v1/workspaces/{workspace.id}/reports/export",
        json={"agent_name": "market_research_agent", "format": "doc"},
    )

    assert response.status_code == status.HTTP_200_OK
    assert "attachment" in response.headers["content-disposition"]


@pytest.mark.asyncio
async def test_download_report_forbidden_for_non_owner(
    client: AsyncClient, db_session: AsyncSession
):
    owner = await create_test_user(db_session, username="report-owner@axiorapulse.com")
    intruder = await create_test_user(db_session, username="report-intruder@axiorapulse.com")
    workspace = await create_workspace(
        db_session, user_id=owner.id, validation_result=sample_validation_result()
    )
    authenticate_as(intruder)

    response = await client.get(f"/api/v1/workspaces/{workspace.id}/reports/idea_validation_agent")

    assert response.status_code == status.HTTP_403_FORBIDDEN


# put /api/v1/workspaces/{id}/survey/questions

@pytest.mark.asyncio
async def test_update_workspace_survey_questions_success(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="survey-edit@axiorapulse.com")
    workspace = await create_workspace(
        db_session, user_id=user.id, validation_result=sample_validation_result()
    )
    authenticate_as(user)

    payload = {
        "survey_title": "Founder Discovery Survey",
        "survey_objective": "Validate demand",
        "questions": [
            {
                "question_text": "What tool do you use today?",
                "question_type": "open_ended",
            },
            {
                "question_text": "How much would you pay?",
                "question_type": "multiple_choice",
                "options": ["$0-10", "$10-50", "$50+"],
            },
        ],
    }

    response = await client.put(f"/api/v1/workspaces/{workspace.id}/survey/questions", json=payload)

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["workspace_id"] == workspace.id
    assert data["survey_title"] == "Founder Discovery Survey"
    assert len(data["questions"]) == 2

    await db_session.refresh(workspace)
    synced_data = workspace.validation_result["agent_results"]["survey_intelligence_agent"]["data"]
    assert len(synced_data["questions"]) == 2

    # Confirms the edit also synced into the standalone `surveys` table
    result = await db_session.execute(select(Survey).where(Survey.workspace_id == workspace.id))
    survey = result.scalar_one_or_none()
    assert survey is not None
    assert len(survey.questions) == 2


@pytest.mark.asyncio
async def test_update_workspace_survey_questions_forbidden_for_non_owner(
    client: AsyncClient, db_session: AsyncSession
):
    owner = await create_test_user(db_session, username="survey-edit-owner@axiorapulse.com")
    intruder = await create_test_user(db_session, username="survey-edit-intruder@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=owner.id)
    authenticate_as(intruder)

    payload = {"questions": [{"question_text": "Hijack?", "question_type": "open_ended"}]}
    response = await client.put(f"/api/v1/workspaces/{workspace.id}/survey/questions", json=payload)

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_update_workspace_survey_questions_rejects_empty_questions(
    client: AsyncClient, db_session: AsyncSession
):
    user = await create_test_user(db_session, username="survey-edit-empty@axiorapulse.com")
    workspace = await create_workspace(db_session, user_id=user.id)
    authenticate_as(user)

    response = await client.put(
        f"/api/v1/workspaces/{workspace.id}/survey/questions", json={}
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
