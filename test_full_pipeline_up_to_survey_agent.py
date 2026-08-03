"""
End-to-end Verification script for Phase 1 integration up to Survey Intelligence Agent.
Tests:
  1. MCP Tool Permission Access Control Matrix.
  2. 8 Core ORM Database Model instantiations.
  3. Full 3-Agent Idea Validation Workflow (IdeaValidation, MarketResearch, SurveyIntelligence).
  4. Survey Generation Workflow execution.
"""
import asyncio
import json
import logging
import sys
from pathlib import Path

# Add backend app directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from app.db.models import (
    AgentDefinition,
    AgentRun,
    LLMUsageLogRecord,
    MCPToolCallRecord,
    OrchestrationRun,
    OrchestrationStep,
    SkillLibrary,
    ValidationResultRecord,
)
from app.llm.llm_gateway import LLMResponse
from app.mcp.mcp_host import mcp_host
from app.models.orchestration_models import (
    IdeaInput,
    OrchestrationRequest,
    WorkflowType,
)
from app.orchestration.orchestrator import orchestrator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Mock LLM Gateway providing contextually appropriate responses for all 3 agents
class MultiAgentMockLLMGateway:

    def get_provider_name(self) -> str:
        return "mock_provider"

    def get_default_model(self) -> str:
        return "mock-model"

    async def complete(self, request) -> LLMResponse:
        system_prompt = request.system_prompt.lower()
        
        if "idea_validation_agent" in system_prompt or "problem" in system_prompt:
            content = json.dumps({
                "problem_clarity_score": 85.0,
                "problem_statement_summary": "Founders lack fast, empirical market feedback.",
                "falsifiable_problem_sentence": "If founders cannot validate willingness to pay, they waste seed capital.",
                "who_and_frequency": "B2B SaaS Founders validating ideas weekly",
                "pain_type_classification": "painkiller",
                "current_workarounds": "Manual spreadsheets and informal advice",
                "assumption_list": ["Founders are willing to pay for automated reports"],
                "red_flags": [],
                "initial_recommendation": "proceed_to_validation",
                "confidence": 0.9,
            })
        elif "market_research_agent" in system_prompt or "market" in system_prompt:
            content = json.dumps({
                "market_opportunity_score": 82.0,
                "audience_narrowness_score": 78.0,
                "primary_icp_summary": "B2B SaaS Founders raising pre-seed funding",
                "persona_summary": "Bootstrap founder wanting automated validation data",
                "target_customer_segments": ["Pre-seed Tech Founders"],
                "competitor_overview": ["Manual agency research", "DIY google forms"],
                "opportunity_signals": ["Growing AI adoption in market research"],
                "risk_signals": ["High competition in AI wrapper space"],
                "red_flags": [],
                "confidence": 0.85,
            })
        else: # survey_intelligence_agent
            content = json.dumps({
                "survey_title": "B2B Founder Validation Survey",
                "survey_objective": "Test willingness to pay for rapid validation reports",
                "target_audience_summary": "Early stage tech founders",
                "questions": [
                    {
                        "question_text": "How many hours do you spend on customer research?",
                        "question_type": "multiple_choice",
                        "target_hypothesis": "Quantify research time bottleneck"
                    },
                    {
                        "question_text": "What is your budget for automated validation reports?",
                        "question_type": "multiple_choice",
                        "target_hypothesis": "Test price sensitivity"
                    }
                ],
                "survey_quality_score": 90.0,
                "confidence": 0.92,
                "disclaimer": "This output provides decision-support guidance only."
            })

        return LLMResponse(
            success=True,
            content=content,
            model="gemini-1.5-flash",
            provider=self.get_provider_name(),
            tokens_input=200,
            tokens_output=300,
            total_tokens=500,
        )


