"""
Verification script for all 5 Phase 1 internal MCP Servers, tools, and resources.
"""
import asyncio
import logging
import sys
from pathlib import Path

# Add backend app directory to sys.path
sys.path.insert(0, str(Path(__file__).parent))

from app.mcp.mcp_host import mcp_host
from app.mcp.tool_registry import mcp_tool_registry

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_mcp_servers_suite():
    logger.info("=== Starting 5 Phase 1 MCP Servers Test Suite ===")

    # 1. Test Registry Discovery
    tools = mcp_tool_registry.list_tools()
    logger.info(f"Registered MCP Tools ({len(tools)} total): {tools}")
    assert len(tools) == 17, f"Expected 17 tools across 5 servers, got {len(tools)}"

    schemes = mcp_tool_registry.list_resource_schemes()
    logger.info(f"Registered Resource Schemes: {schemes}")
    assert len(schemes) == 5

    # ── Server 1: Idea Context Server ──────────────────────────────────────────
    logger.info("--- Testing MCP Server 1: Idea Context Server ---")
    res1 = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "get_idea_details", "arguments": {"idea_id": "idea_001"}},
        "id": 1
    })
    assert res1["result"]["idea"]["title"] == "AI Idea Validation Workspace"

    res1_status = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "update_idea_status", "arguments": {"idea_id": "idea_001", "status": "active"}},
        "id": 2
    })
    assert res1_status["result"]["new_status"] == "active"

    res1_goal = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "get_founder_validation_goal", "arguments": {"idea_id": "idea_001"}},
        "id": 3
    })
    assert "founder_validation_goal" in res1_goal["result"]

    res1_resource = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "resources/read",
        "params": {"uri": "idea://brief/idea_001"},
        "id": 4
    })
    assert "title" in res1_resource["result"]["content"]

    # ── Server 2: Agent Output Server ──────────────────────────────────────────
    logger.info("--- Testing MCP Server 2: Agent Output Server ---")
    res2_save = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "save_agent_output",
            "arguments": {
                "agent_name": "idea_validation_agent",
                "idea_id": "idea_001",
                "score": 85.0,
                "data": {"problem_clarity": 85}
            }
        },
        "id": 5
    })
    assert res2_save["result"]["status"] == "saved"

    res2_get = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "get_agent_outputs", "arguments": {"idea_id": "idea_001"}},
        "id": 6
    })
    assert res2_get["result"]["count"] >= 1

    res2_latest = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "get_latest_validation_result", "arguments": {"idea_id": "idea_001"}},
        "id": 7
    })
    assert res2_latest["result"]["latest_result"]["score"] == 85.0

    res2_resource = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "resources/read",
        "params": {"uri": "agent://history/idea_001"},
        "id": 8
    })
    assert len(res2_resource["result"]["content"]["history"]) >= 1

    # ── Server 3: Survey Server ────────────────────────────────────────────────
    logger.info("--- Testing MCP Server 3: Survey Server ---")
    res3_create = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "create_survey_draft",
            "arguments": {
                "idea_id": "idea_001",
                "survey_title": "Validation Survey",
                "survey_objective": "Test pain points",
                "questions": [{"question_text": "What is your main challenge?"}]
            }
        },
        "id": 9
    })
    survey_id = res3_create["result"]["survey_id"]
    assert res3_create["result"]["status"] == "draft"

    res3_pub = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "publish_survey", "arguments": {"survey_id": survey_id}},
        "id": 10
    })
    assert res3_pub["result"]["status"] == "published"

    res3_q = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "get_survey_questions", "arguments": {"survey_id": survey_id}},
        "id": 11
    })
    assert len(res3_q["result"]["questions"]) == 1

    res3_resp = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "get_survey_responses", "arguments": {"survey_id": "survey_default"}},
        "id": 12
    })
    assert res3_resp["result"]["response_count"] == 2

    res3_resource = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "resources/read",
        "params": {"uri": "survey://schema/survey_default"},
        "id": 13
    })
    assert "questions" in res3_resource["result"]["content"]

    # ── Server 4: Analytics Server ─────────────────────────────────────────────
    logger.info("--- Testing MCP Server 4: Analytics Server ---")
    res4_count = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "calculate_response_count", "arguments": {"survey_id": "survey_default"}},
        "id": 14
    })
    assert res4_count["result"]["response_count"] == 2

    res4_interest = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "calculate_interest_score", "arguments": {"survey_id": "survey_default"}},
        "id": 15
    })
    assert res4_interest["result"]["interest_score"] > 0

    res4_pains = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "summarize_pain_points", "arguments": {"survey_id": "survey_default"}},
        "id": 16
    })
    assert len(res4_pains["result"]["top_pain_points"]) > 0

    res4_wtp = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "summarize_willingness_to_pay", "arguments": {"survey_id": "survey_default"}},
        "id": 17
    })
    assert res4_wtp["result"]["average_wtp_usd"] == 175.0

    res4_resource = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "resources/read",
        "params": {"uri": "analytics://summary/survey_default"},
        "id": 18
    })
    assert res4_resource["result"]["content"]["average_wtp"] == 175.0

    # ── Server 5: Report Server ────────────────────────────────────────────────
    logger.info("--- Testing MCP Server 5: Report Server ---")
    res5_gen = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "generate_validation_report",
            "arguments": {"idea_id": "idea_001", "title": "Final Master Report"}
        },
        "id": 19
    })
    report_id = res5_gen["result"]["report_id"]
    assert res5_gen["result"]["status"] == "generating"

    res5_status = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "get_report_status", "arguments": {"report_id": report_id}},
        "id": 20
    })
    assert res5_status["result"]["status"] == "generating"

    res5_dl = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {"name": "get_report_download_link", "arguments": {"report_id": report_id}},
        "id": 21
    })
    assert "download_url" in res5_dl["result"]

    res5_resource = await mcp_host.handle_request({
        "jsonrpc": "2.0",
        "method": "resources/read",
        "params": {"uri": "report://template/standard_v1"},
        "id": 22
    })
    assert len(res5_resource["result"]["content"]["sections"]) > 0

    print("\n🎉 ALL 5 MCP SERVERS TEST SUITE PASSED SUCCESSFULLY (17 Tools & 5 Resource Schemes verified)!")


if __name__ == "__main__":
    asyncio.run(test_mcp_servers_suite())
