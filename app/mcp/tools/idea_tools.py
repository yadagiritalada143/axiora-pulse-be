"""
MCP Server 1: Idea Context Server
──────────────────────────────────────────────────────────────────────────────
Provides tools and resources for querying and updating founder idea context.

Tools:
  - get_idea_details
  - update_idea_status
  - get_founder_validation_goal

Resources:
  - idea://brief/{idea_id}
  - idea://target_customer/{idea_id}
  - idea://industry/{idea_id}
  - idea://business_stage/{idea_id}
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Simulated database store for idea context
_IDEAS_STORE: dict[str, dict[str, Any]] = {
    "idea_default": {
        "idea_id": "idea_default",
        "title": "AI Idea Validation Workspace",
        "description": "Automated startup validation platform using multi-agent LLM analysis.",
        "problem_statement": "Founders waste months building products without testing key market assumptions.",
        "target_customer": "B2B SaaS Founders & Product Managers",
        "industry": "Software & AI",
        "business_stage": "Ideation",
        "status": "draft",
        "founder_validation_goal": "Validate buyer willingness to pay for automated research reports",
    }
}


# ── MCP Tools ──────────────────────────────────────────────────────────────────

async def get_idea_details(idea_id: str) -> dict[str, Any]:
    """MCP Tool: get_idea_details"""
    logger.info(f"[MCP Idea Context Server] get_idea_details(idea_id='{idea_id}')")
    idea = _IDEAS_STORE.get(idea_id, _IDEAS_STORE["idea_default"])
    return {"success": True, "idea": idea}


async def update_idea_status(idea_id: str, status: str) -> dict[str, Any]:
    """MCP Tool: update_idea_status"""
    logger.info(f"[MCP Idea Context Server] update_idea_status(idea_id='{idea_id}', status='{status}')")
    if idea_id in _IDEAS_STORE:
        _IDEAS_STORE[idea_id]["status"] = status
    else:
        _IDEAS_STORE["idea_default"]["status"] = status
    return {"success": True, "idea_id": idea_id, "new_status": status}


async def get_founder_validation_goal(idea_id: str) -> dict[str, Any]:
    """MCP Tool: get_founder_validation_goal"""
    logger.info(f"[MCP Idea Context Server] get_founder_validation_goal(idea_id='{idea_id}')")
    idea = _IDEAS_STORE.get(idea_id, _IDEAS_STORE["idea_default"])
    return {
        "success": True,
        "idea_id": idea_id,
        "founder_validation_goal": idea.get("founder_validation_goal", ""),
    }


# ── MCP Resource Resolver ─────────────────────────────────────────────────────

async def get_idea_resource(uri: str) -> dict[str, Any]:
    """
    MCP Resource Handler: idea://
    URIs:
      - idea://brief/{idea_id}
      - idea://target_customer/{idea_id}
      - idea://industry/{idea_id}
      - idea://business_stage/{idea_id}
    """
    logger.info(f"[MCP Idea Context Server] Reading resource uri='{uri}'")
    parts = uri.replace("idea://", "").split("/")
    resource_type = parts[0] if parts else "brief"
    idea_id = parts[1] if len(parts) > 1 else "idea_default"

    idea = _IDEAS_STORE.get(idea_id, _IDEAS_STORE["idea_default"])

    if resource_type == "brief":
        content = {
            "title": idea["title"],
            "description": idea["description"],
            "problem_statement": idea["problem_statement"],
        }
    elif resource_type == "target_customer":
        content = {"target_customer": idea["target_customer"]}
    elif resource_type == "industry":
        content = {"industry": idea["industry"]}
    elif resource_type == "business_stage":
        content = {"business_stage": idea["business_stage"]}
    else:
        content = idea

    return {"uri": uri, "mimeType": "application/json", "content": content}
