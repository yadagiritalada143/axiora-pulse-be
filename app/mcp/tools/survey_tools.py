"""
MCP Server 3: Survey Server
──────────────────────────────────────────────────────────────────────────────
Provides tools and resources for creating, publishing, and reading validation surveys.

Tools:
  - create_survey_draft
  - publish_survey
  - get_survey_questions
  - get_survey_responses

Resources:
  - survey://schema/{survey_id}
  - survey://responses/{survey_id}
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Simulated in-memory store for survey data
_SURVEYS_STORE: dict[str, dict[str, Any]] = {
    "survey_default": {
        "survey_id": "survey_default",
        "idea_id": "idea_default",
        "survey_title": "Default Validation Survey",
        "survey_objective": "Test early adopter interest and workarounds",
        "status": "published",
        "questions": [
            {
                "question_id": "q1",
                "question_text": "What is your biggest operational pain point?",
                "question_type": "open_ended",
                "target_hypothesis": "Problem severity",
            },
            {
                "question_id": "q2",
                "question_text": "How much would you pay for a solution that saves 10 hours/week?",
                "question_type": "multiple_choice",
                "target_hypothesis": "Willingness to pay",
            },
        ],
        "responses": [
            {"respondent_id": "r1", "answers": {"q1": "Manual data entry takes too long", "q2": "$100/mo"}},
            {"respondent_id": "r2", "answers": {"q1": "Unclear market positioning", "q2": "$250/mo"}},
        ],
    }
}


# ── MCP Tools ──────────────────────────────────────────────────────────────────

async def create_survey_draft(
    idea_id: str, survey_title: str, survey_objective: str, questions: list[dict[str, Any]]
) -> dict[str, Any]:
    """MCP Tool: create_survey_draft"""
    logger.info(f"[MCP Survey Server] create_survey_draft('{survey_title}' for idea_id='{idea_id}')")
    survey_id = f"survey_{idea_id}_{len(_SURVEYS_STORE) + 1}"
    survey_record = {
        "survey_id": survey_id,
        "idea_id": idea_id,
        "survey_title": survey_title,
        "survey_objective": survey_objective,
        "status": "draft",
        "questions": questions,
        "responses": [],
    }
    _SURVEYS_STORE[survey_id] = survey_record
    return {"success": True, "survey_id": survey_id, "status": "draft"}


async def publish_survey(survey_id: str) -> dict[str, Any]:
    """MCP Tool: publish_survey"""
    logger.info(f"[MCP Survey Server] publish_survey(survey_id='{survey_id}')")
    survey = _SURVEYS_STORE.get(survey_id, _SURVEYS_STORE["survey_default"])
    survey["status"] = "published"
    return {"success": True, "survey_id": survey_id, "status": "published"}


async def get_survey_questions(survey_id: str) -> dict[str, Any]:
    """MCP Tool: get_survey_questions"""
    logger.info(f"[MCP Survey Server] get_survey_questions(survey_id='{survey_id}')")
    survey = _SURVEYS_STORE.get(survey_id, _SURVEYS_STORE["survey_default"])
    return {
        "success": True,
        "survey_id": survey_id,
        "survey_title": survey.get("survey_title", ""),
        "questions": survey.get("questions", []),
    }


async def get_survey_responses(survey_id: str) -> dict[str, Any]:
    """MCP Tool: get_survey_responses"""
    logger.info(f"[MCP Survey Server] get_survey_responses(survey_id='{survey_id}')")
    survey = _SURVEYS_STORE.get(survey_id, _SURVEYS_STORE["survey_default"])
    return {
        "success": True,
        "survey_id": survey_id,
        "response_count": len(survey.get("responses", [])),
        "responses": survey.get("responses", []),
    }


# ── MCP Resource Resolver ─────────────────────────────────────────────────────

async def get_survey_resource(uri: str) -> dict[str, Any]:
    """
    MCP Resource Handler: survey://
    URIs:
      - survey://schema/{survey_id}
      - survey://responses/{survey_id}
    """
    logger.info(f"[MCP Survey Server] Reading resource uri='{uri}'")
    parts = uri.replace("survey://", "").split("/")
    resource_type = parts[0] if parts else "schema"
    survey_id = parts[1] if len(parts) > 1 else "survey_default"

    survey = _SURVEYS_STORE.get(survey_id, _SURVEYS_STORE["survey_default"])

    if resource_type == "schema":
        content = {
            "survey_id": survey["survey_id"],
            "title": survey["survey_title"],
            "objective": survey["survey_objective"],
            "questions": survey["questions"],
        }
    elif resource_type == "responses":
        content = {
            "survey_id": survey["survey_id"],
            "responses": survey["responses"],
        }
    else:
        content = survey

    return {"uri": uri, "mimeType": "application/json", "content": content}
