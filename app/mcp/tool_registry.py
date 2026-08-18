"""
MCP Tool & Resource Registry
──────────────────────────────────────────────────────────────────────────────
Central registry for Model Context Protocol (MCP) tools and resources across
all 5 Phase 1 internal MCP servers:
  1. Idea Context Server
  2. Agent Output Server
  3. Survey Server
  4. Analytics Server
  5. Report Server

Includes strict Agent Permission Model authorization checking.
"""
import inspect
import logging
from typing import Any, Callable, Awaitable

# Server 1: Idea Context
from app.mcp.tools.idea_tools import (
    get_idea_details,
    update_idea_status,
    get_founder_validation_goal,
    get_idea_resource,
)

# Server 2: Agent Output
from app.mcp.tools.agent_output_tools import (
    save_agent_output,
    get_agent_outputs,
    get_latest_validation_result,
    get_agent_resource,
)

# Server 3: Survey
from app.mcp.tools.survey_tools import (
    create_survey_draft,
    publish_survey,
    get_survey_questions,
    get_survey_responses,
    get_survey_resource,
)

# Server 4: Analytics
from app.mcp.tools.analytics_tools import (
    calculate_response_count,
    calculate_interest_score,
    summarize_pain_points,
    summarize_willingness_to_pay,
    get_analytics_resource,
)

# Server 5: Report
from app.mcp.tools.report_tools import (
    generate_validation_report,
    get_report_status,
    get_report_download_link,
    get_report_resource,
)

# Server 6: Real-Time Web Search & Web Scraping
from app.mcp.tools.web_tools import (
    web_search,
    scrape_webpage,
    OPENAI_WEB_TOOL_SCHEMAS,
)

logger = logging.getLogger(__name__)


# ── Agent Tool Permission Access Control Matrix ──────────────────────────────
ALLOWED_AGENT_TOOLS: dict[str, set[str]] = {
    "idea_validation_agent": {"get_idea_details", "save_agent_output", "web_search"},
    "market_research_agent": {"get_idea_details", "save_agent_output", "web_search", "scrape_webpage"},
    "survey_intelligence_agent": {
        "get_idea_details",
        "create_survey_draft",
        "get_survey_responses",
        "save_agent_output",
        "web_search",
    },
    "gtm_strategy_agent": {"get_idea_details", "get_agent_outputs", "save_agent_output", "web_search"},
    "financial_readiness_agent": {"get_idea_details", "save_agent_output", "web_search"},
    "ai_mentor": {
        "get_agent_outputs",
        "get_latest_validation_result",
        "get_survey_responses",
        "generate_validation_report",
        "web_search",
        "scrape_webpage",
    },
}



