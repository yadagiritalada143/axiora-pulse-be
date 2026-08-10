from datetime import datetime
from unittest.mock import patch

import pytest
from fastapi import status
from httpx import AsyncClient

from app.models.orchestration_models import (
    OrchestrationResponse,
    ValidationResult,
    ValidationVerdict,
    WorkflowType,
)
from app.orchestration.orchestrator import orchestrator


# helpers

def valid_idea_payload(**overrides) -> dict:
    payload = {
        "idea_title": "Invoice Tracker",
        "idea_description": "A tool that helps freelancers track unpaid invoices automatically.",
        "problem_statement": "Freelancers lose track of unpaid invoices and follow-ups.",
    }
    payload.update(overrides)
    return payload


def fake_success_response(request) -> OrchestrationResponse:
    return OrchestrationResponse(
        run_id="run-123",
        workspace_id=request.workspace_id,
        idea_id=request.idea_id,
        workflow_type=request.workflow_type,
        status="success",
        result=ValidationResult(
            idea_id=request.idea_id,
            orchestration_run_id="run-123",
            validation_score=82.0,
            confidence_rating=0.75,
            verdict=ValidationVerdict.BUILD,
            strengths=["Clear problem"],
            risks=["Competitive market"],
            assumptions=["Freelancers will pay for this"],
            recommendations=["Talk to 10 freelancers"],
            agent_results={},
            mentor_summary="Looks promising.",
        ),
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )


# post /api/v1/orchestration/run

@pytest.mark.asyncio
async def test_run_orchestration_success(client: AsyncClient):
    async def _fake_run(request):
        return fake_success_response(request)

    with patch.object(orchestrator, "run", side_effect=_fake_run):
        response = await client.post(
            "/api/v1/orchestration/run",
            json={"idea": valid_idea_payload()},
        )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "success"
    assert data["result"]["validation_score"] == 82.0
    assert data["result"]["verdict"] == "build"


@pytest.mark.asyncio
async def test_run_orchestration_defaults_workflow_type_to_idea_validation(client: AsyncClient):
    captured = {}

    async def _fake_run(request):
        captured["workflow_type"] = request.workflow_type
        return fake_success_response(request)

    with patch.object(orchestrator, "run", side_effect=_fake_run):
        response = await client.post(
            "/api/v1/orchestration/run",
            json={"idea": valid_idea_payload()},
        )

    assert response.status_code == status.HTTP_200_OK
    assert captured["workflow_type"] == WorkflowType.IDEA_VALIDATION


@pytest.mark.asyncio
async def test_run_orchestration_passes_through_failed_status(client: AsyncClient):
    async def _fake_run(request):
        return OrchestrationResponse(
            run_id="run-456",
            workspace_id=request.workspace_id,
            idea_id=request.idea_id,
            workflow_type=request.workflow_type,
            status="failed",
            error="Agent pipeline timed out",
            started_at=datetime.utcnow(),
        )

    with patch.object(orchestrator, "run", side_effect=_fake_run):
        response = await client.post(
            "/api/v1/orchestration/run",
            json={"idea": valid_idea_payload()},
        )

    # Orchestrator itself never raises — failures are surfaced in the response body, not HTTP status.
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "failed"
    assert data["error"] == "Agent pipeline timed out"
    assert data["result"] is None


@pytest.mark.asyncio
async def test_run_orchestration_unhandled_exception_returns_500_without_leaking_details(
    client: AsyncClient,
):
    async def _raise(request):
        raise RuntimeError("secret internal stack trace detail")

    with patch.object(orchestrator, "run", side_effect=_raise):
        response = await client.post(
            "/api/v1/orchestration/run",
            json={"idea": valid_idea_payload()},
        )

    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = response.json()["detail"]
    assert "secret internal stack trace detail" not in detail
    assert detail == "An unexpected error occurred. Please try again."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "overrides",
    [
        {"idea_title": "ab"},  # below min_length=3
        {"idea_description": "short"},  # below min_length=10
        {"problem_statement": "short"},  # below min_length=10
    ],
)
async def test_run_orchestration_rejects_invalid_idea_payloads(
    client: AsyncClient, overrides: dict
):
    response = await client.post(
        "/api/v1/orchestration/run",
        json={"idea": valid_idea_payload(**overrides)},
    )

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


@pytest.mark.asyncio
async def test_run_orchestration_requires_idea_field(client: AsyncClient):
    response = await client.post("/api/v1/orchestration/run", json={})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
