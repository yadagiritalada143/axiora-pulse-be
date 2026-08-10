import json
from unittest.mock import MagicMock

import pytest

from app.agents.survey_intelligence_agent import (
    DEFAULT_SURVEY_OUTPUT,
    SurveyIntelligenceAgent,
)
from app.guardrails.output_guardrails import OutputValidator
from app.models.agent_models import AgentInput


def make_agent(mock_skill=None) -> SurveyIntelligenceAgent:
    agent = SurveyIntelligenceAgent.__new__(SurveyIntelligenceAgent)  # bypass __init__/skill loading
    agent.skill = mock_skill or MagicMock()
    agent.llm = MagicMock()
    agent.validator = OutputValidator()
    return agent


def make_agent_input(**overrides) -> AgentInput:
    base = dict(
        idea_title="Invoice Tracker",
        idea_description="Helps freelancers track unpaid invoices automatically.",
        problem_statement="Freelancers lose track of unpaid invoices.",
        founder_validation_goal="Validate willingness to pay",
    )
    base.update(overrides)
    return AgentInput(**base)


def minimal_valid_survey_payload(**overrides) -> dict:
    payload = {
        "survey_title": "Custom Survey Title",
        "survey_objective": "Custom objective",
        "questions": [{"question_text": "Q1?", "question_type": "open_ended"}],
        "confidence": 0.8,
        "survey_quality_score": 88,
    }
    payload.update(overrides)
    return payload


# _build_prompt

def test_build_prompt_raises_when_skill_missing():
    agent = make_agent()
    agent.skill = None
    with pytest.raises(ValueError, match="Skill not loaded"):
        agent._build_prompt(make_agent_input())


def test_build_prompt_uses_target_customer_and_context_overrides():
    mock_skill = MagicMock()
    agent = make_agent(mock_skill)

    agent._build_prompt(make_agent_input(
        target_customer="Freelance designers",
        additional_context={
            "market_research": "Growing gig economy",
            "founder_evidence": "Ran 10 interviews",
        },
    ))

    _, kwargs = mock_skill.build_prompt.call_args
    assert kwargs["target_customer"] == "Freelance designers"
    assert kwargs["market_research"] == "Growing gig economy"
    assert kwargs["founder_info"] == "Ran 10 interviews"


def test_build_prompt_defaults_when_no_context_provided():
    mock_skill = MagicMock()
    agent = make_agent(mock_skill)

    agent._build_prompt(make_agent_input())

    _, kwargs = mock_skill.build_prompt.call_args
    assert kwargs["target_customer"] == "Prospective target customer base"
    assert kwargs["problem_validation"] == "Not provided"
    assert kwargs["founder_info"] == "Not provided"
    assert kwargs["market_research"] == "Not provided"
    assert kwargs["customer_intelligence"] == "Not provided"
    assert kwargs["business_assumptions"] == "Not provided"


# _parse_output — full validation pipeline

def test_parse_output_valid_payload_preserved():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps(minimal_valid_survey_payload()))

    assert parsed["survey_title"] == "Custom Survey Title"
    assert parsed["survey_quality_score"] == 88
    assert parsed["confidence"] == 0.8
    assert len(parsed["questions"]) == 1


def test_parse_output_invalid_json_falls_back_to_defaults():
    agent = make_agent()
    parsed = agent._parse_output("not valid json at all")

    # validate_all() applies default_values for every required field when JSON parse fails... actually
    # a parse failure short-circuits with is_valid=False and empty data — verify graceful fallback occurs.
    assert parsed.get("questions") == DEFAULT_SURVEY_OUTPUT["questions"]
    assert parsed.get("survey_structure") == DEFAULT_SURVEY_OUTPUT["survey_structure"]


def test_parse_output_missing_required_fields_use_defaults():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"survey_title": "Only Title Present"}))

    assert parsed["survey_title"] == "Only Title Present"
    # Other required fields backfilled from DEFAULT_SURVEY_OUTPUT via default_values
    assert parsed["survey_objective"] == DEFAULT_SURVEY_OUTPUT["survey_objective"]
    assert parsed["questions"] == DEFAULT_SURVEY_OUTPUT["questions"]


def test_parse_output_normalizes_score_alias():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps(minimal_valid_survey_payload(
        survey_quality_score=None, score=55,
    )))
    assert parsed["survey_quality_score"] == 55.0


def test_parse_output_defaults_score_when_no_alias_present():
    agent = make_agent()
    payload = minimal_valid_survey_payload()
    del payload["survey_quality_score"]
    parsed = agent._parse_output(json.dumps(payload))
    # validate_all() backfills from DEFAULT_SURVEY_OUTPUT (75.0) before the agent's own 70.0 fallback runs
    assert parsed["survey_quality_score"] == 75.0


def test_parse_output_replaces_non_list_questions_with_default():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps(minimal_valid_survey_payload(questions="not a list")))
    assert parsed["questions"] == DEFAULT_SURVEY_OUTPUT["questions"]


def test_parse_output_replaces_invalid_survey_structure_with_default():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps(minimal_valid_survey_payload(survey_structure="not a dict")))
    assert parsed["survey_structure"] == DEFAULT_SURVEY_OUTPUT["survey_structure"]


def test_parse_output_clamps_score_range():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps(minimal_valid_survey_payload(survey_quality_score=500)))
    assert parsed["survey_quality_score"] == 100.0


def test_parse_output_clamps_confidence_range():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps(minimal_valid_survey_payload(confidence=5.0)))
    assert parsed["confidence"] == 1.0


def test_parse_output_injects_disclaimer():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps(minimal_valid_survey_payload()))
    assert "disclaimer" in parsed
    assert parsed["disclaimer"]


# _extract_score

def test_extract_score_uses_survey_quality_score():
    agent = make_agent()
    assert agent._extract_score({"survey_quality_score": 91}) == 91.0


def test_extract_score_falls_back_to_score_alias():
    agent = make_agent()
    assert agent._extract_score({"score": 60}) == 60.0


def test_extract_score_defaults_to_70_when_missing():
    agent = make_agent()
    assert agent._extract_score({}) == 70.0


def test_extract_score_defaults_to_70_on_non_numeric_value():
    agent = make_agent()
    assert agent._extract_score({"survey_quality_score": "not-a-number"}) == 70.0
