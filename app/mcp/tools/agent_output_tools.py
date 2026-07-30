"""
MCP Server 2: Agent Output Server
──────────────────────────────────────────────────────────────────────────────
Provides tools and resources for storing and retrieving agent execution logs and scores.

Tools:
  - save_agent_output
  - get_agent_outputs
  - get_latest_validation_result

Resources:
  - agent://history/{idea_id}
  - agent://latest_result/{idea_id}
"""
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Simulated in-memory store for agent outputs
_AGENT_OUTPUTS_STORE: list[dict[str, Any]] = []


# ── MCP Tools ──────────────────────────────────────────────────────────────────

async def save_agent_output(
    agent_name: str, idea_id: str, score: float, data: dict[str, Any]
) -> dict[str, Any]:
    """MCP Tool: save_agent_output"""
    logger.info(f"[MCP Agent Output Server] save_agent_output('{agent_name}', idea_id='{idea_id}', score={score})")
    entry = {
        "log_id": f"log_{agent_name}_{len(_AGENT_OUTPUTS_STORE) + 1}",
        "agent_name": agent_name,
        "idea_id": idea_id,
        "score": score,
        "data": data,
        "created_at": datetime.utcnow().isoformat(),
    }
    _AGENT_OUTPUTS_STORE.append(entry)
    return {"success": True, "log_id": entry["log_id"], "status": "saved"}


async def get_agent_outputs(
    idea_id: str, agent_name: str | None = None
) -> dict[str, Any]:
    """MCP Tool: get_agent_outputs"""
    logger.info(f"[MCP Agent Output Server] get_agent_outputs(idea_id='{idea_id}', agent_name='{agent_name}')")
    results = [
        item for item in _AGENT_OUTPUTS_STORE
        if item["idea_id"] == idea_id and (agent_name is None or item["agent_name"] == agent_name)
    ]
    return {"success": True, "count": len(results), "outputs": results}


async def get_latest_validation_result(idea_id: str) -> dict[str, Any]:
    """MCP Tool: get_latest_validation_result"""
    logger.info(f"[MCP Agent Output Server] get_latest_validation_result(idea_id='{idea_id}')")
    filtered = [item for item in _AGENT_OUTPUTS_STORE if item["idea_id"] == idea_id]
    latest = filtered[-1] if filtered else None
    return {"success": True, "idea_id": idea_id, "latest_result": latest}


# ── MCP Resource Resolver ─────────────────────────────────────────────────────

async def get_agent_resource(uri: str) -> dict[str, Any]:
    """
    MCP Resource Handler: agent://
    URIs:
      - agent://history/{idea_id}
      - agent://latest_result/{idea_id}
    """
    logger.info(f"[MCP Agent Output Server] Reading resource uri='{uri}'")
    parts = uri.replace("agent://", "").split("/")
    resource_type = parts[0] if parts else "history"
    idea_id = parts[1] if len(parts) > 1 else "idea_default"

    if resource_type == "history":
        filtered = [item for item in _AGENT_OUTPUTS_STORE if item["idea_id"] == idea_id]
        content = {"idea_id": idea_id, "history": filtered}
    elif resource_type == "latest_result":
        filtered = [item for item in _AGENT_OUTPUTS_STORE if item["idea_id"] == idea_id]
        latest = filtered[-1] if filtered else None
        content = {"idea_id": idea_id, "latest_result": latest}
    else:
        content = {"idea_id": idea_id, "outputs": _AGENT_OUTPUTS_STORE}

    return {"uri": uri, "mimeType": "application/json", "content": content}
