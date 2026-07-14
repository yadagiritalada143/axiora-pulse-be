from pydantic import BaseModel, Field
from typing import Any, Optional
from enum import Enum
from datetime import datetime


class AgentStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentInput(BaseModel):
    """Input payload passed to every agent."""

    idea_title: str
    idea_description: str
    problem_statement: str
    target_customer: str
    industry: str = "general"
    founder_validation_goal: str = "validate my idea"
    geography: str = "global"
    additional_context: dict[str, Any] = Field(default_factory=dict)


class AgentOutput(BaseModel):
    """Structured output returned by every agent after execution."""

    agent_name: str
    status: AgentStatus
    score: Optional[float] = None           # 0–100
    confidence: Optional[float] = None      # 0.0–1.0
    data: Optional[dict[str, Any]] = None   # agent-specific parsed output
    error: Optional[str] = None
    model_used: str = ""
    tokens_input: int = 0
    tokens_output: int = 0
    executed_at: datetime = Field(default_factory=datetime.utcnow)