class MCPToolRegistry:
    """
    Central registry dispatching tool executions and resource resolutions for agents.
    Enforces the Agent Tool Permission Access Control Matrix.
    """

    _instance: "MCPToolRegistry | None" = None

    def __new__(cls) -> "MCPToolRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools: dict[str, Callable[..., Awaitable[Any]]] = {}
            cls._instance._resource_handlers: dict[str, Callable[[str], Awaitable[Any]]] = {}
            cls._instance._register_default_servers()
        return cls._instance

    def register_tool(self, name: str, func: Callable[..., Awaitable[Any]]) -> None:
        """Register an MCP tool handler by name."""
        self._tools[name] = func
        logger.info(f"[MCPToolRegistry] Registered tool: '{name}'")

    def register_resource_handler(
        self, scheme: str, handler: Callable[[str], Awaitable[Any]]
    ) -> None:
        """Register an MCP resource handler by URI scheme (e.g. 'idea', 'survey')."""
        self._resource_handlers[scheme] = handler
        logger.info(f"[MCPToolRegistry] Registered resource scheme: '{scheme}://'")

    def is_agent_authorized(self, caller_agent: str | None, tool_name: str) -> bool:
        """Verify if caller agent is permitted to execute the given tool."""
        if not caller_agent:
            # System / Internal calls without explicit agent identity are allowed
            return True

        allowed_tools = ALLOWED_AGENT_TOOLS.get(caller_agent)
        if allowed_tools is None:
            # If agent not listed in matrix, deny by default
            return False

        return tool_name in allowed_tools

    async def call_tool(
        self, name: str, caller_agent: str | None = None, **kwargs
    ) -> dict[str, Any]:
        """Execute an MCP tool by name with permission checking."""
        if not self.is_agent_authorized(caller_agent, name):
            logger.warning(
                f"[MCP Security Violation] Agent '{caller_agent}' denied access to tool '{name}'."
            )
            return {
                "success": False,
                "error": f"Permission Denied: Agent '{caller_agent}' is not authorized to call tool '{name}'.",
            }

        tool_func = self._tools.get(name)
        if not tool_func:
            logger.error(f"[MCPToolRegistry] Tool not found: '{name}'")
            return {"success": False, "error": f"Tool '{name}' not found."}

        try:
            if inspect.iscoroutinefunction(tool_func):
                result = await tool_func(**kwargs)
            else:
                result = tool_func(**kwargs)
            return {"success": True, "result": result}
        except Exception as e:
            logger.error(f"[MCPToolRegistry] Tool '{name}' error: {e}")
            return {"success": False, "error": str(e)}

    async def read_resource(self, uri: str) -> dict[str, Any]:
        """Resolve and read an MCP resource by URI."""
        if "://" not in uri:
            return {"success": False, "error": f"Invalid resource URI: '{uri}'"}

        scheme = uri.split("://")[0]
        handler = self._resource_handlers.get(scheme)
        if not handler:
            return {"success": False, "error": f"No handler for scheme '{scheme}://'"}

        try:
            if inspect.iscoroutinefunction(handler):
                res = await handler(uri)
            else:
                res = handler(uri)
            return {"success": True, "resource": res}
        except Exception as e:
            logger.error(f"[MCPToolRegistry] Resource '{uri}' read error: {e}")
            return {"success": False, "error": str(e)}

    def list_tools(self) -> list[str]:
        """List names of all registered MCP tools."""
        return list(self._tools.keys())

    def list_resource_schemes(self) -> list[str]:
        """List all registered MCP resource schemes."""
        return [f"{s}://" for s in self._resource_handlers.keys()]

    def get_openai_tool_definitions(self, caller_agent: str | None = None) -> list[dict[str, Any]]:
        """
        Return OpenAI-compatible JSON tool schemas for all tools authorized
        for the given caller_agent.
        """
        allowed = ALLOWED_AGENT_TOOLS.get(caller_agent, set()) if caller_agent else set(self._tools.keys())
        tools_list = []
        for tool_name in allowed:
            if tool_name in OPENAI_WEB_TOOL_SCHEMAS:
                tools_list.append(OPENAI_WEB_TOOL_SCHEMAS[tool_name])
        return tools_list

    def _register_default_servers(self) -> None:
        """Register all Phase 1 & Phase 2 internal MCP servers & resource schemes."""
        # 1. Idea Context Server
        self.register_tool("get_idea_details", get_idea_details)
        self.register_tool("update_idea_status", update_idea_status)
        self.register_tool("get_founder_validation_goal", get_founder_validation_goal)
        self.register_resource_handler("idea", get_idea_resource)

        # 2. Agent Output Server
        self.register_tool("save_agent_output", save_agent_output)
        self.register_tool("get_agent_outputs", get_agent_outputs)
        self.register_tool("get_latest_validation_result", get_latest_validation_result)
        self.register_resource_handler("agent", get_agent_resource)

        # 3. Survey Server
        self.register_tool("create_survey_draft", create_survey_draft)
        self.register_tool("publish_survey", publish_survey)
        self.register_tool("get_survey_questions", get_survey_questions)
        self.register_tool("get_survey_responses", get_survey_responses)
        self.register_resource_handler("survey", get_survey_resource)

        # 4. Analytics Server
        self.register_tool("calculate_response_count", calculate_response_count)
        self.register_tool("calculate_interest_score", calculate_interest_score)
        self.register_tool("summarize_pain_points", summarize_pain_points)
        self.register_tool("summarize_willingness_to_pay", summarize_willingness_to_pay)
        self.register_resource_handler("analytics", get_analytics_resource)

        # 5. Report Server
        self.register_tool("generate_validation_report", generate_validation_report)
        self.register_tool("get_report_status", get_report_status)
        self.register_tool("get_report_download_link", get_report_download_link)
        self.register_resource_handler("report", get_report_resource)

        # 6. Real-Time Web Search & Scraping Server
        self.register_tool("web_search", web_search)
        self.register_tool("scrape_webpage", scrape_webpage)



mcp_tool_registry = MCPToolRegistry()
