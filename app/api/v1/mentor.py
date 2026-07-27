"""
app/api/v1/mentor.py
────────────────────────────────────────────────────────────────────────────────
DEPRECATED — Mentor endpoints have been consolidated under /api/v1/workspaces.

All chat, state retrieval, and reset operations now live as workspace sub-resources:
  POST  /api/v1/workspaces/{workspace_id}/chat   ← replaces POST /api/v1/mentor/chat
  GET   /api/v1/workspaces/{workspace_id}/state  ← replaces GET  /api/v1/mentor/workspace/{id}
  POST  /api/v1/workspaces/{workspace_id}/reset  ← replaces POST /api/v1/mentor/reset/{id}

This module is kept as an empty stub to avoid import errors during the transition.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/mentor", tags=["AI Mentor (Deprecated)"])

# All routes removed — see /api/v1/workspaces/{workspace_id}/chat  |  /state  |  /reset
