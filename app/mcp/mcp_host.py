"""
MCP Host Protocol Endpoint / Transport Layer
──────────────────────────────────────────────────────────────────────────────
Translates incoming Model Context Protocol (MCP) JSON-RPC requests
to the central MCPToolRegistry dispatcher.

Supported JSON-RPC methods:
  - tools/list      : List all available MCP tools across the 5 servers.
  - tools/call      : Invoke a specified MCP tool by name with permission checking.
  - resources/list  : List registered resource schemes.
  - resources/read  : Read resource content by URI.
"""
import logging
from typing import Any

from app.mcp.tool_registry import mcp_tool_registry

logger = logging.getLogger(__name__)


class MCPHost:
    """
    Host interface receiving agent tool & resource invocation requests.
    Enforces agent tool permissions via caller_agent parameter.
    """

    async def handle_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Handle incoming JSON-RPC 2.0 requests.
        Format:
          {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
               "name": "create_survey_draft",
               "caller_agent": "survey_intelligence_agent",
               "arguments": {"idea_id": "123", ...}
            },
            "id": 1
          }
        """
        req_id = payload.get("id", 1)
        method = payload.get("method", "")
        params = payload.get("params", {})

        logger.info(f"[MCP Host] JSON-RPC request id={req_id} method='{method}'")

        if method == "tools/list":
            tools = mcp_tool_registry.list_tools()
            return {
                "jsonrpc": "2.0",
                "result": {"tools": [{"name": t} for t in tools]},
                "id": req_id,
            }

        elif method == "tools/call":
            tool_name = params.get("name", "")
            caller_agent = params.get("caller_agent")
            arguments = params.get("arguments", {})

            res = await mcp_tool_registry.call_tool(
                name=tool_name, caller_agent=caller_agent, **arguments
            )

            if res.get("success"):
                return {
                    "jsonrpc": "2.0",
                    "result": res.get("result"),
                    "id": req_id,
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": res.get("error", "Internal error")},
                    "id": req_id,
                }

        elif method == "resources/list":
            schemes = mcp_tool_registry.list_resource_schemes()
            return {
                "jsonrpc": "2.0",
                "result": {"resource_schemes": schemes},
                "id": req_id,
            }

        elif method == "resources/read":
            uri = params.get("uri", "")
            res = await mcp_tool_registry.read_resource(uri)
            if res.get("success"):
                return {
                    "jsonrpc": "2.0",
                    "result": res.get("resource"),
                    "id": req_id,
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "error": {"code": -32602, "message": res.get("error", "Resource not found")},
                    "id": req_id,
                }

        else:
            return {
                "jsonrpc": "2.0",
                "error": {"code": -32601, "message": f"Method '{method}' not found"},
                "id": req_id,
            }


mcp_host = MCPHost()