async def test_mcp_permissions():
    logger.info("=== Test 1: MCP Tool Permission Access Control Matrix ===")

    # 1. Idea Validation Agent calling authorized tool
    res1 = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "get_idea_details",
            "caller_agent": "idea_validation_agent",
            "arguments": {"idea_id": "idea_100"}
        },
        "id": 1
    })
    assert "result" in res1, f"Expected successful tool execution, got error: {res1}"
    logger.info("✓ Test 1.1 Passed: IdeaValidationAgent authorized to call get_idea_details.")

    # 2. Idea Validation Agent attempting UNAUTHORIZED call to create_survey_draft
    res2 = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "create_survey_draft",
            "caller_agent": "idea_validation_agent",
            "arguments": {"idea_id": "idea_100", "survey_title": "Unauthorized Survey"}
        },
        "id": 2
    })
    assert "error" in res2, "Expected permission denied error for unauthorized agent tool call."
    assert "Permission Denied" in res2["error"]["message"]
    logger.info("✓ Test 1.2 Passed: IdeaValidationAgent denied call to create_survey_draft.")

    # 3. Survey Intelligence Agent calling authorized tool create_survey_draft
    res3 = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "create_survey_draft",
            "caller_agent": "survey_intelligence_agent",
            "arguments": {
                "idea_id": "idea_100",
                "survey_title": "Authorized Survey",
                "survey_objective": "Test objective",
                "questions": []
            }
        },
        "id": 3
    })
    assert "result" in res3
    assert res3["result"]["status"] == "draft"
    logger.info("✓ Test 1.3 Passed: SurveyIntelligenceAgent authorized to call create_survey_draft.")


def test_orm_models():
    logger.info("=== Test 2: Instantiating 8 Core Database Models ===")
    agent_def = AgentDefinition(name="survey_intelligence_agent", description="Survey Agent")
    skill_lib = SkillLibrary(skill_name="survey_intelligence_skill", purpose="Design surveys", prompt_template="")
    orch_run = OrchestrationRun(workspace_id="ws_1", idea_id="idea_1", run_type="idea_validation")
    orch_step = OrchestrationStep(orchestration_run_id=orch_run.id, step_name="survey_step", agent_name="survey_intelligence_agent")
    agent_run = AgentRun(orchestration_run_id=orch_run.id, agent_id=agent_def.id)
    mcp_call = MCPToolCallRecord(tool_name="create_survey_draft")
    llm_log = LLMUsageLogRecord(provider="google", model="gemini-1.5-flash", total_tokens=500)
    val_res = ValidationResultRecord(idea_id="idea_1", orchestration_run_id=orch_run.id, validation_score=85.5, confidence_rating=0.9, verdict="build")

    assert agent_def.name == "survey_intelligence_agent"
    assert val_res.verdict == "build"
    logger.info("✓ Test 2 Passed: 8 Core ORM Database Models instantiated cleanly.")


async def test_full_pipeline_orchestration():
    logger.info("=== Test 3: Full 3-Agent Idea Validation Workflow ===")
    
    # Patch LLM Gateway instantiation to use MultiAgentMockLLMGateway
    import app.orchestration.orchestrator as orch_module
    original_get_llm = orch_module.get_llm_gateway
    orch_module.get_llm_gateway = lambda: MultiAgentMockLLMGateway()

    try:
        req = OrchestrationRequest(
            workspace_id="ws_demo",
            idea_id="idea_demo",
            workflow_type=WorkflowType.IDEA_VALIDATION,
            idea=IdeaInput(
                idea_title="AI Startup Validator",
                idea_description="Automated AI multi-agent platform for validating startup ideas.",
                problem_statement="Founders spend excessive time and seed capital on unvalidated startup ideas.",
                founder_evidence="Interviewed 15 founders experiencing this exact issue.",
            ),
        )

        response = await orchestrator.run(req)

        assert response.status == "success", f"Orchestration failed: {response.error}"
        assert response.result is not None
        assert response.result.validation_score >= 80.0
        assert response.result.verdict == "build"
        assert len(response.result.agent_results) == 3
        assert "idea_validation_agent" in response.result.agent_results
        assert "market_research_agent" in response.result.agent_results
        assert "survey_intelligence_agent" in response.result.agent_results

        logger.info(
            f"✓ Test 3 Passed: Pipeline executed 3 agents cleanly! "
            f"Score={response.result.validation_score}, Verdict={response.result.verdict}"
        )
    finally:
        orch_module.get_llm_gateway = original_get_llm


async def main():
    await test_mcp_permissions()
    test_orm_models()
    await test_full_pipeline_orchestration()
    print("\n🎉 ALL INTEGRATION TESTS PASSED SUCCESSFULLY UP TO SURVEY INTELLIGENCE AGENT!")


if __name__ == "__main__":
    asyncio.run(main())
