"""
MCP Server 5: Report Server
──────────────────────────────────────────────────────────────────────────────
Provides tools and resources for compiling, formatting, and serving final startup validation reports.

Tools:
  - generate_validation_report
  - get_report_status
  - get_report_download_link

Resources:
  - report://template/{template_id}
  - report://content_blocks/{report_id}
"""
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Simulated in-memory store for validation reports
_REPORTS_STORE: dict[str, dict[str, Any]] = {
    "report_default": {
        "report_id": "report_default",
        "idea_id": "idea_default",
        "title": "Comprehensive Idea Validation Master Report",
        "status": "completed",
        "download_url": "https://api.axiorapulse.com/v1/reports/report_default/download.pdf",
        "created_at": "2026-07-30T10:00:00Z",
        "content_blocks": [
            {"section": "Executive Summary", "status": "verified"},
            {"section": "Problem & Pain Analysis", "status": "verified"},
            {"section": "Market & Persona Profile", "status": "verified"},
            {"section": "Survey Intelligence Findings", "status": "verified"},
        ],
    }
}


# ── MCP Tools ──────────────────────────────────────────────────────────────────

async def generate_validation_report(idea_id: str, title: str = "Validation Master Report") -> dict[str, Any]:
    """MCP Tool: generate_validation_report"""
    logger.info(f"[MCP Report Server] generate_validation_report(idea_id='{idea_id}', title='{title}')")
    report_id = f"report_{idea_id}_{len(_REPORTS_STORE) + 1}"
    record = {
        "report_id": report_id,
        "idea_id": idea_id,
        "title": title,
        "status": "generating",
        "download_url": f"https://api.axiorapulse.com/v1/reports/{report_id}/download.pdf",
        "created_at": datetime.utcnow().isoformat(),
        "content_blocks": [
            {"section": "Problem Analysis", "status": "ready"},
            {"section": "Market Profile", "status": "ready"},
        ],
    }
    _REPORTS_STORE[report_id] = record
    return {"success": True, "report_id": report_id, "status": "generating"}


async def get_report_status(report_id: str) -> dict[str, Any]:
    """MCP Tool: get_report_status"""
    logger.info(f"[MCP Report Server] get_report_status(report_id='{report_id}')")
    report = _REPORTS_STORE.get(report_id, _REPORTS_STORE["report_default"])
    return {
        "success": True,
        "report_id": report_id,
        "status": report.get("status", "completed"),
        "title": report.get("title", ""),
    }


async def get_report_download_link(report_id: str) -> dict[str, Any]:
    """MCP Tool: get_report_download_link"""
    logger.info(f"[MCP Report Server] get_report_download_link(report_id='{report_id}')")
    report = _REPORTS_STORE.get(report_id, _REPORTS_STORE["report_default"])
    return {
        "success": True,
        "report_id": report_id,
        "download_url": report.get("download_url", ""),
        "expires_in_seconds": 86400,
    }


# ── MCP Resource Resolver ─────────────────────────────────────────────────────

async def get_report_resource(uri: str) -> dict[str, Any]:
    """
    MCP Resource Handler: report://
    URIs:
      - report://template/{template_id}
      - report://content_blocks/{report_id}
    """
    logger.info(f"[MCP Report Server] Reading resource uri='{uri}'")
    parts = uri.replace("report://", "").split("/")
    resource_type = parts[0] if parts else "content_blocks"
    identifier = parts[1] if len(parts) > 1 else "report_default"

    if resource_type == "template":
        content = {
            "template_id": identifier,
            "name": "Standard Startup Validation Report Template",
            "sections": [
                "Executive Summary",
                "Problem Analysis",
                "Market & Customer Persona",
                "Survey Intelligence",
                "Final Recommendation & Scorecard",
            ],
        }
    elif resource_type == "content_blocks":
        report = _REPORTS_STORE.get(identifier, _REPORTS_STORE["report_default"])
        content = {
            "report_id": report["report_id"],
            "content_blocks": report.get("content_blocks", []),
        }
    else:
        content = _REPORTS_STORE.get(identifier, _REPORTS_STORE["report_default"])

    return {"uri": uri, "mimeType": "application/json", "content": content}
