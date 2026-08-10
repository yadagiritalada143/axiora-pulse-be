import json
from unittest.mock import MagicMock

import pytest

from app.agents.idea_validation_agent import IdeaValidationAgent
from app.models.agent_models import AgentInput


def make_agent(mock_skill=None) -> IdeaValidationAgent:
    agent = IdeaValidationAgent.__new__(IdeaValidationAgent)  # bypass __init__/skill loading
    agent.skill = mock_skill or MagicMock()
    agent.llm = MagicMock()
    return agent


def make_agent_input(**overrides) -> AgentInput:
    base = dict(
        idea_title="Invoice Tracker",
        idea_description="Helps freelancers track unpaid invoices automatically.",
        problem_statement="Freelancers lose track of unpaid invoices.",
        industry="fintech",
        geography="global",
        founder_validation_goal="validate my idea",
    )
    base.update(overrides)
    return AgentInput(**base)


# _build_prompt

def test_build_prompt_raises_when_skill_missing():
    agent = make_agent(mock_skill=None)
    agent.skill = None
    with pytest.raises(ValueError, match="Skill not loaded"):
        agent._build_prompt(make_agent_input())


def test_build_prompt_passes_founder_evidence_when_provided():
    mock_skill = MagicMock()
    mock_skill.build_prompt.return_value = "rendered prompt"
    agent = make_agent(mock_skill)

    result = agent._build_prompt(make_agent_input(founder_evidence="Ran 20 customer interviews"))

    assert result == "rendered prompt"
    _, kwargs = mock_skill.build_prompt.call_args
    assert kwargs["founder_evidence"] == "Ran 20 customer interviews"


def test_build_prompt_falls_back_to_additional_context_evidence():
    mock_skill = MagicMock()
    agent = make_agent(mock_skill)

    agent._build_prompt(
        make_agent_input(additional_context={"founder_evidence": "From context dict"})
    )
    _, kwargs = mock_skill.build_prompt.call_args
    assert kwargs["founder_evidence"] == "From context dict"


def test_build_prompt_default_evidence_when_none_provided():
    mock_skill = MagicMock()
    agent = make_agent(mock_skill)

    agent._build_prompt(make_agent_input())
    _, kwargs = mock_skill.build_prompt.call_args
    assert "No explicit evidence" in kwargs["founder_evidence"]


# _parse_output — json extraction

def test_parse_output_direct_valid_json():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"problem_clarity_score": 80, "confidence": 0.7}))
    assert parsed["problem_clarity_score"] == 80


def test_parse_output_extracts_json_from_surrounding_text():
    agent = make_agent()
    raw = 'Here is my analysis:\n```json\n{"problem_clarity_score": 75}\n```'
    parsed = agent._parse_output(raw)
    assert parsed["problem_clarity_score"] == 75


def test_parse_output_raises_json_decode_error_when_unparseable():
    agent = make_agent()
    with pytest.raises(json.JSONDecodeError):
        agent._parse_output("completely unparseable text")


# _parse_output — field normalization & aliasing

def test_parse_output_uses_idea_clarity_score_alias_when_primary_missing():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"idea_clarity_score": 65}))
    assert parsed["problem_clarity_score"] == 65
    assert parsed["idea_clarity_score"] == 65


def test_parse_output_defaults_score_to_40_when_absent():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({}))
    assert parsed["problem_clarity_score"] == 40


def test_parse_output_normalizes_summary_aliases():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"problem_summary": "Alt summary"}))
    assert parsed["problem_statement_summary"] == "Alt summary"
    assert parsed["problem_summary"] == "Alt summary"


def test_parse_output_default_summary_when_missing():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({}))
    assert "Unable to generate" in parsed["problem_statement_summary"]


def test_parse_output_normalizes_who_and_frequency_aliases():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"customer_hypothesis": "Freelance designers"}))
    assert parsed["who_and_frequency"] == "Freelance designers"
    assert parsed["customer_hypothesis"] == "Freelance designers"


def test_parse_output_normalizes_assumptions_aliases():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"key_assumptions": ["A1", "A2"]}))
    assert parsed["assumption_list"] == ["A1", "A2"]
    assert parsed["key_assumptions"] == ["A1", "A2"]


def test_parse_output_default_assumptions_when_missing():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({}))
    assert len(parsed["assumption_list"]) == 2


def test_parse_output_wraps_non_list_assumptions_as_single_item_list():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"assumption_list": "single string assumption"}))
    assert parsed["assumption_list"] == ["single string assumption"]


# _parse_output — defaults for analysis 1 fields

def test_parse_output_applies_defaults_for_missing_fields():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({}))

    assert parsed["falsifiable_problem_sentence"] == "Problem statement requires further definition."
    assert parsed["pain_type_classification"] == "Unclear"
    assert parsed["current_workarounds"].startswith("Not specified")
    assert parsed["red_flags"] == []
    assert parsed["initial_recommendation"] == "needs_clarification"
    assert parsed["confidence"] == 0.4
    assert "decision-support guidance only" in parsed["disclaimer"]


# _parse_output — numeric clamping

def test_parse_output_clamps_score_above_100():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"problem_clarity_score": 250}))
    assert parsed["problem_clarity_score"] == 100


def test_parse_output_clamps_score_below_0():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"problem_clarity_score": -20}))
    assert parsed["problem_clarity_score"] == 0


def test_parse_output_non_numeric_score_falls_back_to_40():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"problem_clarity_score": "not-a-number"}))
    assert parsed["problem_clarity_score"] == 40


def test_parse_output_non_numeric_confidence_falls_back_to_default():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"confidence": "invalid"}))
    assert parsed["confidence"] == 0.4


def test_parse_output_clamps_confidence_above_1():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"confidence": 5.0}))
    assert parsed["confidence"] == 1.0


# _parse_output — enum validation

@pytest.mark.parametrize("raw_pain_type,expected", [
    ("painkiller", "Painkiller"),
    ("VITAMIN", "Vitamin"),
    ("unclear", "Unclear"),
    ("garbage-value", "Unclear"),
])
def test_parse_output_validates_pain_type_enum(raw_pain_type, expected):
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"pain_type_classification": raw_pain_type}))
    assert parsed["pain_type_classification"] == expected


@pytest.mark.parametrize("raw_rec,expected", [
    ("proceed_to_validation", "proceed_to_validation"),
    ("Reduce Scope", "reduce_scope"),
    ("pivot", "pivot"),
    ("nonsense_value", "needs_clarification"),
])
def test_parse_output_validates_recommendation_enum(raw_rec, expected):
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"initial_recommendation": raw_rec}))
    assert parsed["initial_recommendation"] == expected


def test_parse_output_wraps_non_list_red_flags():
    agent = make_agent()
    parsed = agent._parse_output(json.dumps({"red_flags": "single flag"}))
    assert parsed["red_flags"] == ["single flag"]


# _extract_score

def test_extract_score_uses_problem_clarity_score():
    agent = make_agent()
    assert agent._extract_score({"problem_clarity_score": 77}) == 77.0


def test_extract_score_falls_back_to_idea_clarity_score():
    agent = make_agent()
    assert agent._extract_score({"idea_clarity_score": 33}) == 33.0


def test_extract_score_defaults_to_40_when_both_missing():
    agent = make_agent()
    assert agent._extract_score({}) == 40.0
