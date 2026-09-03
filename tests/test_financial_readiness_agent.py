import json
from unittest.mock import AsyncMock, MagicMock
import pytest

from app.agents.financial_readiness_agent import (
    FinancialReadinessAgent,
    DEFAULT_FINANCIAL_OUTPUT,
    VALID_CFO_DECISIONS,
)
from app.models.agent_models import AgentInput, AgentStatus
from app.llm.llm_gateway import LLMResponse
from app.orchestration.validation_engine import validation_engine, AGENT_WEIGHTS
from app.services.report_service import report_service


def make_agent(mock_skill=None) -> FinancialReadinessAgent:
    agent = FinancialReadinessAgent.__new__(FinancialReadinessAgent)
    agent.skill = mock_skill or MagicMock()
    agent.llm = MagicMock()
    return agent



def make_agent_input(**overrides) -> AgentInput:
    base = dict(
        idea_title="SaaS Metric Pulse",
        idea_description="Automated CFO intelligence and financial readiness for startups.",
        problem_statement="Founders struggle with cash runway management and financial modelling.",
        industry="FinTech / B2B SaaS",
        geography="Global",
        business_type="B2B",
        founder_validation_goal="Validate pricing power and unit economics",
    )
    base.update(overrides)
    return AgentInput(**base)


# ── _build_prompt Tests ────────────────────────────────────────────────────────

def test_build_prompt_raises_when_skill_missing():
    agent = make_agent(mock_skill=None)
    agent.skill = None
    with pytest.raises(ValueError, match="Skill not loaded"):
        agent._build_prompt(make_agent_input())


def test_build_prompt_passes_all_fields_and_context():
    mock_skill = MagicMock()
    mock_skill.build_prompt.return_value = "rendered prompt"
    agent = make_agent(mock_skill)

    agent_input = make_agent_input(
        additional_context={
            "primary_icp_summary": "Seed-stage founders with $10k-$50k MRR",
            "market_opportunity_summary": "Large underserved market in automated SMB financial analysis",
            "budget_range": "$50,000",
            "revenue_model_assumption": "Monthly SaaS subscription",
            "pricing_assumption": "$99 / month",
            "business_stage": "Early Revenue",
            "current_monthly_revenue": "$2,500/mo",
            "estimated_monthly_costs": "$1,200/mo",
        }
    )

    result = agent._build_prompt(agent_input)
    assert result == "rendered prompt"

    _, kwargs = mock_skill.build_prompt.call_args
    assert kwargs["idea_title"] == "SaaS Metric Pulse"
    assert kwargs["primary_icp_summary"] == "Seed-stage founders with $10k-$50k MRR"
    assert kwargs["market_opportunity_summary"] == "Large underserved market in automated SMB financial analysis"
    assert kwargs["budget_range"] == "$50,000"
    assert kwargs["revenue_model_assumption"] == "Monthly SaaS subscription"
    assert kwargs["pricing_assumption"] == "$99 / month"
    assert kwargs["business_stage"] == "Early Revenue"
    assert kwargs["current_monthly_revenue"] == "$2,500/mo"
    assert kwargs["estimated_monthly_costs"] == "$1,200/mo"


def test_build_prompt_defaults_when_no_additional_context():
    mock_skill = MagicMock()
    mock_skill.build_prompt.return_value = "rendered prompt"
    agent = make_agent(mock_skill)

    agent._build_prompt(make_agent_input())
    _, kwargs = mock_skill.build_prompt.call_args
    assert "Subscription" in kwargs["revenue_model_assumption"]
    assert "Early stage" in kwargs["budget_range"]


# ── _parse_output Tests ────────────────────────────────────────────────────────

def test_parse_output_direct_valid_json():
    agent = make_agent()
    sample = {
        "financial_readiness_score": 82,
        "ai_cfo_decision": "proceed",
        "cost_category_summary": ["Fixed: $2k/mo servers", "Variable: Stripe 2.9%"],
        "revenue_model_options": ["B2B SaaS $149/mo"],
        "pricing_consideration_notes": ["High WTP for finance automation"],
        "funding_gap_awareness": "Self-funding runway for 12 months",
        "financial_risk_flags": ["Slow enterprise sales cycle"],
        "unit_economics_summary": {
            "estimated_cac": "$350",
            "estimated_ltv": "$2,200",
            "ltv_to_cac_ratio": "6.2x",
            "gross_margin_pct": "84%",
            "cac_payback_months": "3.5 months",
        },
        "confidence": 0.85,
    }

    parsed = agent._parse_output(json.dumps(sample))
    assert parsed["financial_readiness_score"] == 82
    assert parsed["ai_cfo_decision"] == "proceed"
    assert len(parsed["cost_category_summary"]) == 2
    assert parsed["confidence"] == 0.85
    assert "educational_disclaimer" in parsed


def test_parse_output_markdown_wrapped_json():
    agent = make_agent()
    raw = """Here is the financial analysis:
```json
{
  "financial_readiness_score": 70,
  "ai_cfo_decision": "proceed_with_conditions",
  "funding_gap_awareness": "Need $30k buffer for marketing",
  "confidence": 0.75
}
```
"""
    parsed = agent._parse_output(raw)
    assert parsed["financial_readiness_score"] == 70
    assert parsed["ai_cfo_decision"] == "proceed_with_conditions"
    assert parsed["funding_gap_awareness"] == "Need $30k buffer for marketing"
    assert parsed["confidence"] == 0.75


def test_parse_output_raises_on_unparseable_json():
    agent = make_agent()
    with pytest.raises(json.JSONDecodeError):
        agent._parse_output("This is raw text with no valid json anywhere.")


