import json
from unittest.mock import MagicMock

import pytest

from app.agents.market_research_agent import MarketResearchAgent
from app.models.agent_models import AgentInput


def make_agent(mock_skill=None) -> MarketResearchAgent:
    agent = MarketResearchAgent.__new__(MarketResearchAgent)  # bypass __init__/skill loading
    agent.skill = mock_skill or MagicMock()
    agent.llm = MagicMock()
    return agent


def make_agent_input(**overrides) -> AgentInput:
    base = dict(
        idea_title="Invoice Tracker",
        idea_description="Helps freelancers track unpaid invoices automatically.",
        problem_statement="Freelancers lose track of unpaid invoices.",
        industry="fintech",
        business_type="B2C",
        geography="global",
    )
    base.update(overrides)
    return AgentInput(**base)


# _build_prompt

def test_build_prompt_raises_when_skill_missing():
    agent = make_agent()
    agent.skill = None
    with pytest.raises(ValueError, match="Skill not loaded"):
        agent._build_prompt(make_agent_input())


def test_build_prompt_forwards_context_from_idea_validation_agent():
    mock_skill = MagicMock()
    agent = make_agent(mock_skill)

    agent._build_prompt(make_agent_input(additional_context={
        "problem_statement_summary": "Summary from prior agent",
        "falsifiable_problem_sentence": "80% of freelancers miss invoices.",
        "who_and_frequency": "Freelance designers, weekly.",
    }))

    _, kwargs = mock_skill.build_prompt.call_args
    assert kwargs["problem_statement_summary"] == "Summary from prior agent"
    assert kwargs["falsifiable_problem_sentence"] == "80% of freelancers miss invoices."
    assert kwargs["who_and_frequency"] == "Freelance designers, weekly."


def test_build_prompt_falls_back_to_alias_context_fields():
    mock_skill = MagicMock()
    agent = make_agent(mock_skill)

    agent._build_prompt(make_agent_input(additional_context={
        "problem_summary": "Alias summary",
        "customer_hypothesis": "Alias customer hypothesis",
    }))

    _, kwargs = mock_skill.build_prompt.call_args
    assert kwargs["problem_statement_summary"] == "Alias summary"
    assert kwargs["who_and_frequency"] == "Alias customer hypothesis"


def test_build_prompt_defaults_when_no_context_provided():
    mock_skill = MagicMock()
    agent = make_agent(mock_skill)

    agent._build_prompt(make_agent_input())

    _, kwargs = mock_skill.build_prompt.call_args
    assert kwargs["problem_statement_summary"] == "Freelancers lose track of unpaid invoices."
    assert kwargs["who_and_frequency"] == "Not specified"


# _parse_output — json extraction

def test_parse_output_direct_valid_json():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"market_opportunity_score": 70}))
    assert parsed["market_opportunity_score"] == 70


def test_parse_output_extracts_json_from_surrounding_text():
    agent = make_agent()
    raw = 'Result:\n```json\n{"market_opportunity_score": 65}\n```'
    parsed = agent._parse_output(raw)
    assert parsed["market_opportunity_score"] == 65


def test_parse_output_raises_json_decode_error_when_unparseable():
    agent = make_agent()
    with pytest.raises(json.JSONDecodeError):
        agent._parse_output("not json at all")


# _parse_output — field normalization

def test_parse_output_uses_market_score_alias_when_primary_missing():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"market_score": 55}))
    assert parsed["market_opportunity_score"] == 55


def test_parse_output_defaults_market_score_to_50():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({}))
    assert parsed["market_opportunity_score"] == 50


def test_parse_output_defaults_narrowness_score_to_30():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({}))
    assert parsed["audience_narrowness_score"] == 30


def test_parse_output_applies_string_field_defaults():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({}))
    assert "requires further clarification" in parsed["primary_icp_summary"]
    assert "could not be determined" in parsed["persona_summary"]
    assert "requiring further validation" in parsed["market_opportunity_summary"]


def test_parse_output_applies_array_field_defaults():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({}))
    assert parsed["secondary_segments"] == []
    assert parsed["red_flags"] == []
    assert len(parsed["target_customer_segments"]) == 1
    assert len(parsed["competitor_overview"]) == 1
    assert len(parsed["opportunity_signals"]) == 1
    assert len(parsed["risk_signals"]) == 1
    assert parsed["confidence"] == 0.5


# _parse_output — numeric clamping

def test_parse_output_clamps_market_score_above_100():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"market_opportunity_score": 300}))
    assert parsed["market_opportunity_score"] == 100


def test_parse_output_clamps_market_score_below_0():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"market_opportunity_score": -5}))
    assert parsed["market_opportunity_score"] == 0


def test_parse_output_non_numeric_market_score_falls_back_to_50():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"market_opportunity_score": "bad"}))
    assert parsed["market_opportunity_score"] == 50


def test_parse_output_clamps_narrowness_score_range():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"audience_narrowness_score": 999}))
    assert parsed["audience_narrowness_score"] == 100


def test_parse_output_non_numeric_narrowness_score_falls_back_to_30():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"audience_narrowness_score": "bad"}))
    assert parsed["audience_narrowness_score"] == 30


def test_parse_output_clamps_confidence_range():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"confidence": 10.0}))
    assert parsed["confidence"] == 1.0


def test_parse_output_non_numeric_confidence_falls_back_to_default():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"confidence": "bad"}))
    assert parsed["confidence"] == 0.5


def test_parse_output_wraps_non_list_fields_as_single_item_list():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"red_flags": "single flag string"}))
    assert parsed["red_flags"] == ["single flag string"]


def test_parse_output_empty_string_field_becomes_empty_list():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"secondary_segments": ""}))
    assert parsed["secondary_segments"] == []


# _extract_score

def test_extract_score_uses_market_opportunity_score():
    agent = make_agent()
    assert agent._extract_score({"market_opportunity_score": 82}) == 82.0


def test_extract_score_defaults_to_50_when_missing():
    agent = make_agent()
    assert agent._extract_score({}) == 50.0
