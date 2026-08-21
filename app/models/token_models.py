"""
app/models/token_models.py
────────────────────────────────────────────────────────────────────────────────
Pydantic models for Token Usage tracking and Analytics endpoints.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


class TokenUsageLogOut(BaseModel):
    id: int
    user_id: int
    workspace_id: Optional[int] = None
    source: str
    agent_name: Optional[str] = None
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated_cost: float
    metadata_json: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserTokenTotalOut(BaseModel):
    id: int
    user_id: int
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    total_cost: float = 0.0
    total_calls: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SourceTokenBreakdown(BaseModel):
    source: str
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    call_count: int = 0


class ModelTokenBreakdown(BaseModel):
    model: str
    provider: str
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    call_count: int = 0


class WorkspaceTokenSummaryOut(BaseModel):
    workspace_id: int
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    total_calls: int = 0
    by_source: List[SourceTokenBreakdown] = Field(default_factory=list)
    by_model: List[ModelTokenBreakdown] = Field(default_factory=list)
    recent_logs: List[TokenUsageLogOut] = Field(default_factory=list)


class WorkspaceUsageEntry(BaseModel):
    workspace_id: Optional[int] = None
    workspace_name: Optional[str] = None
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    total_calls: int = 0


class DailyTokenUsage(BaseModel):
    date: str  # YYYY-MM-DD
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost: float = 0.0
    call_count: int = 0


class UserTokenSummaryOut(BaseModel):
    user_id: int
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    total_calls: int = 0
    by_workspace: List[WorkspaceUsageEntry] = Field(default_factory=list)
    by_source: List[SourceTokenBreakdown] = Field(default_factory=list)
    by_model: List[ModelTokenBreakdown] = Field(default_factory=list)
    daily_usage: List[DailyTokenUsage] = Field(default_factory=list)


class AdminUserTokenUsage(BaseModel):
    user_id: int
    username: str
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    estimated_cost: float = 0.0
    total_calls: int = 0


class AdminTokenAnalyticsOut(BaseModel):
    total_platform_tokens: int = 0
    total_platform_prompt_tokens: int = 0
    total_platform_completion_tokens: int = 0
    total_platform_cost: float = 0.0
    total_platform_calls: int = 0
    top_users: List[AdminUserTokenUsage] = Field(default_factory=list)
    by_model: List[ModelTokenBreakdown] = Field(default_factory=list)
    by_source: List[SourceTokenBreakdown] = Field(default_factory=list)


class TokenAnalyticsEnvelope(BaseModel):
    success: bool = True
    data: Any
    message: Optional[str] = None
