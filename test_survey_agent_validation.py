"""
Verification script for Survey Intelligence Agent, Output Validation System, and MCP Tools.
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add backend app directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from app.agents.survey_intelligence_agent import SurveyIntelligenceAgent
from app.guardrails.output_guardrails import OutputValidator
from app.llm.llm_gateway import LLMResponse
from app.mcp.mcp_host import mcp_host
from app.mcp.tool_registry import mcp_tool_registry
from app.models.agent_models import AgentInput, AgentStatus

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Mock LLM Gateway for testing agent execution
class MockLLMGateway:

    def __init__(self, response_content: str, success: bool = True):
        self.response_content = response_content
        self.success = success

    async def complete(self, request) -> LLMResponse:
        if self.success:
            return LLMResponse(
                success=True,
                content=self.response_content,
                model="test-model",
                provider="test-provider",
                tokens_input=150,
                tokens_output=200,
                total_tokens=350,
            )
        return LLMResponse(
            success=False,
            error="Mock LLM Failure",
            model="test-model",
            provider="test-provider",
        )


async def test_output_validator():
    logger.info("=== Test 1: Testing OutputValidator Engine ===")
    validator = OutputValidator()

    # 1. Valid JSON with all fields
    valid_json = json.dumps(
        {
            "survey_title": "Founder Survey",
            "survey_objective": "Test problem urgency",
            "questions": [{"question_text": "What tools do you use?", "question_type": "open_ended"}],
            "survey_quality_score": 88.5,
            "confidence": 0.9,
            "disclaimer": "Custom disclaimer statement.",
        }
    )

    res1 = validator.validate_all(
        raw_content=valid_json,
        required_fields=["survey_title", "survey_objective", "questions", "confidence"],
        range_specs={"survey_quality_score": (0.0, 100.0), "confidence": (0.0, 1.0)},
    )
    assert res1.is_valid, f"Expected valid result, got errors: {res1.errors}"
    assert res1.data["survey_quality_score"] == 88.5
    assert not res1.forbidden_advice_flagged
    logger.info("✓ Test 1.1 Passed: Valid JSON and schema fields.")

    # 2. Out-of-bounds score clamping & missing disclaimer auto-injection
    out_of_bounds_json = json.dumps(
        {
            "survey_title": "Out of Bounds Test",
            "survey_objective": "Test clamping",
            "questions": [],
            "survey_quality_score": 150.0,  # Should clamp to 100.0
            "confidence": 1.5,  # Should clamp to 1.0
        }
    )

    res2 = validator.validate_all(
        raw_content=out_of_bounds_json,
        required_fields=["survey_title", "survey_objective", "questions", "confidence"],
        range_specs={"survey_quality_score": (0.0, 100.0), "confidence": (0.0, 1.0)},
    )
    assert res2.is_valid
    assert res2.data["survey_quality_score"] == 100.0, f"Expected 100.0, got {res2.data['survey_quality_score']}"
    assert res2.data["confidence"] == 1.0, f"Expected 1.0, got {res2.data['confidence']}"
    assert "disclaimer" in res2.data, "Expected default disclaimer injection."
    logger.info("✓ Test 1.2 Passed: Score clamping and disclaimer injection.")

    # 3. Forbidden advice screening
    forbidden_json = json.dumps(
        {
            "survey_title": "Forbidden Advice Survey",
            "survey_objective": "Test forbidden advice detection",
            "questions": [],
            "confidence": 0.8,
            "disclaimer": "Guarantees $50,000 revenue in 7 days without risk.",
        }
    )

    res3 = validator.validate_all(
        raw_content=forbidden_json,
        required_fields=["survey_title", "survey_objective", "questions", "confidence"],
    )
    assert res3.forbidden_advice_flagged, "Expected forbidden advice to be flagged."
    logger.info("✓ Test 1.3 Passed: Forbidden advice pattern detected.")


async def test_survey_intelligence_agent():
    logger.info("=== Test 2: Testing SurveyIntelligenceAgent Execution ===")

    llm_payload = json.dumps(
        {
            "survey_title": "Validation Survey for AI Idea Incubator",
            "survey_objective": "Determine founder willingness to pay for rapid validation reports.",
            "survey_context": {
                "startup_summary": "AI Idea Incubator survey for validation hypothesis testing",
                "validation_scope": "Demand validation and willingness to pay",
            },
            "validation_objectives": {
                "research_objectives": ["Determine speed bottlenecks in validation"],
                "learning_goals": ["Quantify validation turnaround expectations"],
                "research_hypotheses": ["Founders spend >2 weeks on manual validation"],
            },
            "survey_strategy": {
                "survey_type": "Customer Discovery",
                "target_completion_time_minutes": 5,
                "recommended_question_count": 5,
                "data_collection_method": "Online self-administered questionnaire",
                "required_confidence_level": "95%",
            },
            "audience_definition": {
                "icp_summary": "Early-stage tech founders",
                "demographics_or_firmographics": "Seed stage, 1-10 employees",
                "eligibility_rules": ["Currently working on a tech startup"],
                "exclusion_rules": ["Non-founders"],
            },
            "sampling_strategy": {
                "recommended_sample_size": 100,
                "sampling_method": "Purposive Sampling",
                "confidence_level": "95%",
                "margin_of_error": "5%",
                "sampling_bias_risks": ["Over-indexing on tech incubators"],
            },
            "survey_structure": {
                "sections": [
                    {
                        "section_number": 1,
                        "section_title": "Current Workflow",
                        "questions": [
                            {
                                "question_id": "Q1",
                                "question_text": "How do you currently validate new product ideas?",
                                "question_type": "open_ended",
                                "options": [],
                                "is_mandatory": True,
                                "target_hypothesis": "Verify current manual process friction.",
                                "skip_logic": None,
                            }
                        ],
                    }
                ]
            },
            "question_optimization_report": {
                "anti_bias_checks_passed": True,
                "improvements_made": ["Framed questions neutrally"],
            },
            "multilingual_support": {
                "default_language": "English",
                "supported_languages": ["English"],
                "localization_notes": "Standard tech terminology",
            },
            "testing_report": {
                "question_logic_check": "Passed",
                "flow_check": "Confirmed",
                "estimated_completion_time_minutes": 5,
                "mobile_friendliness": "Optimized",
                "publishing_readiness": "Ready",
            },
            "target_audience_summary": "Early-stage tech founders",
            "questions": [
                {
                    "question_text": "How do you currently validate new product ideas?",
                    "question_type": "open_ended",
                    "target_hypothesis": "Verify current manual process friction.",
                },
                {
                    "question_text": "How many days does your validation process take?",
                    "question_type": "multiple_choice",
                    "target_hypothesis": "Quantify speed bottleneck.",
                },
            ],
            "survey_quality_score": 85.0,
            "confidence": 0.88,
        }
    )

    mock_llm = MockLLMGateway(llm_payload)
    agent = SurveyIntelligenceAgent(llm_gateway=mock_llm)

    agent_input = AgentInput(
        idea_title="AI Idea Incubator",
        idea_description="An AI platform that creates surveys and market reports for founders.",
        problem_statement="Founders spend weeks on market validation with low accuracy.",
        target_customer="Tech Startup Founders",
        additional_context={
            "problem_validation": "Validated problem statement: slow validation cycles",
            "market_research": "TAM $5B, strong growth in developer tools",
            "customer_intelligence": "ICP: B2B SaaS founders",
            "business_assumptions": "Founders will pay $50/mo for instant reports",
        },
    )

    output = await agent.run(agent_input)

    assert output.status == AgentStatus.SUCCESS, f"Agent failed: {output.error}"
    assert output.score == 85.0, f"Expected score 85.0, got {output.score}"
    assert output.confidence == 0.88
    assert "disclaimer" in output.data
    assert "survey_structure" in output.data
    assert "testing_report" in output.data
    assert output.data["testing_report"]["publishing_readiness"] == "Ready"
    assert len(output.data["questions"]) == 2
    logger.info(f"✓ Test 2 Passed: SurveyIntelligenceAgent executed successfully with score {output.score}.")


async def test_mcp_tools():
    logger.info("=== Test 3: Testing MCP Tools & Host ===")

    # 1. Test tool discovery
    tools = mcp_tool_registry.list_tools()
    assert "get_idea_details" in tools
    assert "create_survey_draft" in tools
    assert "save_agent_output" in tools
    logger.info(f"✓ Registered MCP tools: {tools}")

    # 2. Test MCP Host JSON-RPC tool calls
    req1 = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "get_idea_details", "arguments": {"idea_id": "idea_123"}},
        "id": 1001,
    }
    res1 = await mcp_host.handle_request(req1)
    assert res1.get("id") == 1001
    assert res1["result"]["idea"]["title"] == "AI Idea Validation Workspace"
    logger.info("✓ Test 3.1 Passed: MCP Host handled get_idea_details.")

    req2 = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "create_survey_draft",
            "arguments": {
                "idea_id": "idea_123",
                "survey_title": "Test Survey",
                "survey_objective": "Test Objective",
                "questions": [{"q": "Question 1"}],
            },
        },
        "id": 1002,
    }
    res2 = await mcp_host.handle_request(req2)
    assert res2["result"]["status"] == "draft"
    logger.info("✓ Test 3.2 Passed: MCP Host handled create_survey_draft.")


async def main():
    await test_output_validator()
    await test_survey_intelligence_agent()
    await test_mcp_tools()
    print("\n🎉 ALL TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(main())