def test_parse_output_normalizes_aliases_and_clamping():
    agent = make_agent()
    sample = {
        "financial_score": 150,  # should clamp to 100
        "cfo_decision": "HOLD AND WAIT",  # should normalize to "pause"
        "costs": ["Server costs"],
        "revenue_models": ["Transaction fees"],
        "pricing_notes": ["Keep base price low"],
        "financial_risks": ["Underestimating CAC"],
        "confidence": 95,  # percentage -> normalized to 0.95
    }

    parsed = agent._parse_output(json.dumps(sample))
    assert parsed["financial_readiness_score"] == 100
    assert parsed["ai_cfo_decision"] == "pause"
    assert parsed["cost_category_summary"] == ["Server costs"]
    assert parsed["revenue_model_options"] == ["Transaction fees"]
    assert parsed["pricing_consideration_notes"] == ["Keep base price low"]
    assert parsed["financial_risk_flags"] == ["Underestimating CAC"]
    assert parsed["confidence"] == 0.95


def test_parse_output_handles_all_cfo_decisions():
    agent = make_agent()
    for dec in VALID_CFO_DECISIONS:
        parsed = agent._parse_output(json.dumps({"ai_cfo_decision": dec}))
        assert parsed["ai_cfo_decision"] == dec


# ── run() Flow Tests ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_success():
    mock_skill = MagicMock()
    mock_skill.build_prompt.return_value = "rendered prompt"

    agent = make_agent(mock_skill)
    agent.llm.complete = AsyncMock(

        return_value=LLMResponse(
            provider="google",
            success=True,
            content=json.dumps({
                "financial_readiness_score": 78,
                "ai_cfo_decision": "proceed",
                "cost_category_summary": ["Hosting", "APIs"],
                "revenue_model_options": ["SaaS"],
                "confidence": 0.8,
            }),
            tokens_input=120,
            tokens_output=80,
            model="gemini-2.0-flash",
        )

    )

    output = await agent.run(make_agent_input())
    assert output.status == AgentStatus.SUCCESS
    assert output.score == 78
    assert output.confidence == 0.8
    assert output.data["ai_cfo_decision"] == "proceed"
    assert output.tokens_input == 120
    assert output.tokens_output == 80


# ── Validation Engine Integration Tests ────────────────────────────────────────

def test_validation_engine_weights_and_insights_with_financial_agent():
    assert "financial_readiness_agent" in AGENT_WEIGHTS
    assert AGENT_WEIGHTS["financial_readiness_agent"] == 0.25

    aggregated = {
        "agent_results": {
            "idea_validation_agent": {
                "score": 80,
                "confidence": 0.8,
                "data": {
                    "problem_clarity_score": 80,
                    "problem_statement_summary": "Invoicing takes too long.",
                },
            },
            "market_research_agent": {
                "score": 75,
                "confidence": 0.7,
                "data": {
                    "market_opportunity_score": 75,
                    "primary_icp_summary": "Small business owners",
                },
            },
            "survey_intelligence_agent": {
                "score": 85,
                "confidence": 0.85,
                "data": {
                    "survey_title": "Invoicing Pain Survey",
                    "questions": [{"question_text": "How often do you invoice?"}],
                },
            },
            "financial_readiness_agent": {
                "score": 90,
                "confidence": 0.9,
                "data": {
                    "financial_readiness_score": 90,
                    "ai_cfo_decision": "proceed",
                    "revenue_model_options": ["B2B SaaS Subscription"],
                    "financial_risk_flags": ["High initial CAC"],
                    "priority_actions": ["Validate pricing sensitivity"],
                },
            },
        }
    }

    result = validation_engine.calculate(aggregated)
    # Expected weighted score: (80*0.25 + 75*0.25 + 85*0.25 + 90*0.25) / 1.0 = 82.5
    assert result["validation_score"] == 82.5
    assert any("AI CFO Decision: Proceed" in s for s in result["strengths"])
    assert any("Monetization Strategy: B2B SaaS Subscription" in s for s in result["strengths"])
    assert any("High initial CAC" in r for r in result["risks"])
    assert any("Validate pricing sensitivity" in rec for rec in result["recommendations"])


# ── Report Service Integration Tests ───────────────────────────────────────────

def test_report_service_financial_readiness_blocks():
    validation_data = {
        "validation_score": 85,
        "verdict": "build",
        "agent_results": {
            "financial_readiness_agent": {
                "data": {
                    "financial_readiness_score": 85,
                    "ai_cfo_decision": "proceed",
                    "confidence": 0.8,
                    "executive_summary": "Strong unit economics and pricing power.",
                    "funding_gap_awareness": "Self-funded runway of 18 months.",
                    "cost_category_summary": ["Compute: $500/mo"],
                    "revenue_model_options": ["SaaS Tiered"],
                    "pricing_consideration_notes": ["$49 starter, $199 pro"],
                    "unit_economics_summary": {
                        "gross_margin_pct": "82%",
                        "ltv_to_cac_ratio": "4.5x",
                    },
                    "financial_risk_flags": ["Long sales cycle"],
                    "priority_actions": ["Test pricing page"],
                }
            }
        }
    }

    blocks = report_service._financial_readiness_blocks(validation_data["agent_results"])
    assert len(blocks) > 0
    section_block = blocks[0]
    assert section_block["type"] == "section"
    assert "Financial Readiness & AI CFO Analysis" in section_block["title"]

    titles = [b.get("title") for b in blocks if b.get("title")]
    assert "Cost Structure Summary" in titles
    assert "Revenue Model Options" in titles
    assert "Financial Risk Flags" in titles