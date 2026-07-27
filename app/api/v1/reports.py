"""
app/api/v1/reports.py
────────────────────────────────────────────────────────────────────────────────
DEPRECATED — Report endpoints have been consolidated under /api/v1/workspaces.

All report download and export operations now live as workspace sub-resources:
  GET  /api/v1/workspaces/{workspace_id}/reports/{agent_name}  ← replaces GET /api/v1/reports/workspace/{id}/agent/{name}
  POST /api/v1/workspaces/{workspace_id}/reports/export        ← replaces POST /api/v1/reports/export

This module is kept as an empty stub to avoid import errors during the transition.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/reports", tags=["Reports (Deprecated)"])

# All routes removed — see /api/v1/workspaces/{workspace_id}/reports/{agent_name}
